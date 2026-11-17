# Qwen3-0.6B 第一阶段闭环实验报告（910B4-126 / 114）

日期：2026-11-17  
运行机：`910b4-126`、`910b4-114`，各 8 × Ascend 910B4（32 GiB HBM/die）  
模型：Qwen3-0.6B 架构（28 层、hidden 1024、16 heads、8 KV heads、vocab 151936），
`from_config` 随机初始化；本实验测吞吐/显存，不测收敛。  
数据：`/root/irsi-workspace/data/tiny-packed`（合成 packed 数据，2048 token/record）  
框架：HyperParallel + `patches/0001-qwen3-recompute-policy.patch`（126 已应用，114 同步后同样带 policy）  
执行：8 卡、32 步、global batch 8、micro batch 1、bf16、FSDP `dp_shard_size=8`、full determinism、seed 42。

## 1. 结论

两套契约、两台机器都跑通了 `environment → clean baseline → observation → observed baseline → neutrality → calibrated → decision → development → execution → gates → judgment → archive/commit` 闭环。

- **重计算候选**：`off` 是唯一 keep；相对 observed baseline：
  - 126：`17160.25 → 21054.50`，**+22.69%**
  - 114：`16109.65 → 20871.40`，**+29.56%**
- **层级重计算候选**：`layers-0` 是唯一 keep；相对 observed baseline：
  - 126：`15966.00 → 21566.85`，**+35.08%**
  - 114：`16410.60 → 23140.50`，**+41.01%**

所有候选的 `loss/grad_norm` 指纹完全相同（`065d26c1…`），`receipt`、`bitwise`、`memory` 三门全 PASS；本轮没有 crash/env_error/patch_error。`off`/`layers-0` 的吞吐最高，但显存峰值 9.28 GiB；full/selective 省显存但更慢。这说明在本 workload 下，吞吐最优解是**关闭重计算**，重计算只在显存约束收紧时才有价值。

## 2. 契约与候选

`contracts/qwen3-0.6b-recompute.yaml`：
- baseline：`activation_checkpoint.mode=full`
- candidates：`off`、`control`、`selective`、`selective-swap`、`full-swap`
- budget `max_trials=4`，实际 keep 为 `off`

`contracts/qwen3-0.6b-layerwise.yaml`：
- baseline：`activation_checkpoint.mode=full`
- candidates：`control`、`layers-0`、`layers-6`、`layers-12`、`layers-18`
- budget `max_trials=5`，实际 keep 为 `layers-0`

`layers-0` 等价于“所有 activation 保留、不做层重计算”，因此它和 `off` 的吞吐/显存接近；但它走 `selection.source=model_adapter_safe_regions` 路径。  
注意：安装 Qwen3 policy 后，`mode=full` 会走 adapter-region wrapper 路径，故 layerwise 契约的 baseline 比不装 patch 的 full 更慢；这也是 `layers-0` 相对 baseline 的增益高于 `off` 契约的原因之一。

## 3. 结果明细

### 3.1 910b4-126 — recompute 契约

| 候选 | status | tps | 峰值 GiB | 相对 observed baseline |
|---|---:|---:|---:|---:|
| clean baseline | baseline | 16846.95 | — | — |
| observed baseline（reference） | calibrated | 17160.25 | — | — |
| full-swap | discard | 15616.95 | 4.78267 | -8.99% |
| off | keep | 21054.50 | 9.27897 | **+22.69%** |
| selective | discard | 11849.80 | 5.96810 | -30.95% |
| selective-swap | discard | 11874.85 | 5.85341 | -30.77% |

### 3.2 910b4-114 — recompute 契约

| 候选 | status | tps | 峰值 GiB | 相对 observed baseline |
|---|---:|---:|---:|---:|
| clean baseline | baseline | 16909.95 | — | — |
| observed baseline（reference） | calibrated | 16109.65 | — | — |
| full-swap | discard | 15736.50 | 4.78267 | -2.32% |
| off | keep | 20871.40 | 9.27897 | **+29.56%** |
| selective | discard | 12621.05 | 5.96810 | -21.65% |
| selective-swap | discard | 11993.15 | 5.85341 | -25.55% |

### 3.3 910b4-126 — layerwise 契约

| 候选 | status | tps | 峰值 GiB | 相对 observed baseline |
|---|---:|---:|---:|---:|
| clean baseline | baseline | 16268.05 | — | — |
| observed baseline（reference） | calibrated | 15966.00 | — | — |
| layers-0 | keep | 21566.85 | 9.27897 | **+35.08%** |
| layers-12 | discard | 19281.50 | 7.40588 | +20.77% |
| layers-18 | discard | 17104.00 | 6.46859 | +7.13% |
| layers-6 | discard | 19442.40 | 8.34365 | +21.78% |
| control | discard | 16458.05 | 4.89251 | +3.08% |

### 3.4 910b4-114 — layerwise 契约

| 候选 | status | tps | 峰值 GiB | 相对 observed baseline |
|---|---:|---:|---:|---:|
| clean baseline | baseline | 15795.65 | — | — |
| observed baseline（reference） | calibrated | 16410.60 | — | — |
| layers-0 | keep | 23140.50 | 9.27897 | **+41.01%** |
| layers-12 | discard | 19497.25 | 7.40588 | +18.81% |
| layers-18 | discard | 18421.10 | 6.46859 | +12.25% |
| layers-6 | discard | 20917.80 | 8.34316 | +27.46% |
| control | discard | 16160.90 | 4.89251 | -1.52% |

说明：表中“相对 observed baseline”对 discard 候选也给出数值，便于看 frontier；判定仍按 `best_before`（当前 best）而不是 baseline 计算。

## 4. 观测与基线中性

观测计划是 task-level、与假设无关；本轮 `observation_patch` 为空，因此 clean baseline 与 observed baseline 是同一配置的两次独立测量：

- `numeric_identical=True`，clean/observed 的 `loss/grad_norm` 指纹相同；
- `peak_mem_delta=0.0`；
- clean-vs-observed 的 tps 差（126 recompute +1.86%，114 recompute -4.73%，126 layerwise -1.86%，114 layerwise +3.89%）是运行噪声，不是观测开销；
- reference 固定为 **observed baseline**；clean baseline 只作为观测开销/漂移对照。

这也验证了“观测中性=数值语义不变”不等于“性能零开销”：本轮没有观测 patch，所以没有真实的观测开销；若以后启用非空 patch，必须用同一 neutrality 检查记录 overhead。

## 5. commit 与回退

每个候选只产生一个 commit：
- keep：`trial config + step report` 入库；
- discard/crash：只提交 step report，候选 config/patch 不入库；
- baseline/calibration：提交 `environment_report.json`、`calibration.json`（及 observation.patch，若存在）。

910b4-126 recompute：`438b007` environment → `15d3f3b` calibration → `4f39eff` full-swap discard → `fbbe5e8` off keep → `dd767d3` selective discard → `6815ade` selective-swap discard。  
910b4-126 layerwise：`4672dfd` environment → `359e453` calibration → `2caec20` layers-0 keep → `13ba5ae` layers-12 discard → `3e93198` layers-18 discard → `38baa93` layers-6 discard → `cfb4a65` control discard。  
910b4-114 recompute：`41e9da5` environment → `883e177` calibration → `ce8f9af` full-swap discard → `be1cbe7` off keep → `bde2667` selective discard → `cd815e1` selective-swap discard。  
910b4-114 layerwise：`a0f5325` environment → `1a2df7c` calibration → `642fc75` layers-0 keep → `65e2288` layers-12 discard → `f815210` layers-18 discard → `59c94b4` layers-6 discard → `cb88bb8` control discard。

完整 git log 在导出结果目录的 `git-log.txt`。

## 6. 环境快照

两台机器均为 Python 3.11.18、`torch 2.9.0`、`torch_npu 2.9.0.post9`、Linux aarch64；`repo_commit` 为 null，因为运行现场的 HyperParallel checkout 不是 git 仓库（patch 已作为文件应用）。`env_setup` 均为 `source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh`。

## 7. 限制与下一步

- 模型是 Qwen3-0.6B **架构**的随机初始化，不是加载真实预训练权重；绝对 tps 受主机负载和 run-to-run 噪声影响（同一配置重复测量差可达 2–5%）。
- 数据是合成 packed 数据，不是真实语料；结论是“重计算策略在固定 workload 下的吞吐/显存 frontier”，不是模型质量结论。
- `layers-0` 的增益部分来自 Qwen3 policy 对 `full` 路径的改变；跨契约比较时要区分“同一 baseline 内比较”和“不同契约比较”。
- OpenJiuwen runtime 仍按约定暂缓；本轮只验证代码强制闭环 + HyperParallel 远端执行。

## 8. 复现路径

本仓库：
- `contracts/qwen3-0.6b-recompute.yaml`
- `contracts/qwen3-0.6b-layerwise.yaml`
- `workspace/configs/qwen3-0.6b/config.json`
- `workspace/configs/train_qwen3_06b.yaml`

导出结果：
- `results/qwen3-06b-20261117/126-recompute/`
- `results/qwen3-06b-20261117/126-layerwise/`
- `results/qwen3-06b-20261117/114-recompute/`
- `results/qwen3-06b-20261117/114-layerwise/`

运行命令（126 示例）：

```bash
cd /root/infra-rsi
/root/miniconda3/envs/irsi/bin/python -m irsi.cli run \
  --contract contracts/qwen3-0.6b-recompute.yaml \
  --runs-dir /root/irsi-workspace/runs
```

114 上需先 `source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh`，再执行同一命令；环境已同步。

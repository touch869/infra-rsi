# Qwen3-0.6B 并行策略实验报告（910b4-126，2026-11-18）

运行机：`910b4-126`，8 × Ascend 910B4（32 GiB HBM/die）  
模型：Qwen3-0.6B 架构（28 层、hidden 1024、16 heads、8 KV heads、vocab 151936），随机初始化；测吞吐/显存，不测收敛。  
数据：`/root/irsi-workspace/data/tiny-packed`（合成 packed 数据，2048 token/record）。  
执行：8 卡、32 步、global batch 8、micro batch 1、bf16、full determinism、seed 42。  
契约：`contracts/qwen3-0.6b-parallel.yaml`。  
基线：`tp_size=1`、`dp_shard_size=8`、`activation_checkpoint.mode=full`。

## 1. 结论

本轮并行策略实验跑通了 `environment → clean baseline → observation → observed baseline → neutrality → calibrated → decision → development → execution → gates → judgment → archive/commit` 闭环。

- **唯一 keep：`dp1`**（`tp_size=1`, `fsdp_config.dp_shard_size=1`，即 8 卡参数全复制）。
  - observed baseline：`15407.05`
  - `dp1`：`17348.45`
  - 提升：**+12.60%**
  - 峰值显存：**11.38 GiB**（预算 24 GiB）
- **TP 候选全部失败或远慢于基线**：
  - `tp2-dp4` 吞吐 `7542.16`（loss parity 通过，但远低于 best，discard）
  - `tp2-dp1`、`tp2-dp2`、`tp4-dp2`、`tp8-dp1` 均被 `numeric-parity` 判为 crash
- 这说明在本 workload 下，**纯 FSDP 参数复制**是吞吐最优解；TP 的通信开销远大于小模型的收益，且 TP 会改变数值轨迹。

## 2. 候选与结果

| 候选 | tp_size | dp_shard | tps | 峰值 GiB | 相对 baseline | 判决 |
|---|---:|---:|---:|---:|---:|---|
| clean baseline | 1 | 8 | 16665.5 | — | — | baseline |
| observed baseline（reference） | 1 | 8 | 15407.05 | 4.89 | — | calibrated |
| `dp1` | 1 | 1 | 17348.45 | 11.38 | **+12.60%** | **keep** |
| `dp2` | 1 | 2 | 15907.9 | 7.81 | +3.25% | discard |
| `dp4` | 1 | 4 | 16112.65 | 5.89 | +4.58% | discard |
| `tp2-dp4` | 2 | 4 | 7542.16 | 4.67 | -51.05% | discard |
| `tp2-dp2` | 2 | 2 | 7667.68 | 6.29 | -50.24% | crash |
| `tp2-dp1` | 2 | 1 | 8546.075 | 9.06 | -44.52% | crash |
| `tp4-dp2` | 4 | 2 | 3992.965 | 3.21 | -74.08% | crash |
| `tp8-dp1` | 8 | 1 | 2460.85 | 2.39 | -84.03% | crash |
| `control` | 1 | 8 | 16288.9 | 4.89 | +5.72% | discard |

说明：`control` 是 no-op 漂移对照，不是优化候选；它相对 baseline 的 +5.72% 说明同一配置的 run-to-run 噪声可达约 5–8%。clean baseline 16665.5 与 observed 15407.05 的差异也是运行噪声，本轮 observation patch 为空。

## 3. 验证面结果

### 3.1 `parallel-engagement`

所有候选均通过：运行时日志确实出现请求的 device mesh 与 ShardingPlanner 拓扑，例如：

- `dp1`: `Built device mesh (8, 1, 1), dense FSDP mesh (8, 1, 1)`
- `tp2-dp4`: `Built device mesh (4, 1, 2), dense FSDP mesh (1, 4, 2)`，并出现 `Running ShardingPlanner.plan(tp=2, cp=1, ep=1, sequence_parallel=False, loss_parallel=True)`

该门证明“配置请求”不等于“运行时实际采用”；仅检查 YAML 不够。

### 3.2 `numeric-parity`

并行候选改变了浮点归约顺序，因此不能用 `bitwise`。本轮契约使用：

```yaml
numeric-parity:
  rtol: 0.05
  atol: 1.0e-4
  fields:
    - loss
```

只比较 `loss` 轨迹；`grad_norm` 不作为语义判据，因为 TP/FSDP 的梯度归约与缩放不同。结果：

| 候选 | loss parity | 备注 |
|---|---|---|
| dp1 | PASS | 最大 loss 相对偏差约 2.76% |
| dp2 | PASS | 约 2.66% |
| dp4 | PASS | 约 2.50% |
| tp2-dp4 | PASS | 约 4.70%，但吞吐远低于 best |
| tp2-dp1 | FAIL | step 32: loss 10.508 → 11.1497 |
| tp2-dp2 | FAIL | step 25: loss 10.6008 → 11.1592 |
| tp4-dp2 | FAIL | step 16: loss 11.2647 → 11.8309 |
| tp8-dp1 | FAIL | step 16: loss 11.2647 → 11.8916 |

因此 `dp1` 的数值等价是“在 5% loss 容差内”，不是逐位相同。报告必须保留这个口径。

### 3.3 其他门

- `receipt`: 所有 32 步完成，exit 0。
- `memory`: 所有候选均 ≤ 24 GiB；`dp1` 峰值 11.38 GiB，是 keep 候选中最高的。

## 4. 关键发现

1. **TP 对小模型不利**：Qwen3-0.6B 只有 28 层、hidden 1024；TP=2/4/8 的 all-gather/reduce-scatter 开销远大于参数分片收益，吞吐降到基线的 16–51%。
2. **TP 会改变训练轨迹**：即使 `loss_parallel=true`，TP 的梯度归约与 FSDP 缩放会让 loss 轨迹漂移；`grad_norm` 差异更大。不能把 TP 当成数值中性修改。
3. **FSDP 参数复制是有效方向**：`dp_shard_size=1` 让每卡持有完整参数，减少 FSDP 分片通信；吞吐 +12.6%，代价是显存从 4.89 GiB 升到 11.38 GiB。
4. **`sequence_parallel` 不能与当前 packed-text 数据直接组合**：序列被切半而 labels 未切，loss 形状不匹配；本轮契约显式禁用。

## 5. commit 与回退

每个候选一个 commit，report 随 commit：

```text
b749cf5 environment baseline
6753ba4 observation patch + calibration
342b63e step 3 dp1 keep
1f79939 step 4 dp2 discard
fe32440 step 5 dp4 discard
9e09bd3 step 6 tp2-dp1 crash
14584ec step 7 tp2-dp2 crash
266b32a step 8 tp2-dp4 discard
4b13dfb step 9 tp4-dp2 crash
7c6c53c step 10 tp8-dp1 crash
212a036 step 11 control discard
```

keep 提交 `trial config + step report`；discard/crash 只提交 step report；失败候选配置不入库。

## 6. 环境快照

- Python 3.11.18
- `torch 2.9.0`
- `torch_npu 2.9.0.post9`
- Linux aarch64
- `env_setup`: `source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh`
- `repo_commit`: null（HyperParallel checkout 不是 git 仓库）

## 7. 限制

- 模型是 Qwen3-0.6B 架构随机初始化，不是预训练权重；绝对 tps 受主机负载影响。
- 数据是合成 packed 数据，不是真实语料。
- 本轮只在一台 910b4-126 上验证；跨机结论需另跑。
- `numeric-parity` 只比较 loss；grad_norm 的并行缩放差异未被判等。
- clean/observed baseline 差异约 8%，说明单轮噪声较大；`control` 的 +5.72% 也属于漂移。

## 8. 复现路径

本仓库：
- `contracts/qwen3-0.6b-parallel.yaml`
- `irsi/contract/surfaces/parallel.py`
- `irsi/gates/parallel.py`
- `knowledge/skills/hp/parallel-tensor/`
- `knowledge/skills/hp/parallel-frontier/`
- `knowledge/skills/hp/parallel-numeric-parity/`

导出结果：
- `results/qwen3-06b-20261117-parallel/`

运行命令：

```bash
cd /root/infra-rsi
/root/miniconda3/envs/irsi/bin/python -m irsi.cli run \
  --contract contracts/qwen3-0.6b-parallel.yaml \
  --runs-dir /root/irsi-workspace/runs
```

先 `source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh`，并保证 HyperParallel 与 `irsi-workspace` 在 `PYTHONPATH`/契约中可达。

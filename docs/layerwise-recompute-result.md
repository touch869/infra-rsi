# 层级重计算 RSI 结果（Qwen3 dense）

| 项 | 值 |
|---|---|
| 日期 | 2026-11-13 |
| 机器 | `910b4-126`，8 × Ascend 910B4（32 GiB HBM/die） |
| 模型 | 24 层 Qwen3（hidden 2048、seq 4096、随机初始化），32 步 |
| 框架 | HyperParallel + `patches/0001-qwen3-recompute-policy.patch` |
| 机制 | `activation_checkpoint.selection.source=model_adapter_safe_regions` + `layer_count` |
| 结论 | 层级开关打通；无约束下 `layers-0` 26 244.9 tps（同 run +34.29%）；8 GiB 预算下 `layers-6` 25 129.3（+28.04%）；6 GiB 下 `layers-14` 21 315.5（+9.39%） |

---

## 1. 实施内容

| 位置 | 改动 |
|---|---|
| HyperParallel（本地分支 `qwen3-recompute-policy`） | 新增 `qwen3/adapter/policies/activation_checkpointing.py`（`region_patterns=("model.layers.*",)`），并在 `qwen3/adapter/registration.py` 注册 `recompute=` |
| `patches/0001-qwen3-recompute-policy.patch` | 上述改动以 `git am` 补丁形式入库，附应用说明 |
| `irsi/contract/task_spec.py` | `InfraTaskSpec.domain_params`（通用插件参数，写入 `task.json`） |
| `irsi/contract/surfaces/recompute.py` | 新领域 `recompute-layerwise`：control + 由 `domain_params.layer_counts` 驱动的 `layer_count` 阶梯 |
| `contracts/medium-qwen3-layerwise{,-6gib,-8gib}.yaml` | 三个预算档位的契约 |
| `tests/` | 本地 22 个单测（领域阶梯、参数校验）+ HyperParallel 侧 2 个 policy 测试 |

HyperParallel 侧测试：

```
PYTHONPATH=/root/hyper-parallel python tests/ut/auto_models/models/qwen3/test_recompute_policy.py -v
# 2 tests OK（policy 结构 + adapter 注册）
```

## 2. 方法

三个契约共用同一 workload（24 层 Qwen3、8 卡、32 步、seed 42、bitwise 门、3% 噪声带、
warmup 8 / measured 16），只改显存预算与层数阶梯：

| 契约 | 显存门 | `layer_counts` |
|---|---|---|
| `medium-qwen3-layerwise` | 24 GiB | 0, 6, 12, 18 |
| `medium-qwen3-layerwise-6gib` | 6 GiB | 12, 14, 16, 20 |
| `medium-qwen3-layerwise-8gib` | 8 GiB | 4, 6, 8, 10 |

每个候选只改 `activation_checkpoint.mode=selective`、
`selection.source=model_adapter_safe_regions`、`selection.layer_count=k`；契约的只读键
（seed、determinism、batch、precision、compile、FSDP、`allow_cache_entry_mutation`）在整个
搜索中不可变。

## 3. 结果

### 3.1 无约束（24 GiB）

| trial | 状态 | tps | Δ vs baseline | 峰值 GiB |
|---|---|---|---|---|
| baseline（`full` → adapter regions） | reference | 19 543.4 | — | 3.99 |
| `control` | discard | 18 928.9 | −3.14%（漂移 suspected） | 3.99 |
| `layers-0` | **keep** | **26 244.9** | **+34.29%**（vs control +38.65%） | 9.06 |
| `layers-6` | discard | 22 866.1 | +16.99% | 7.68 |
| `layers-12` | discard | 22 322.4 | +14.22% | 6.29 |
| `layers-18` | discard | 20 985.4 | +7.38% | 4.89 |

### 3.2 6 GiB 预算

| trial | 状态 | tps | Δ vs baseline | 峰值 GiB |
|---|---|---|---|---|
| baseline | reference | 19 485.4 | — | 3.99 |
| `control` | discard | 19 850.4 | +1.87% | 3.99 |
| `layers-12` | **crash**（memory） | 21 609.1 | +10.90% | 6.29 > 6.00 |
| `layers-14` | **keep** | **21 315.5** | **+9.39%** | 5.83 |
| `layers-16` | discard | 21 775.6 | +11.75% | 5.36 |
| `layers-20` | discard | 19 676.7 | +0.98% | 4.40 |

`layers-16` 比保留点快 2.16%、显存更低，但差异落在 3% 噪声带内，按规则未替换
`layers-14`——这是当前“只按主指标做超噪声比较”的保守行为，见 §5。

### 3.3 8 GiB 预算

| trial | 状态 | tps | Δ vs baseline | 峰值 GiB |
|---|---|---|---|---|
| baseline | reference | 19 626.7 | — | 3.99 |
| `control` | discard | 19 410.3 | −1.10% | 3.99 |
| `layers-4` | **crash**（memory） | 23 466.7 | +19.57% | 8.14 > 8.00 |
| `layers-6` | **keep** | **25 129.3** | **+28.04%** | 7.68 |
| `layers-8` | discard | 23 994.9 | +22.25% | 7.21 |
| `layers-10` | discard | 21 021.1 | +7.10% | 6.75 |

三个 run 共 18 个 trial（含 baseline）的 loss/grad_norm 指纹全部相同
（`48f4302f…`）；`receipt` 与 `bitwise` 零失败，memory 门按设计拦下 2 个候选。

## 4. 关键发现

### 4.1 层级开关有效，但被两个端点夹住

`layers-0` ≈ 关闭重算（9.06 GiB / 26 244.9），`layers-24` ≈ `full`（3.99 GiB /
~19.5k）。层级选择在两者之间给出可用的显存-吞吐阶梯：8 GiB 预算下 `layers-6` 就比
`full` 快 28%（同 run），6 GiB 下只能选到 `layers-14`（+9.39%）。

### 4.2 装 policy 会改变 `full` 的语义（A/B）

同一配置背靠背跑两次，只差 `recompute=` 注册：

| 路径 | 机制 | tps | 峰值 GiB |
|---|---|---|---|
| 无 policy，`mode=full` | HF native gradient checkpointing | 21 099.5 | 4.01 |
| 有 policy，`mode=full` | 显式 `CheckpointWrapper`（自动升级） | 18 461.6 | 3.99 |

指纹相同，但显式 wrapper 慢约 12.5%。三个契约的 baseline（19 485–19 627）都低于
native 路径，与该归因一致。因此：

- **同 run 内**：winner 相对 baseline 的增益如上表；
- **相对 native block-full（21 099.5）**：`layers-0` +24.4%，`layers-6` +8.4%～+19.1%
  （两次测量），`layers-14` +1.0%（基本持平）。

### 4.3 噪声比契约假设的大

`layers-6` 在无约束 run 是 22 866，在 8 GiB run 是 25 129（+9.9%）；baseline 反而稳定在
19.5k。说明候选侧的 run-to-run 波动超过 3% 噪声带，精确的阶梯形状（例如 14 vs 16 层）
不可靠，粗粒度趋势（层数越少越快、显存越高）可靠。

## 5. 局限与后续

1. **上游化**：policy 目前是本地分支 + vendored patch，需要提 PR；
   `patches/README.md` 有应用方式。
2. **`full` 路径开销**：adapter-region full 走显式 wrapper，比 HF native 慢 ~12.5%。
   若上游接受，应让无显式 selection 的 `full` 继续走 native 路径，或对齐两条路径的开销。
3. **裁决规则**：`layers-16` 更快且更省显存却因噪声带被丢弃。后续可加“次指标不劣化时
   接受在噪声带内的更快候选”，或对候选做 `noise_confirm_reruns`。
4. **异构模型**：qwen3 24 层同构，前缀扫描足够；MoE/CSA/vision 模型需要
   `layer_indices` 子集搜索，`domain_params` 已预留扩展点。
5. **只覆盖单节点 8 卡、随机初始化小模型**，结论不外推到多节点/大模型。

## 6. 复现

```bash
# 运行机
git -C /root/hyper-parallel apply /root/infra-rsi/patches/0001-qwen3-recompute-policy.patch
irsi run --contract /root/infra-rsi/contracts/medium-qwen3-layerwise.yaml --runs-dir /root/irsi-workspace/runs
irsi run --contract /root/infra-rsi/contracts/medium-qwen3-layerwise-6gib.yaml --runs-dir /root/irsi-workspace/runs
irsi run --contract /root/infra-rsi/contracts/medium-qwen3-layerwise-8gib.yaml --runs-dir /root/irsi-workspace/runs

# 本地
python -m pytest -q      # 22 个单测
```

证据与逐 trial 指标：`results/layerwise-20261113/`。

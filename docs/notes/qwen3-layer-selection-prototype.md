# Qwen3 层级重计算支持评估（原型验证）

日期：2026-11-13　机器：`910b4-126`　结论：**工作量小，已在运行机验证可行**

> 后续（2026-11-13）：该 policy 已正式实现并入库为
> `patches/0001-qwen3-recompute-policy.patch`，三个预算档位的 RSI 闭环已跑通，
> 结果见 `docs/layerwise-recompute-result.md` 与 `results/layerwise-20261113/`。
> 本文保留最初的评估与原型数据。

## 问题

HyperParallel 的显式层级重计算（`activation_checkpoint.selection.*` +
`source=model_adapter_safe_regions`）要求模型声明 `ModelAdapterSpec.recompute`。当前仓库里
只有 `deepseek_v41` 注册了该字段，所以 qwen3 无法使用 `layer_count` / `layer_indices`。
这不是“HP 不支持 qwen3 的重计算”：`off` / `full` / `selective`（自动 SAC 策略）对 qwen3
都可用，阶段 1 的 baseline 与负例就是这样跑出来的。被关闭的只是**显式层覆盖**这一维。

拒绝而不是猜测的原因写在 `_adapter_recompute_spec`：`required=True` 时直接抛
`ValueError`。`RecomputePolicy` 承载的是模型自身的安全知识——哪些子模块可以重放、哪些
跨层状态生产者/消费者必须留在区域外、重放时需要固定哪些离散状态（DSV4.1 的 CSA indexer）。
通用回退无法安全地推断这些信息。

## 原型

在运行机的 `/root/hyper-parallel` 上临时打了两个改动（验证后已还原）：

1. 新增 `hyper_parallel/models/qwen3/adapter/policies/activation_checkpointing.py`：

```python
from hyper_parallel.models.adapter_spec import RecomputePolicy


def build_recompute_policy() -> RecomputePolicy:
    return RecomputePolicy(region_patterns=("model.layers.*",))
```

2. `hyper_parallel/models/qwen3/adapter/registration.py` 增加惰性加载并注册：

```python
def _load_recompute():
    from hyper_parallel.models.qwen3.adapter.policies.activation_checkpointing import (
        build_recompute_policy,
    )
    return build_recompute_policy()          # 注意：provider 本身要被调用，返回 Policy


QWEN3_ADAPTER_SPEC = ModelAdapterSpec(
    ...,
    recompute=_load_recompute,
)
```

第一个坑：`recompute=` 接收的是“零参调用后返回 `RecomputePolicy` 的 provider”，
直接返回 builder 函数会抛 `ModelAdapterSpec.recompute must return RecomputePolicy`。

## 验证

12 层 tiny、20 步、8 卡，数据与阶段 1 冒烟相同（`workspace/make_data.py` 种子生成）：

```yaml
activation_checkpoint:
  mode: selective
  selection:
    source: model_adapter_safe_regions
    layer_count: 6
```

结果：

| 项 | baseline (`full`) | `layer_count=6` |
|---|---|---|
| 状态 | 20 步通过 | 20 步通过 |
| 数值指纹 | `84b0ad95…` | `84b0ad95…`（**逐位一致**） |
| 吞吐 | 42 779.8 tps | 43 408.8 tps |
| 峰值显存 | 1.29 GiB | 1.98 GiB |

tiny 上的吞吐差在噪声内，不构成收益结论；这里只证明层级选择能跑通且语义不变。

## 成本与注意事项

- **代码量**：policy 约 20 行（qwen3 dense 无跨层状态、无 vision tower，不需要
  `exclude_patterns` / `exclude_predicate` / `on_applied`）；registration 约 8 行；UT 一个。
- **必须重跑 baseline**：`_apply_activation_checkpointing` 在 `mode=full` +
  `source=default` 且模型声明了 policy 时，会自动升级为 adapter regions
  （`layer_count=len(ac_layers)`）。注册 policy 会改变现有 `full` 的含义，阶段 1 的
  +20.63% 需要重新测量确认。
- **收益门槛**：当前 medium 配置 `off` 只用 9.06/24 GiB 且最快，层级选择在显存预算更紧
  （< 9 GiB）或模型/序列更大时才可能拿到更优点；它把 `full`→`off` 之间的离散点变成
  `layer_count` 阶梯（24 层 = 25 个前缀点，或任意 `layer_indices` 子集）。
- **上游流程**：这是 HyperParallel 的改动，需走上游评审；本仓库只需在 domain 里增加
  `layer_count` 候选，契约已允许该键。

预计工作量：局部实现 + UT + 重跑 baseline 约 **0.5–1 人日**（不含上游排队）。

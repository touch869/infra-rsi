# Phase-1 run: medium-qwen3-recompute

Evidence exported from the run machine; raw logs stay on the host.

| 项 | 值 |
|---|---|
| Host | `910b4-126` (8 × Ascend 910B4, 32 GiB HBM/die) |
| Task dir (remote) | `/root/irsi-workspace/runs/20261112T133547Z-medium-qwen3-recompute` |
| Contract | `contracts/medium-qwen3.yaml` (32 steps, noise 3%, gates receipt+bitwise+memory) |
| Model | 24-layer Qwen3 config, hidden 2048, seq 4096, random init (`from_config`) |
| Framework | HyperParallel (`/root/hyper-parallel`), torch 2.9.0 + torch_npu 2.9.0.post9, CANN 8.5.2 |

## Headline

| trial | status | tps | Δ vs baseline | Δ vs control | peak GiB | bitwise |
|---|---|---|---|---|---|---|
| baseline (`mode: full`) | reference | 21 416.4 | — | — | 4.01 | hash `48f430…`-class |
| `h01-off` | **keep** | **25 834.9** | **+20.63%** | **+15.78%** | 9.06 | identical |
| `h02-control` (no-op) | discard | 22 314.0 | +4.19% (**drift suspected**) | — | 4.01 | identical |
| `h03-selective` | discard | 14 616.0 | −31.75% | −43.43% | 4.88 | identical |
| `h04-selective-swap` | discard | 13 938.1 | −34.92% | −46.05% | 4.70 | identical |

- `robust=true`（相对 no-op control 仍超噪声带）
- no-op 对照漂移 +4.19%，超过 3% 噪声阀值 → `drift.suspected=true`；因此对外口径以
  **vs control 的 +15.78%** 为准
- 0 crash；四条决策的三道门全部通过（`receipt` / `bitwise` / `memory`）
- 单 trial 墙钟 54–70 s（32 步）

## Repeatability (same host, same contract)

| run (remote task dir) | steps | Δ vs baseline | no-op drift | robust |
|---|---|---|---|---|
| `20261112T132254Z` | 24 | +17.64% | +3.84% | n/a (pre-drift-detection) |
| `20261112T132758Z` | 32 | +11.18% | +2.42% | true |
| `20261112T133547Z` | 32 | +20.63% | +4.19% | true |

结论：同配置三次运行，收益区间 **+11% ~ +21%**，方向一致；漂移 2–4%，所以保守口径
（vs no-op 对照）是 **+8.6% ~ +15.8%**。tiny（12 层）单候选冒烟也给出 +17.93%。

## Files

```
report.md / report.json        最终报告（含 drift / robust 字段）
baseline.json                  baseline 摘要 + 门禁
decisions/*.json               每条候选的指标、门禁、覆盖项、产物路径
trials/<trial>/metrics.json    逐 step 指标（loss / grad_norm / tps / 显存）
trials/<trial>/train.yaml      该 trial 实际渲染出的训练配置
```

## Reproduce

```bash
# on the run host
irsi run --contract /root/infra-rsi/contracts/medium-qwen3.yaml \
         --runs-dir /root/irsi-workspace/runs
irsi report runs/<task-dir>
```

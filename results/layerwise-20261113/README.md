# Layerwise recompute RSI runs (2026-11-13)

Three contracts on `910b4-126` after the Qwen3 `RecomputePolicy` patch
(`patches/0001-qwen3-recompute-policy.patch`) was applied. Same model, data,
seed and 32-step workload as phase 1; only `activation_checkpoint.selection`
changes. Raw logs stay on the host; this directory keeps the reports,
decisions and per-trial metrics/configs.

## Unconstrained (`20261113T012727Z`, memory 24 GiB)

| trial | status | tps | Δ vs baseline | peak GiB |
|---|---|---|---|---|
| baseline (`full` → adapter regions) | reference | 19 543.4 | — | 3.99 |
| `control` (no-op) | discard | 18 928.9 | −3.14% (drift suspected) | 3.99 |
| `layers-0` | **keep** | **26 244.9** | **+34.29%** | 9.06 |
| `layers-6` | discard | 22 866.1 | +16.99% | 7.68 |
| `layers-12` | discard | 22 322.4 | +14.22% | 6.29 |
| `layers-18` | discard | 20 985.4 | +7.38% | 4.89 |

## 6 GiB budget (`20261113T013442Z`)

| trial | status | tps | Δ vs baseline | peak GiB |
|---|---|---|---|---|
| baseline | reference | 19 485.4 | — | 3.99 |
| `control` | discard | 19 850.4 | +1.87% | 3.99 |
| `layers-12` | **crash** (memory) | 21 609.1 | +10.90% | 6.29 > 6.00 |
| `layers-14` | **keep** | **21 315.5** | **+9.39%** | 5.83 |
| `layers-16` | discard | 21 775.6 | +11.75% | 5.36 |
| `layers-20` | discard | 19 676.7 | +0.98% | 4.40 |

`layers-16` measured above the kept point but only by 2.16%, inside the 3% noise
band, so the engine did not replace `layers-14`.

## 8 GiB budget (`20261113T014430Z`)

| trial | status | tps | Δ vs baseline | peak GiB |
|---|---|---|---|---|
| baseline | reference | 19 626.7 | — | 3.99 |
| `control` | discard | 19 410.3 | −1.10% | 3.99 |
| `layers-4` | **crash** (memory) | 23 466.7 | +19.57% | 8.14 > 8.00 |
| `layers-6` | **keep** | **25 129.3** | **+28.04%** | 7.68 |
| `layers-8` | discard | 23 994.9 | +22.25% | 7.21 |
| `layers-10` | discard | 21 021.1 | +7.10% | 6.75 |

All 18 trials (baselines included) kept the same loss/grad_norm fingerprint
`48f4302f…`; every non-memory gate passed.

## A/B: policy changes what `full` means

Back-to-back runs of the same 32-step config, differing only in whether the
`recompute=` registration is present:

| path | mechanism | tps | peak GiB |
|---|---|---|---|
| no policy, `mode=full` | HF native gradient checkpointing | 21 099.5 | 4.01 |
| policy installed, `mode=full` | explicit `CheckpointWrapper` per layer | 18 461.6 | 3.99 |

Same fingerprint. With a policy, `full` auto-upgrades to adapter regions, which
costs ~7–13% step time. The three contract baselines (19 485–19 627) all sit
below the native path, matching this attribution. Compare layerwise gains
against the same-run baseline; against the native block-level baseline, `layers-0`
is +24.4%, `layers-6` +8.4%…+19.1% (two runs), `layers-14` +1.0%.

Cross-run spread on a candidate is larger than the 3% noise band: `layers-6`
measured 22 866 (unconstrained run) and 25 129 (8 GiB run). Baseline tps stayed
stable across the three runs, so treat the exact ladder shape as provisional.

## Files

```
<contract>/report.md|json      final report and decisions
<contract>/decisions/*.json    per-candidate gates, overrides, metric
<contract>/trials/*/metrics.json|train.yaml
ab/ab_blockfull.log            native full checkpointing, no policy
ab/ab_adapterfull.log          adapter-region full, policy installed
```

## Reproduce

```bash
# on the run host, with the patch applied to /root/hyper-parallel
irsi run --contract /root/infra-rsi/contracts/medium-qwen3-layerwise.yaml \
         --runs-dir /root/irsi-workspace/runs
irsi run --contract /root/infra-rsi/contracts/medium-qwen3-layerwise-6gib.yaml --runs-dir /root/irsi-workspace/runs
irsi run --contract /root/infra-rsi/contracts/medium-qwen3-layerwise-8gib.yaml --runs-dir /root/irsi-workspace/runs
```

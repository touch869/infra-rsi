# Qwen3-0.6B parallel-strategy evidence (910b4-126, 2026-11-18)

One host, one contract, one round.

| candidate | tp | dp_shard | tps | peak GiB | vs baseline | status |
|---|---:|---:|---:|---:|---:|---|
| observed baseline | 1 | 8 | 15407.05 | 4.89 | — | calibrated |
| `dp1` | 1 | 1 | 17348.45 | 11.38 | **+12.60%** | **keep** |
| `dp2` | 1 | 2 | 15907.9 | 7.81 | +3.25% | discard |
| `dp4` | 1 | 4 | 16112.65 | 5.89 | +4.58% | discard |
| `tp2-dp4` | 2 | 4 | 7542.16 | 4.67 | -51.05% | discard |
| `tp2-dp2` | 2 | 2 | 7667.68 | 6.29 | -50.24% | crash |
| `tp2-dp1` | 2 | 1 | 8546.075 | 9.06 | -44.52% | crash |
| `tp4-dp2` | 4 | 2 | 3992.965 | 3.21 | -74.08% | crash |
| `tp8-dp1` | 8 | 1 | 2460.85 | 2.39 | -84.03% | crash |
| `control` | 1 | 8 | 16288.9 | 4.89 | +5.72% | discard |

`parallel-engagement` passes for all candidates. `numeric-parity` compares loss within `rtol=0.05`, `atol=1e-4`; TP candidates `tp2-dp1`, `tp2-dp2`, `tp4-dp2`, `tp8-dp1` crash on loss divergence, while `tp2-dp4` passes loss parity but is much slower.

The observation patch is empty, so clean vs observed baseline difference is run noise. The control's +5.72% is also drift, not an improvement.

Write-up: `docs/qwen3-0.6b-parallel-result.md`.

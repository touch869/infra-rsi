# Qwen3-0.6B phase-1 evidence (2026-11-17)

Two hosts, two contracts, one round each.

| dir | host | contract | reference baseline | best | gain |
|---|---|---|---:|---|---:|
| `126-recompute` | 910b4-126 | `qwen3-0.6b-recompute` | 17160.25 | `off` 21054.50 | +22.69% |
| `126-layerwise` | 910b4-126 | `qwen3-0.6b-layerwise` | 15966.00 | `layers-0` 21566.85 | +35.08% |
| `114-recompute` | 910b4-114 | `qwen3-0.6b-recompute` | 16109.65 | `off` 20871.40 | +29.56% |
| `114-layerwise` | 910b4-114 | `qwen3-0.6b-layerwise` | 16410.60 | `layers-0` 23140.50 | +41.01% |

All candidates share the same numeric fingerprint `065d26c10495d2efc23850f262d239d220548d7a50bf7611ebc9a508231262a6`; receipt/bitwise/memory gates pass. The observation patch is empty, so clean baseline and observed baseline are repeated measurements of the same configuration; their difference is run noise, not observation overhead. The reference baseline is the observed baseline.

Each directory contains the full run artifacts: `report.md`, `report.json`, `records.jsonl`, `calibration.json`, `environment_report.json`, `state.json`, `step_reports/`, `trials/*/metrics.json`, `train.yaml`, `run.log`, and `git-log.txt` (commit history). Raw logs stay in the run dirs; the exported copies are under `results/qwen3-06b-20261117/`.

Write-up: `docs/qwen3-0.6b-result.md`.

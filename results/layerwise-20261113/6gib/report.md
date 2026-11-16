# medium-qwen3-layerwise-6gib · recompute-layerwise

- metric: `performance/tokens_per_second` (maximize, noise 3%)
- baseline: 19485.4 (peak 3.99 GiB)
- best: h03-layers-14 = 21315.5 (peak 5.83 GiB), gain +9.39%
- control drift: +1.87% (within noise), gain vs control +7.38%, robust=True

| trial | status | metric | delta vs best | detail |
|---|---|---|---|---|
| h01-control | discard | 19850.4 | +1.87% | 19850.4 does not beat 19485.4 beyond noise |
| h02-layers-12 | crash | 21609 | +10.90% | memory: peak 6.29 GiB > limit 6.00 GiB |
| h03-layers-14 | keep | 21315.5 | +9.39% | 21315.5 beats 19485.4 beyond noise |
| h04-layers-16 | discard | 21775.6 | +2.16% | 21775.6 does not beat 21315.5 beyond noise |
| h05-layers-20 | discard | 19676.7 | -7.69% | 19676.7 does not beat 21315.5 beyond noise |

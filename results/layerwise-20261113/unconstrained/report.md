# medium-qwen3-layerwise · recompute-layerwise

- metric: `performance/tokens_per_second` (maximize, noise 3%)
- baseline: 19543.3 (peak 3.99 GiB)
- best: h02-layers-0 = 26244.9 (peak 9.06 GiB), gain +34.29%
- control drift: -3.14% (suspected), gain vs control +38.65%, robust=True

| trial | status | metric | delta vs best | detail |
|---|---|---|---|---|
| h01-control | discard | 18928.8 | -3.14% | 18928.8 does not beat 19543.3 beyond noise |
| h02-layers-0 | keep | 26244.9 | +34.29% | 26244.9 beats 19543.3 beyond noise |
| h03-layers-6 | discard | 22866.1 | -12.87% | 22866.1 does not beat 26244.9 beyond noise |
| h04-layers-12 | discard | 22322.3 | -14.95% | 22322.3 does not beat 26244.9 beyond noise |
| h05-layers-18 | discard | 20985.4 | -20.04% | 20985.4 does not beat 26244.9 beyond noise |

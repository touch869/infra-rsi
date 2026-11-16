# medium-qwen3-layerwise-8gib · recompute-layerwise

- metric: `performance/tokens_per_second` (maximize, noise 3%)
- baseline: 19626.7 (peak 3.99 GiB)
- best: h03-layers-6 = 25129.2 (peak 7.68 GiB), gain +28.04%
- control drift: -1.10% (within noise), gain vs control +29.46%, robust=True

| trial | status | metric | delta vs best | detail |
|---|---|---|---|---|
| h01-control | discard | 19410.3 | -1.10% | 19410.3 does not beat 19626.7 beyond noise |
| h02-layers-4 | crash | 23466.7 | +19.57% | memory: peak 8.14 GiB > limit 8.00 GiB |
| h03-layers-6 | keep | 25129.2 | +28.04% | 25129.2 beats 19626.7 beyond noise |
| h04-layers-8 | discard | 23994.9 | -4.51% | 23994.9 does not beat 25129.2 beyond noise |
| h05-layers-10 | discard | 21021.1 | -16.35% | 21021.1 does not beat 25129.2 beyond noise |

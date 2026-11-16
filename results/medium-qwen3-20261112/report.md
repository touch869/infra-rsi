# medium-qwen3-recompute · recompute

- metric: `performance/tokens_per_second` (maximize, noise 3%)
- baseline: 21416.4 (peak 4.01 GiB)
- best: h01-off = 25834.9 (peak 9.06 GiB), gain +20.63%
- control drift: +4.19% (suspected), gain vs control +15.78%, robust=True

| trial | status | metric | delta vs best | detail |
|---|---|---|---|---|
| h01-off | keep | 25834.9 | +20.63% | 25834.9 beats 21416.4 beyond noise |
| h02-control | discard | 22314 | -13.63% | 22314 does not beat 25834.9 beyond noise |
| h03-selective | discard | 14616 | -43.43% | 14616 does not beat 25834.9 beyond noise |
| h04-selective-swap | discard | 13938.1 | -46.05% | 13938.1 does not beat 25834.9 beyond noise |

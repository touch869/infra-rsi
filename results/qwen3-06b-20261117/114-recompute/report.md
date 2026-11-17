# round round-1

- reference baseline: 16109.7
- best: off = 20871.4
- counts: {'baseline': 2, 'calibrated': 1, 'discard': 3, 'keep': 1}

| step | stage | hypothesis | status | metric | detail |
|---|---|---|---|---|---|
| round-1-0000 | clean_baseline | - | baseline | 16909.9 | clean baseline (observation off) |
| round-1-0001 | observed_baseline | - | baseline | 16109.7 | observed baseline (observation on) |
| round-1-0002 | calibrated | - | calibrated | 16109.7 | reference = observed baseline |
| round-1-0003 | judgment | full-swap | discard | 15736.5 | 15736.5 does not beat 16109.7 beyond noise |
| round-1-0004 | judgment | off | keep | 20871.4 | 20871.4 beats 16109.7 beyond noise |
| round-1-0005 | judgment | selective | discard | 12621 | 12621 does not beat 20871.4 beyond noise |
| round-1-0006 | judgment | selective-swap | discard | 11993.2 | 11993.2 does not beat 20871.4 beyond noise |

# round round-1

- reference baseline: 17160.2
- best: off = 21054.5
- counts: {'baseline': 2, 'calibrated': 1, 'discard': 3, 'keep': 1}

| step | stage | hypothesis | status | metric | detail |
|---|---|---|---|---|---|
| round-1-0000 | clean_baseline | - | baseline | 16847 | clean baseline (observation off) |
| round-1-0001 | observed_baseline | - | baseline | 17160.2 | observed baseline (observation on) |
| round-1-0002 | calibrated | - | calibrated | 17160.2 | reference = observed baseline |
| round-1-0003 | judgment | full-swap | discard | 15617 | 15617 does not beat 17160.2 beyond noise |
| round-1-0004 | judgment | off | keep | 21054.5 | 21054.5 beats 17160.2 beyond noise |
| round-1-0005 | judgment | selective | discard | 11849.8 | 11849.8 does not beat 21054.5 beyond noise |
| round-1-0006 | judgment | selective-swap | discard | 11874.9 | 11874.9 does not beat 21054.5 beyond noise |

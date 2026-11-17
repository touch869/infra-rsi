# round round-1

- reference baseline: 15966
- best: layers-0 = 21566.8
- counts: {'baseline': 2, 'calibrated': 1, 'keep': 1, 'discard': 4}

| step | stage | hypothesis | status | metric | detail |
|---|---|---|---|---|---|
| round-1-0000 | clean_baseline | - | baseline | 16268 | clean baseline (observation off) |
| round-1-0001 | observed_baseline | - | baseline | 15966 | observed baseline (observation on) |
| round-1-0002 | calibrated | - | calibrated | 15966 | reference = observed baseline |
| round-1-0003 | judgment | layers-0 | keep | 21566.8 | 21566.8 beats 15966 beyond noise |
| round-1-0004 | judgment | layers-12 | discard | 19281.5 | 19281.5 does not beat 21566.8 beyond noise |
| round-1-0005 | judgment | layers-18 | discard | 17104 | 17104 does not beat 21566.8 beyond noise |
| round-1-0006 | judgment | layers-6 | discard | 19442.4 | 19442.4 does not beat 21566.8 beyond noise |
| round-1-0007 | judgment | control | discard | 16458 | 16458 does not beat 21566.8 beyond noise |

# round round-1

- reference baseline: 16410.6
- best: layers-0 = 23140.5
- counts: {'baseline': 2, 'calibrated': 1, 'keep': 1, 'discard': 4}

| step | stage | hypothesis | status | metric | detail |
|---|---|---|---|---|---|
| round-1-0000 | clean_baseline | - | baseline | 15795.7 | clean baseline (observation off) |
| round-1-0001 | observed_baseline | - | baseline | 16410.6 | observed baseline (observation on) |
| round-1-0002 | calibrated | - | calibrated | 16410.6 | reference = observed baseline |
| round-1-0003 | judgment | layers-0 | keep | 23140.5 | 23140.5 beats 16410.6 beyond noise |
| round-1-0004 | judgment | layers-12 | discard | 19497.2 | 19497.2 does not beat 23140.5 beyond noise |
| round-1-0005 | judgment | layers-18 | discard | 18421.1 | 18421.1 does not beat 23140.5 beyond noise |
| round-1-0006 | judgment | layers-6 | discard | 20917.8 | 20917.8 does not beat 23140.5 beyond noise |
| round-1-0007 | judgment | control | discard | 16160.9 | 16160.9 does not beat 23140.5 beyond noise |

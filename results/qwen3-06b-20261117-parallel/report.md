# round round-1

- reference baseline: 15407
- best: dp1 = 17348.4
- counts: {'baseline': 2, 'calibrated': 1, 'keep': 1, 'discard': 4, 'crash': 4}

| step | stage | hypothesis | status | metric | detail |
|---|---|---|---|---|---|
| round-1-0000 | clean_baseline | - | baseline | 16665.5 | clean baseline (observation off) |
| round-1-0001 | observed_baseline | - | baseline | 15407 | observed baseline (observation on) |
| round-1-0002 | calibrated | - | calibrated | 15407 | reference = observed baseline |
| round-1-0003 | judgment | dp1 | keep | 17348.4 | 17348.4 beats 15407 beyond noise |
| round-1-0004 | judgment | dp2 | discard | 15907.9 | 15907.9 does not beat 17348.4 beyond noise |
| round-1-0005 | judgment | dp4 | discard | 16112.7 | 16112.7 does not beat 17348.4 beyond noise |
| round-1-0006 | judgment | tp2-dp1 | crash | 8546.08 | numeric-parity: first divergence at step 32: loss 10.508 -> 11.1497 (|delta|=0.6417 > 0.5255) |
| round-1-0007 | judgment | tp2-dp2 | crash | 7667.68 | numeric-parity: first divergence at step 25: loss 10.6008 -> 11.1592 (|delta|=0.5584 > 0.53014) |
| round-1-0008 | judgment | tp2-dp4 | discard | 7542.16 | 7542.16 does not beat 17348.4 beyond noise |
| round-1-0009 | judgment | tp4-dp2 | crash | 3992.97 | numeric-parity: first divergence at step 16: loss 11.2647 -> 11.8309 (|delta|=0.5662 > 0.563335) |
| round-1-0010 | judgment | tp8-dp1 | crash | 2460.85 | numeric-parity: first divergence at step 16: loss 11.2647 -> 11.8916 (|delta|=0.6269 > 0.563335) |
| round-1-0011 | judgment | control | discard | 16288.9 | 16288.9 does not beat 17348.4 beyond noise |

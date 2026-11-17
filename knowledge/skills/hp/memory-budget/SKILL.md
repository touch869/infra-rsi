# Peak device memory and budget gate

## Measured bands

On medium Qwen3 with 8x910B4:

- `full` ~4.01 GiB
- `selective` ~4.88 GiB
- `off` ~9.06 GiB

These bands are evidence for engaged-path checks, not universal constants.

## Gate rule

- `peak_mem_gib` comes from `memory/device_max_allocated_gb`.
- `memory_budget_gib` is the contract limit.
- If peak memory is missing, the gate fails.
- If peak memory exceeds the limit, the trial is a crash; its metric is not recorded.

## Use in development

Layerwise candidates trade memory for step time. A higher `layer_count` can reduce peak memory but may be slower. Choose layer counts that fit the contract's budget, then verify with the memory gate.

## Caveat

Memory budget is a hard gate, not a noise-band metric. Do not accept an OOM or over-budget trial just because its tokens/s is higher.

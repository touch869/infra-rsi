# Parallel-strategy frontier

## What changes

- TP splits attention heads and hidden states across ranks, adding
  all-gather/reduce-scatter communication.
- FSDP `dp_shard_size` changes how parameters are sharded versus replicated.
- Both change per-rank memory and communication, but not the global workload.

## Measurement

- Use `performance/tokens_per_second` from the whole run, not a per-rank rate.
- Keep `global_batch_size`, `micro_batch_size`, seed, data, optimizer and
  `activation_checkpoint.mode` fixed.
- Use the same warmup and measured window as the observed baseline.
- The no-op control is a drift check, not a candidate win.

## Expected shape

For a small model on 8x910B4:

- TP reduces per-rank weight and activation memory.
- TP communication can dominate when the model is small and the batch is short.
- Smaller `dp_shard_size` (more replication) can raise per-rank memory and
  reduce FSDP communication; it is a separate frontier point.
- The best point is the one with the highest stable throughput that also passes
  the memory and numeric gates, not simply the lowest memory.

## Reporting

Report per-candidate `tps`, `peak_mem_gib`, and gain versus the observed baseline.
Do not compare candidates across different contracts or activation modes.

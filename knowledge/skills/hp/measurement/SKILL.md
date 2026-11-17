# Training metric extraction and steady windows

## Metric keys

- `performance/tokens_per_second` - primary throughput metric.
- `performance/step_time` - per-step time.
- `memory/device_max_allocated_gb` - peak device memory.
- `training/foundation_loss` / `training/total_loss` - loss.
- `training/grad_norm` - gradient norm for numeric fingerprint.

## Window

- `warmup_steps` are excluded from the steady value.
- `measured_steps` take the last N values after warmup.
- The steady value is the median; even counts average the two middle values.
- `noise_fraction` defines the improvement band. A candidate must beat the reference beyond the band.
- A no-op control measures drift; it is not an improvement candidate.

## Receipt context

- `workload.expect_steps` is the expected completed step count.
- `exit_code`, `timed_out`, `traceback`, and `completed_steps` are receipt evidence.
- Same-config cross-run variation can be large in real training; do not treat a small in-band change as a win.

## Caveats

- `tokens/s` is the phase-1 metric; MFU/HFU are optional analysis, not the primary contract metric.
- Measurement windows must be identical for baseline and candidates.

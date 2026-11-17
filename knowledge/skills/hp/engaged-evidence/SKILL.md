# Positive evidence that the configured path is engaged

## Definition

A trial is engaged only when the requested configuration actually took effect. A fallback run and an optimized run can look indistinguishable in ordinary logs.

## Evidence sources

1. Resolved config dump
   - The dump must contain the requested mode exactly.
   - Example: request `off`, dump must show `"mode": "off"`.

2. Peak memory band
   - `full` ~4.0 GiB
   - `selective` ~4.9 GiB
   - `off` ~9.1 GiB
   - If the dump says `off` but peak memory is still near 4 GiB, the path did not engage.

## Receipt protocol

PR1517 uses a training receipt with fields such as:

```text
phase, status, completed_steps, engaged, first_error_step
```

Failure classes include `oom`, `numerical_mismatch`, `incomplete`, `contention`, and `futile`. A missing engaged marker is reported as `path_not_engaged`.

## Failure behavior

- Engaged evidence missing: crash.
- No benchmark metric should be recorded.
- A normal-looking run is not evidence of engagement.

## Use by stage

- Observation: collect the dump and memory fields.
- Execution: preserve logs and config.
- Judgment: gate on engaged evidence.
- Archive: report the engaged verdict alongside the metric.

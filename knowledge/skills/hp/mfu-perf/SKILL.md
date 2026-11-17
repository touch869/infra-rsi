# MFU and HFU performance analysis

## Definitions

- MFU: model FLOPs utilization.
- HFU: hardware FLOPs utilization.
- Both need model FLOPs, effective tokens/s, and device peak performance.

## Use in phase 1

`performance/tokens_per_second` is the primary contract metric. MFU/HFU are optional analysis for explaining whether a throughput gain is real or just a measurement artifact.

## Caveats

- MFU does not replace the bitwise numeric gate.
- MFU depends on model shape, hardware peak, and parallel topology; do not compare across different workloads.
- Report MFU only when the workload identity and measurement window are fixed.

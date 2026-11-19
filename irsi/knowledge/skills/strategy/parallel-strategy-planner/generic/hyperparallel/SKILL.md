---
name: parallel-strategy-planner
version: 1
description: >
  Recommend DP/FSDP/TP/PP/EP/CP strategy mixes from model + hardware constraints,
  with memory/comm/compute/bubble estimates. Use for strategy planning, scale-out,
  OOM, or comparing configs. Not for implementing platform or operator code, or running training jobs.
category: "strategy"
environment: "generic"
framework: "hyperparallel"
inputs:
  - "model architecture"
  - "hardware topology"
  - "memory and communication constraints"
outputs:
  - "candidate DP, FSDP, TP, PP, EP and CP strategies"
  - "memory, communication, compute and bubble estimates"
next:
  - "strategy-validator"
  - "strategy-optimizer"
  - "hf-model-integration"
---

# Parallel Strategy Planner

**Single source of truth** for the formulas and decision trees in this skill.

> **Applicability.** The strategy and memory rules cover Ascend A2/A3/950DT
> and NVIDIA A100/H100/H200. The generated DeviceMesh example assumes the
> HyperParallel API; another training framework needs a sibling variant.

## When to use

- Choose or rescale parallel strategies; debug OOM; compare configs; estimate comm/bubble

Inputs / examples / full output shape / limits:
[references/io-contract.md](references/io-contract.md).

## Analysis flow (load workflow before each phase)

```text
1 Collect info     → workflows/01-collect-model-info.md
2 Global baseline  → workflows/02-global-baseline.md   (memory + FLOPs, no parallel)
3 Strategy search  → workflows/03-strategy-search.md
4 Cost analysis    → workflows/04-cost-analysis.md     (TP/CP/EP/DP + PP bubble)
5–7 Shard mem / MFU / score + report → workflows/05-scoring-output.md
```

Do **Phase 2 before** cost/memory-after-shard so “fits in memory” is not preferred
over strategies with prohibitive communication.

## Tables & formulas (on demand)

- [references/known-models.md](references/known-models.md)
- [references/known-hardware.md](references/known-hardware.md)
- [references/memory-estimation.md](references/memory-estimation.md)
- [references/strategy-rules.md](references/strategy-rules.md)
- [references/moe-strategy-rules.md](references/moe-strategy-rules.md) — **MoE-specific** (load when `is_moe=True`)

## Output (short)

Emit: baseline → recommendation + DeviceMesh code → post-shard mem → comm →
bubble → opts → top-3 alternatives. Details in `io-contract.md`.

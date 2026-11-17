# Per-layer recompute via model adapter safe regions

## When to use

Use this skill when a contract exposes `activation_checkpoint.selection.layer_count` and the model adapter declares a recompute policy.

## Mechanism

- `activation_checkpoint.selection.source = model_adapter_safe_regions`
- `activation_checkpoint.selection.layer_count = k` selects the contiguous prefix `[0, k)` of discovered decoder layers.
- `k = 0` keeps every activation resident; `k = N` replays every layer.
- Intermediate `k` trades memory for step time.

## Qwen3 prerequisite

Qwen3 dense needs `ModelAdapterSpec.recompute` declared by the patch:

```text
patches/0001-qwen3-recompute-policy.patch
```

Without that policy, the layer dimension is closed and layerwise candidates fail at launch. Do not silently guess safe regions.

## Evidence

The 2026-11-13 layerwise run found:

- `layers-0`: +34.29% versus the same-run baseline
- `layers-6`: +28.04% at 8 GiB
- `layers-14`: +9.39% at 6 GiB
- all numerics bitwise identical

Note: installing the patch makes `mode=full` use the adapter-region wrapper path, about 7-13% slower than HF native checkpointing.

## Constraints

- `domain_params.layer_counts` must be a non-empty list of non-negative integers.
- Layer count must respect the memory budget; higher `k` reduces memory but can slow the trial.
- The candidate is still a recompute candidate; do not invent layers outside the adapter's safe regions.

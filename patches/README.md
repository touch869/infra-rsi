# HyperParallel patches

Patches the run harness applies to the HyperParallel checkout (`repo_root` in the
contracts, `/root/hyper-parallel` on the run host) before a contract runs.

## `0001-qwen3-recompute-policy.patch`

Declares `ModelAdapterSpec.recompute` for Qwen3 dense. Without it,
`activation_checkpoint.selection.source=model_adapter_safe_regions` raises
`ValueError` and `layer_count` / `layer_indices` are unusable (only
DeepSeek-V4.1 declared a policy upstream). With it, selected decoder layers can
be recomputed independently.

Base: `hyper-parallel` master @ `befd6c07` (2026-11-13).

```bash
git -C ../hyper-parallel checkout -b qwen3-recompute-policy
git -C ../hyper-parallel am /path/to/0001-qwen3-recompute-policy.patch
```

On a non-git checkout (the run host is an rsync copy), copy the patched files
directly and run the patch's unit test:

```bash
PYTHONPATH=/root/hyper-parallel python \
  tests/ut/auto_models/models/qwen3/test_recompute_policy.py -v
```

Side effect to keep in mind: once a policy exists, `mode=full` with the default
selection auto-upgrades to the adapter regions (`layer_count=all layers`), so
full-recompute baselines change behavior and must be re-measured.

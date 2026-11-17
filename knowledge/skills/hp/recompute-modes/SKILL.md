# HyperParallel activation recompute modes

## When to use

Use this skill when selecting or explaining an `activation_checkpoint.mode` candidate.

## Modes

- `off`: keep activations resident; no recompute. Highest memory, usually fastest.
- `full`: recompute all activations. Lowest memory, highest recompute overhead.
- `selective`: recompute selected regions only. Memory between `full` and `off`; usually slower than `off`.
- `swap_inputs`: swap input activations to reduce memory; can change performance and must be evaluated as its own candidate.

## Phase-1 measured facts

On medium Qwen3 with 8x910B4, the reproduction observed:

| mode | peak memory | tokens/s |
|---|---|---|
| full | ~4.01 GiB | ~21.5k |
| selective | ~4.88 GiB | ~14.7k |
| off | ~9.06 GiB | ~25.5k |

`off` was +16.6% versus `full`; the independent infra-rsi run measured +20.6%. `selective` is not a default win when memory is already sufficient.

## Constraints

- Only keys under `activation_checkpoint.*` may be changed.
- `activation_checkpoint.allow_cache_entry_mutation` is read-only in the phase-1 contract.
- The no-op control is a drift check, not an optimization candidate.
- If the Qwen3 recompute-policy patch is installed, `mode=full` can take the adapter-region wrapper path and be slower than HF native checkpointing.

## Decision guidance

- If the memory budget allows it, `off` is the strongest phase-1 hypothesis.
- `selective` is an exploration candidate, not an assumed improvement.
- Always verify the mode was actually engaged; do not trust the requested config alone.

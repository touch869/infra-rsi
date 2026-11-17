# HyperParallel tensor-parallel topology

## Keys

- `accelerator.tp_size`, `cp_size`, `ep_size`, `pp_size`
- `accelerator.sequence_parallel`, `accelerator.loss_parallel`
- `fsdp_config.dp_shard_size`

## Mesh equations

```text
dense_world = dp_size * cp_size * tp_size * pp_size
nproc       = dense_world * pp_size
dp_size     = nproc / (tp_size * cp_size * pp_size)
dp_shard_size must divide dp_size
dp_replicate_size = dp_size / dp_shard_size
```

The runtime log must show:

```text
Built device mesh (dp, cp, tp), dense FSDP mesh (replicate, shard, tp)
```

## Tensor parallel

- TP splits attention heads and the hidden dimension.
- The vocabulary output is sharded, so `loss_parallel=true` is required for
  language-model loss. TP without `loss_parallel` fails at the loss shape.
- `tp_size` must divide `num_attention_heads`; for GQA it must also divide
  `num_key_value_heads`. Qwen3-0.6B has 16 heads and 8 KV heads, so TP can be
  1, 2, 4, or 8.

## Sequence parallel

- `sequence_parallel` shards the sequence dimension, not the hidden dimension.
- It is a separate feature. In the packed-text workload used here the labels
  are not sequence-sharded, so enabling it makes the loss input shape mismatch.
- Do not treat TP and SP as interchangeable candidates.

## FSDP shard size

- `dp_shard_size = dp_size` means one FSDP shard per data-parallel rank.
- Smaller `dp_shard_size` replicates parameters across `dp_replicate_size`
  groups. This can reduce FSDP communication but raises per-rank memory.
- The memory gate, not the requested config, decides whether the topology fits.

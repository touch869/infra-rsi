"""Parallel-strategy edit surface: tensor parallel and FSDP shard topology.

The candidates change only ``accelerator.*`` and ``fsdp_config.dp_shard_size``.
The contract must list those keys as writable and keep the workload, model,
optimizer, data and activation-checkpoint settings read-only so the comparison
isolates parallelism. Tensor parallel shards the vocabulary output, so the
loss must run in ``loss_parallel`` mode; without it the language-model loss
cannot match the full-vocabulary labels.

``sequence_parallel`` is a separate feature, not the same as tensor parallel.
In the packed-text workload used here the batch labels are not sequence-sharded,
so enabling it would make the loss input shape mismatch; the surface refuses it
unless the contract explicitly declares ``allow_sequence_parallel``.
"""

from __future__ import annotations

from typing import Any, List, Mapping

from ..task_spec import InfraTaskSpec
from ...registry import SURFACES
from .base import Hypothesis

__all__ = ["parallel_candidates"]


def _as_int(value: Any, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _as_bool(value: Any, name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a bool, got {value!r}")
    return value


@SURFACES.register("parallel")
def parallel_candidates(spec: InfraTaskSpec) -> List[Hypothesis]:
    """Emit a contract-declared tensor-parallel / FSDP shard ladder.

    ``domain_params.parallel_ladder`` is a list of mappings with ``id``,
    ``tp_size``, ``dp_shard_size`` and optional ``loss_parallel`` /
    ``sequence_parallel``. The surface validates the topology against
    ``workload.nproc`` and, when provided, against the model's head counts.

    The no-op control is always emitted; it is a drift check, not a candidate
    improvement.
    """
    raw = spec.domain_params.get("parallel_ladder", ())
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("domain_params.parallel_ladder must be a non-empty list")

    nproc = spec.workload.nproc
    allow_sequence_parallel = bool(spec.domain_params.get("allow_sequence_parallel", False))
    heads = spec.domain_params.get("num_attention_heads")
    kv_heads = spec.domain_params.get("num_key_value_heads")

    candidates: List[Hypothesis] = [
        Hypothesis(
            id="control",
            description="no-op control (baseline topology re-run for drift)",
            overrides={},
        )
    ]

    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("each parallel_ladder entry must be a mapping")
        tp = _as_int(item.get("tp_size"), "tp_size")
        dp_shard = _as_int(item.get("dp_shard_size"), "dp_shard_size")
        cp = _as_int(item.get("cp_size", 1), "cp_size")
        pp = _as_int(item.get("pp_size", 1), "pp_size")
        loss_parallel = _as_bool(item.get("loss_parallel"), "loss_parallel", tp > 1)
        sequence_parallel = _as_bool(
            item.get("sequence_parallel"), "sequence_parallel", False
        )

        if sequence_parallel and not allow_sequence_parallel:
            raise ValueError(
                "sequence_parallel is not enabled by this contract; the packed-text "
                "loss labels are not sequence-sharded"
            )
        if tp > 1 and not loss_parallel:
            raise ValueError(
                f"tensor parallel tp_size={tp} requires loss_parallel=true"
            )
        if heads is not None and tp > 1:
            heads_int = _as_int(heads, "num_attention_heads")
            if heads_int % tp != 0:
                raise ValueError(
                    f"tp_size={tp} must divide num_attention_heads={heads_int}"
                )
        if kv_heads is not None and tp > 1:
            kv_int = _as_int(kv_heads, "num_key_value_heads")
            if kv_int % tp != 0:
                raise ValueError(
                    f"tp_size={tp} must divide num_key_value_heads={kv_int}"
                )

        dense_world = nproc // pp
        if dense_world % (tp * cp) != 0:
            raise ValueError(
                f"nproc={nproc} must be divisible by tp*cp*pp={tp * cp * pp}"
            )
        dp_size = dense_world // (tp * cp)
        if dp_size % dp_shard != 0:
            raise ValueError(
                f"dp_shard_size={dp_shard} must divide dp_size={dp_size}"
            )

        candidate_id = str(item.get("id") or f"tp{tp}-dp{dp_shard}")
        if candidate_id in seen:
            raise ValueError(f"duplicate parallel candidate id: {candidate_id!r}")
        seen.add(candidate_id)

        candidates.append(
            Hypothesis(
                id=candidate_id,
                description=str(
                    item.get(
                        "description",
                        f"tensor parallel tp={tp}, FSDP dp_shard={dp_shard}",
                    )
                ),
                overrides={
                    "accelerator.tp_size": tp,
                    "accelerator.cp_size": cp,
                    "accelerator.ep_size": 1,
                    "accelerator.pp_size": pp,
                    "accelerator.sequence_parallel": sequence_parallel,
                    "accelerator.loss_parallel": loss_parallel,
                    "fsdp_config.dp_shard_size": dp_shard,
                },
            )
        )

    return candidates

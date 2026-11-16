"""Recompute edit surface: activation-checkpoint modes and their variants.

Every candidate here changes only ``activation_checkpoint.*`` keys, which the
contract must list in ``writable_prefixes``. Recompute replays the forward
pass, so a correct implementation is numerically identical to the baseline and
the bitwise gate stays the primary correctness check.
"""

from __future__ import annotations

from typing import List

from ..task_spec import InfraTaskSpec
from ...registry import SURFACES
from .base import Hypothesis

__all__ = ["recompute_candidates", "recompute_layerwise_candidates"]


@SURFACES.register("recompute")
def recompute_candidates(spec: InfraTaskSpec) -> List[Hypothesis]:
    """Return the phase-1 recompute candidate list, cheapest win first."""
    del spec  # the surface is fixed for phase 1; kept for plugin symmetry
    return [
        Hypothesis(
            id="off",
            description="disable activation recompute (baseline is full)",
            overrides={"activation_checkpoint.mode": "off"},
        ),
        Hypothesis(
            id="control",
            description="no-op control (should be discarded inside the noise band)",
            overrides={},
        ),
        Hypothesis(
            id="selective",
            description="selective activation checkpointing instead of full",
            overrides={"activation_checkpoint.mode": "selective"},
        ),
        Hypothesis(
            id="selective-swap",
            description="selective checkpointing with activation input swap",
            overrides={
                "activation_checkpoint.mode": "selective",
                "activation_checkpoint.swap_inputs": True,
            },
        ),
        Hypothesis(
            id="full-swap",
            description="full checkpointing with activation input swap",
            overrides={
                "activation_checkpoint.mode": "full",
                "activation_checkpoint.swap_inputs": True,
            },
        ),
    ]


@SURFACES.register("recompute-layerwise")
def recompute_layerwise_candidates(spec: InfraTaskSpec) -> List[Hypothesis]:
    """Return per-layer recompute candidates for models with a recompute policy.

    ``layer_count=k`` selects the contiguous prefix ``[0, k)`` of the discovered
    decoder layers through HyperParallel's ``model_adapter_safe_regions``
    source: ``k=0`` keeps every activation resident, ``k=N`` replays every
    layer, and values in between trade memory for step time. The source
    requires the model adapter to declare a ``RecomputePolicy``; without one
    every candidate fails at launch rather than silently guessing regions.

    The ladder comes from ``domain_params.layer_counts`` so one contract can
    probe a coarse frontier and another can bracket a memory budget.
    """
    raw = spec.domain_params.get("layer_counts", (0, 6, 12, 18))
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("domain_params.layer_counts must be a non-empty list")
    counts: List[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"layer_counts entries must be non-negative integers, got {value!r}"
            )
        if value not in counts:
            counts.append(value)
    counts.sort()

    candidates = [
        Hypothesis(
            id="control",
            description="no-op control (baseline re-run for drift)",
            overrides={},
        )
    ]
    for count in counts:
        if count == 0:
            description = "keep every activation resident (no layer recomputes)"
        else:
            description = f"recompute the first {count} decoder layers via safe regions"
        candidates.append(
            Hypothesis(
                id=f"layers-{count}",
                description=description,
                overrides={
                    "activation_checkpoint.mode": "selective",
                    "activation_checkpoint.selection.source": "model_adapter_safe_regions",
                    "activation_checkpoint.selection.layer_count": count,
                },
            )
        )
    return candidates

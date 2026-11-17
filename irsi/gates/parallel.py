"""Gates for parallel-strategy trials: topology engagement and numeric parity.

Tensor parallel changes the order of floating-point reductions, so a bitwise
hash is not the right correctness check. The parity gate compares loss and
grad_norm step-by-step against the observed baseline within a declared
relative/absolute tolerance. The engagement gate proves that the requested
topology actually reached the runtime, using the HyperParallel mesh and
ShardingPlanner log lines, not just the rendered YAML.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import yaml

from .base import GateContext, GateResult
from ..registry import GATES

__all__ = ["NumericParityGate", "ParallelEngagementGate"]


@GATES.register("parallel-engagement")
class ParallelEngagementGate:
    """The runtime must build the requested mesh and apply the requested plan."""

    name = "parallel-engagement"

    def __init__(self, require_mesh: bool = True, require_plan: bool = True) -> None:
        self._require_mesh = require_mesh
        self._require_plan = require_plan

    def check(self, ctx: GateContext) -> GateResult:
        config = self._read_config(ctx)
        accelerator = config.get("accelerator") or {}
        fsdp = config.get("fsdp_config") or {}
        tp = int(accelerator.get("tp_size", 1))
        cp = int(accelerator.get("cp_size", 1))
        pp = int(accelerator.get("pp_size", 1))
        sequence_parallel = bool(accelerator.get("sequence_parallel", False))
        loss_parallel = bool(accelerator.get("loss_parallel", False))
        dp_shard = int(fsdp.get("dp_shard_size", 1))

        world = ctx.spec.workload.nproc
        dense_world = world // pp
        if dense_world % (tp * cp) != 0:
            return GateResult(
                self.name, False, f"invalid topology: nproc={world}, tp={tp}, cp={cp}, pp={pp}"
            )
        dp_size = dense_world // (tp * cp)
        if dp_size % dp_shard != 0:
            return GateResult(
                self.name, False, f"invalid FSDP shard: dp_size={dp_size}, dp_shard={dp_shard}"
            )
        dp_replicate = dp_size // dp_shard

        expected_mesh = (
            f"Built device mesh ({dp_size}, {cp}, {tp}), "
            f"dense FSDP mesh ({dp_replicate}, {dp_shard}, {tp})"
        )
        log = Path(ctx.trial.log_path).read_text(encoding="utf-8", errors="replace")
        if self._require_mesh and expected_mesh not in log:
            return GateResult(
                self.name,
                False,
                f"requested mesh not engaged: expected {expected_mesh!r}",
            )

        expected_plan = (
            f"Running ShardingPlanner.plan(tp={tp}, cp={cp}, ep=1, "
            f"sequence_parallel={sequence_parallel}, loss_parallel={loss_parallel})"
        )
        # A tp=1 topology has no tensor-parallel sharding plan to apply.
        if self._require_plan and tp > 1 and expected_plan not in log:
            return GateResult(
                self.name,
                False,
                f"requested plan not engaged: expected {expected_plan!r}",
            )

        return GateResult(
            self.name,
            True,
            f"mesh ({dp_size}, {cp}, {tp}); FSDP ({dp_replicate}, {dp_shard}, {tp}); "
            f"sequence_parallel={sequence_parallel}, loss_parallel={loss_parallel}",
        )

    @staticmethod
    def _read_config(ctx: GateContext) -> Mapping[str, Any]:
        raw = yaml.safe_load(Path(ctx.trial.config_path).read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            return {}
        return raw


@GATES.register("numeric-parity")
class NumericParityGate:
    """Selected metrics must stay within a tolerance band of the reference.

    Use this for parallel candidates where tensor splitting changes summation
    order. For recompute or other numerically exact changes, use ``bitwise``.
    ``fields`` selects which per-step metrics are semantically compared; for
    parallel training, ``loss`` is the model-equivalence proxy and ``grad_norm``
    is diagnostic because TP/FSDP reduce and scale gradients differently.
    """

    name = "numeric-parity"

    def __init__(
        self,
        rtol: float = 1e-3,
        atol: float = 1e-6,
        fields: tuple[str, ...] = ("loss", "grad_norm"),
    ) -> None:
        if rtol < 0:
            raise ValueError("rtol must be >= 0")
        if atol < 0:
            raise ValueError("atol must be >= 0")
        valid = ("loss", "grad_norm")
        if not fields or any(field not in valid for field in fields):
            raise ValueError(f"fields must be a non-empty subset of {valid}")
        self._rtol = rtol
        self._atol = atol
        self._fields = tuple(fields)

    def check(self, ctx: GateContext) -> GateResult:
        if ctx.baseline is None:
            return GateResult(self.name, True, "baseline reference")

        baseline = ctx.baseline.metrics
        candidate = ctx.trial.metrics
        if baseline.numeric_hash == candidate.numeric_hash:
            return GateResult(self.name, True, "numeric fingerprint identical")

        if len(baseline.steps) != len(candidate.steps):
            return GateResult(
                self.name,
                False,
                f"step count differs: baseline={len(baseline.steps)}, candidate={len(candidate.steps)}",
            )

        for left, right in zip(baseline.steps, candidate.steps):
            if left.step != right.step:
                return GateResult(
                    self.name, False, f"step labels differ at {left.step} vs {right.step}"
                )
            for field in self._fields:
                base_value = getattr(left, field)
                cand_value = getattr(right, field)
                if base_value is None or cand_value is None:
                    return GateResult(
                        self.name, False, f"missing {field} at step {left.step}"
                    )
                tolerance = self._atol + self._rtol * abs(base_value)
                if not math.isclose(cand_value, base_value, rel_tol=0.0, abs_tol=tolerance):
                    return GateResult(
                        self.name,
                        False,
                        f"first divergence at step {left.step}: "
                        f"{field} {base_value!r} -> {cand_value!r} "
                        f"(|delta|={abs(cand_value - base_value):.6g} > {tolerance:.6g})",
                    )

        return GateResult(
            self.name,
            True,
            f"parity within rtol={self._rtol}, atol={self._atol}, fields={self._fields}",
        )

"""Built-in gates: receipt completeness, bitwise equivalence, memory budget."""

from __future__ import annotations

from ..registry import GATES
from .base import GateContext, GateResult

__all__ = ["BitwiseGate", "MemoryGate", "ReceiptGate"]


@GATES.register("receipt")
class ReceiptGate:
    """The trial must finish cleanly with the expected number of steps."""

    name = "receipt"

    def __init__(self, expect_steps: int | None = None) -> None:
        self._expect_steps = expect_steps

    def check(self, ctx: GateContext) -> GateResult:
        expected = self._expect_steps or ctx.spec.workload.expect_steps
        metrics = ctx.trial.metrics
        if metrics.timed_out:
            return GateResult(self.name, False, "timeout")
        if metrics.traceback:
            return GateResult(self.name, False, "traceback in log")
        if metrics.exit_code != 0:
            return GateResult(self.name, False, f"exit_code={metrics.exit_code}")
        if metrics.completed_steps < expected:
            return GateResult(
                self.name,
                False,
                f"incomplete_window: {metrics.completed_steps}/{expected} steps",
            )
        return GateResult(self.name, True, f"{metrics.completed_steps} steps")


@GATES.register("bitwise")
class BitwiseGate:
    """Loss/grad_norm must be bitwise identical to the baseline."""

    name = "bitwise"

    def check(self, ctx: GateContext) -> GateResult:
        if ctx.baseline is None:
            return GateResult(self.name, True, "baseline reference")
        baseline = ctx.baseline.metrics
        candidate = ctx.trial.metrics
        if baseline.numeric_hash == candidate.numeric_hash:
            return GateResult(self.name, True, "identical loss/grad_norm")
        detail = "numeric mismatch"
        for left, right in zip(baseline.steps, candidate.steps):
            if (left.loss, left.grad_norm) != (right.loss, right.grad_norm):
                detail = (
                    f"first divergence at step {left.step}: "
                    f"loss {left.loss!r}->{right.loss!r}, "
                    f"grad_norm {left.grad_norm!r}->{right.grad_norm!r}"
                )
                break
        return GateResult(self.name, False, detail)


@GATES.register("memory")
class MemoryGate:
    """Peak device memory must stay under the declared budget."""

    name = "memory"

    def __init__(self, limit_gib: float | None = None) -> None:
        self._limit_gib = limit_gib

    def check(self, ctx: GateContext) -> GateResult:
        limit = self._limit_gib or ctx.spec.memory_budget_gib
        peak = ctx.trial.metrics.peak_mem_gib
        if peak is None:
            return GateResult(self.name, False, "no memory metric in log")
        if peak > limit:
            return GateResult(self.name, False, f"peak {peak:.2f} GiB > limit {limit:.2f} GiB")
        return GateResult(self.name, True, f"peak {peak:.2f} GiB <= {limit:.2f} GiB")

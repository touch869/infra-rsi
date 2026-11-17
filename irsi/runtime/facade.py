"""Deterministic runtime tools shared by expert roles.

The facade is the boundary between an expert artifact and the real harness:
experts never import backends, gates, or HyperParallel directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..contract import InfraTaskSpec, check_overrides_allowed
from ..contract import surfaces as _surfaces  # noqa: F401  (plugin registration)
from .. import gates as _gates  # noqa: F401
from ..contract.surfaces.base import Hypothesis
from ..execution.backends.base import Backend, TrialResult
from ..execution.trial_executor import TrialExecutor
from ..gates.base import GateContext, GateResult
from ..registry import GATES, SURFACES

__all__ = ["RuntimeFacade"]


class RuntimeFacade:
    """A stable set of deterministic operations an expert may request."""

    def __init__(
        self,
        spec: InfraTaskSpec,
        backend: Backend,
        trial_root: str | Path,
        *,
        executor: TrialExecutor | None = None,
    ) -> None:
        self.spec = spec
        self.backend = backend
        self.trial_root = Path(trial_root)
        self.executor = executor or TrialExecutor(spec, backend)

    def list_candidates(self) -> list[Hypothesis]:
        """Return the edit-surface candidates for the contract's domain."""
        candidates = SURFACES.create(self.spec.domain, spec=self.spec)
        if not isinstance(candidates, (list, tuple)):
            raise TypeError("surface plugin must return a sequence of Hypothesis")
        return list(candidates)

    def validate_overrides(self, overrides: Mapping[str, Any]) -> None:
        """Reject keys outside the contract's writable surface."""
        check_overrides_allowed(self.spec, overrides)

    def execute_trial(
        self,
        overrides: Mapping[str, Any],
        label: str,
        *,
        trial_dir: str | Path | None = None,
    ) -> TrialResult:
        """Run one candidate trial through the selected backend."""
        self.validate_overrides(overrides)
        path = Path(trial_dir) if trial_dir is not None else self.trial_root / label
        return self.executor.execute(overrides, label, path)

    def run_gates(
        self,
        trial: TrialResult,
        baseline: TrialResult | None = None,
        best: TrialResult | None = None,
    ) -> list[GateResult]:
        """Instantiate and run the contract's gates against one trial."""
        gates = [GATES.create(gate.name, **dict(gate.params)) for gate in self.spec.gates]
        context = GateContext(self.spec, trial, baseline, best)
        return [gate.check(context) for gate in gates]

    def metric_value(self, trial: TrialResult) -> float | None:
        """Read the contract metric from one trial's parsed steps."""
        return trial.metrics.value(
            self.spec.metric.key,
            warmup_steps=self.spec.metric.warmup_steps,
            measured_steps=self.spec.metric.measured_steps,
        )

    @staticmethod
    def delta(value: float | None, reference: float | None) -> float | None:
        """Relative change against a reference value."""
        if value is None or reference in (None, 0):
            return None
        return (value - reference) / reference

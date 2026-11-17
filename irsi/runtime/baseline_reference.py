"""Frozen reference baseline: always the observed trial."""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import InfraTaskSpec
from ..execution.backends.base import TrialResult

__all__ = ["BaselineReference"]


@dataclass(frozen=True)
class BaselineReference:
    """The observed baseline used for all candidate comparisons."""

    trial: TrialResult
    metric: float | None
    numeric_hash: str

    @classmethod
    def from_trial(cls, spec: InfraTaskSpec, trial: TrialResult) -> "BaselineReference":
        metric = trial.metrics.value(
            spec.metric.key,
            warmup_steps=spec.metric.warmup_steps,
            measured_steps=spec.metric.measured_steps,
        )
        return cls(trial=trial, metric=metric, numeric_hash=trial.metrics.numeric_hash)

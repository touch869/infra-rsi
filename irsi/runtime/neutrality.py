"""Post-execution neutrality check for the observation patch."""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import InfraTaskSpec
from ..execution.backends.base import TrialResult

__all__ = ["NeutralityChecker", "NeutralityResult"]


@dataclass(frozen=True)
class NeutralityResult:
    """Whether the observation patch changed numerical semantics."""

    numeric_identical: bool
    clean_metric: float | None
    observed_metric: float | None
    overhead: float | None
    clean_numeric_hash: str
    observed_numeric_hash: str
    peak_mem_delta: float | None
    reason: str


class NeutralityChecker:
    """Compare clean and observed trial results; execution is separate."""

    def check(self, spec: InfraTaskSpec, clean: TrialResult, observed: TrialResult) -> NeutralityResult:
        metric = spec.metric
        clean_metric = clean.metrics.value(
            metric.key,
            warmup_steps=metric.warmup_steps,
            measured_steps=metric.measured_steps,
        )
        observed_metric = observed.metrics.value(
            metric.key,
            warmup_steps=metric.warmup_steps,
            measured_steps=metric.measured_steps,
        )

        if clean_metric is None or observed_metric is None or clean_metric == 0:
            overhead = None
        else:
            overhead = (observed_metric - clean_metric) / clean_metric

        clean_hash = clean.metrics.numeric_hash
        observed_hash = observed.metrics.numeric_hash
        numeric_identical = (
            clean_hash == observed_hash
            and bool(clean.metrics.steps)
            and bool(observed.metrics.steps)
        )

        clean_peak = clean.metrics.peak_mem_gib
        observed_peak = observed.metrics.peak_mem_gib
        peak_mem_delta = (
            observed_peak - clean_peak
            if clean_peak is not None and observed_peak is not None
            else None
        )

        reason = (
            "numeric fingerprints identical"
            if numeric_identical
            else "numeric fingerprints differ"
        )
        return NeutralityResult(
            numeric_identical=numeric_identical,
            clean_metric=clean_metric,
            observed_metric=observed_metric,
            overhead=overhead,
            clean_numeric_hash=clean_hash,
            observed_numeric_hash=observed_hash,
            peak_mem_delta=peak_mem_delta,
            reason=reason,
        )

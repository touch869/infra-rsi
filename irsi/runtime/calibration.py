"""Baseline calibration for observation overhead.

Two baselines are measured: a clean run and an observed run with the metric
instrumentation enabled. If the observation changes throughput beyond the noise
band, the observed baseline becomes the comparison reference.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import InfraTaskSpec
from ..execution.backends.base import TrialResult
from .facade import RuntimeFacade

__all__ = ["BaselineCalibration", "BaselineCalibrator"]


@dataclass(frozen=True)
class BaselineCalibration:
    """Clean and observed baseline measurements plus the chosen reference."""

    clean: TrialResult
    observed: TrialResult
    clean_metric: float | None
    observed_metric: float | None
    overhead: float | None
    use_observed: bool
    reference_metric: float | None


class BaselineCalibrator:
    """Run two baselines and decide whether observation overhead is material."""

    def __init__(
        self,
        spec: InfraTaskSpec,
        clean_facade: RuntimeFacade,
        observed_facade: RuntimeFacade,
    ) -> None:
        self.spec = spec
        self.clean_facade = clean_facade
        self.observed_facade = observed_facade

    def run(self) -> BaselineCalibration:
        clean = self.clean_facade.execute_trial({}, "baseline-clean")
        observed = self.observed_facade.execute_trial({}, "baseline-observed")

        clean_metric = self.clean_facade.metric_value(clean)
        observed_metric = self.observed_facade.metric_value(observed)

        if clean_metric is None or observed_metric is None:
            use_observed = False
            reference_metric = clean_metric if clean_metric is not None else observed_metric
            overhead = None
        else:
            overhead = self.clean_facade.delta(observed_metric, clean_metric)
            use_observed = overhead is not None and abs(overhead) > self.spec.metric.noise_fraction
            reference_metric = observed_metric if use_observed else clean_metric

        return BaselineCalibration(
            clean=clean,
            observed=observed,
            clean_metric=clean_metric,
            observed_metric=observed_metric,
            overhead=overhead,
            use_observed=use_observed,
            reference_metric=reference_metric,
        )

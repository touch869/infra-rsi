"""Baseline calibration: analyze clean/observed trials; reference is observed."""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import InfraTaskSpec
from ..execution.backends.base import TrialResult
from .baseline_reference import BaselineReference
from .neutrality import NeutralityChecker, NeutralityResult

__all__ = ["BaselineCalibration", "BaselineCalibrator"]


@dataclass(frozen=True)
class BaselineCalibration:
    """Clean control, observed reference, and neutrality evidence."""

    clean: TrialResult
    observed: TrialResult
    neutrality: NeutralityResult
    reference: BaselineReference


class BaselineCalibrator:
    """Analyze two already-executed baselines; it does not run trials."""

    def calibrate(
        self,
        spec: InfraTaskSpec,
        clean: TrialResult,
        observed: TrialResult,
    ) -> BaselineCalibration:
        neutrality = NeutralityChecker().check(spec, clean, observed)
        reference = BaselineReference.from_trial(spec, observed)
        return BaselineCalibration(
            clean=clean,
            observed=observed,
            neutrality=neutrality,
            reference=reference,
        )

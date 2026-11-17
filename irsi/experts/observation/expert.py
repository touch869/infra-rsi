"""ObservationExpert: produce a task-level metric/log observation plan."""

from __future__ import annotations

from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..artifacts import ObservationPatch, ObservationPlan
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import OBSERVATION_PROMPT_SPEC

__all__ = ["ObservationExpert"]


class ObservationExpert:
    name = "observation"
    stage = "observation"
    prompt_spec = OBSERVATION_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        # Observation is task-level and independent of any hypothesis/candidate.
        metric = context.task.metric
        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=ObservationPlan(
                metric_key=metric.key,
                direction=metric.direction,
                noise_fraction=metric.noise_fraction,
                warmup_steps=metric.warmup_steps,
                measured_steps=metric.measured_steps,
                log_patterns=(
                    "step=",
                    "performance/tokens_per_second",
                    "memory/device_max_allocated_gb",
                ),
                # Phase-1 HP logs already expose these fields, so no code patch
                # is required; a non-empty patch is applied before calibration.
                instrumentation_patch=ObservationPatch(),
                calibrate_baseline=True,
            ),
        )


EXPERTS.register(ObservationExpert())

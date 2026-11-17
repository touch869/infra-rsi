"""ObservationExpert: produce a task-level metric/log observation plan."""

from __future__ import annotations

from typing import Mapping

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
        patch_config = context.task.domain_params.get("observation_patch", {})
        if patch_config:
            if not isinstance(patch_config, Mapping):
                raise ValueError("domain_params.observation_patch must be a mapping")
            patch = ObservationPatch(
                target_files=tuple(
                    str(path) for path in patch_config.get("target_files", ())
                ),
                diff=str(patch_config.get("diff", "")),
                apply_before_baseline=bool(
                    patch_config.get("apply_before_baseline", True)
                ),
            )
        else:
            patch = ObservationPatch()

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
                instrumentation_patch=patch,
                calibrate_baseline=True,
            ),
        )


EXPERTS.register(ObservationExpert())

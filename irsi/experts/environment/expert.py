"""EnvironmentExpert: deterministic environment probe for the baseline world."""

from __future__ import annotations

from ...environment.snapshot import EnvironmentSnapshot
from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import ENVIRONMENT_PROMPT_SPEC

__all__ = ["EnvironmentExpert"]


class EnvironmentExpert:
    name = "environment"
    stage = "environment"
    prompt_spec = ENVIRONMENT_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        # Deterministic probe; environment repair remains a bounded external action.
        snapshot = EnvironmentSnapshot.capture(context.task)
        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=snapshot,
        )


EXPERTS.register(EnvironmentExpert())

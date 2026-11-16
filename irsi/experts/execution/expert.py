"""ExecutionExpert: run one candidate through the backend facade."""

from __future__ import annotations

from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..artifacts import CandidateSpec, ExecutionResult
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import EXECUTION_PROMPT_SPEC

__all__ = ["ExecutionExpert"]


class ExecutionExpert:
    name = "execution"
    stage = "execution"
    prompt_spec = EXECUTION_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        candidate = context.candidate
        if not isinstance(candidate, CandidateSpec):
            candidate = context.previous_artifact
        if not isinstance(candidate, CandidateSpec):
            raise ValueError("ExecutionExpert needs a CandidateSpec")

        trial = facade.execute_trial(
            candidate.overrides,
            label=candidate.hypothesis_id,
        )
        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=ExecutionResult(candidate=candidate, trial=trial),
        )


EXPERTS.register(ExecutionExpert())

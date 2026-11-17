"""Deterministic execution stage: no expert prompt, no agent, no judgment."""

from __future__ import annotations

from ..experts.artifacts import CandidateSpec, ExecutionResult
from ..prompting import StageContext
from ..runtime.facade import RuntimeFacade

__all__ = ["ExecutionStage"]


class ExecutionStage:
    """Run one candidate through the runtime facade and return raw evidence."""

    name = "execution"
    stage = "execution"

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExecutionResult:
        candidate = context.candidate
        if not isinstance(candidate, CandidateSpec):
            candidate = context.previous_artifact
        if not isinstance(candidate, CandidateSpec):
            raise ValueError("ExecutionStage needs a CandidateSpec")

        trial = facade.execute_trial(candidate.overrides, label=candidate.hypothesis_id)
        return ExecutionResult(candidate, trial)

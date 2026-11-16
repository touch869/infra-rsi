"""DevelopmentExpert: convert a hypothesis into a contract-approved candidate."""

from __future__ import annotations

from ...contract.surfaces.base import Hypothesis
from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..artifacts import CandidateSpec, HypothesisSet
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import DEVELOPMENT_PROMPT_SPEC

__all__ = ["DevelopmentExpert"]


class DevelopmentExpert:
    name = "development"
    stage = "development"
    prompt_spec = DEVELOPMENT_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        artifact = context.previous_artifact
        if isinstance(artifact, HypothesisSet):
            if not artifact.hypotheses:
                raise ValueError("DecisionExpert returned an empty HypothesisSet")
            hypothesis = artifact.hypotheses[0]
        elif isinstance(context.candidate, Hypothesis):
            hypothesis = context.candidate
        else:
            raise ValueError("DevelopmentExpert needs a Hypothesis or HypothesisSet")

        facade.validate_overrides(hypothesis.overrides)

        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=CandidateSpec(
                hypothesis_id=hypothesis.id,
                description=hypothesis.description,
                overrides=dict(hypothesis.overrides),
                expect_numeric_equal=hypothesis.expect_numeric_equal,
                target_surface=context.task.domain,
                rationale="Overrides validated against the task contract.",
            ),
        )


EXPERTS.register(DevelopmentExpert())

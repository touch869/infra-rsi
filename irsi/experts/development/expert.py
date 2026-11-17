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

        overrides = dict(hypothesis.overrides)
        hypothesis_id = hypothesis.id
        rationale = "Overrides validated against the task contract."

        if context.failure and context.attempt > 0:
            overrides = self._repair_overrides(context, overrides)
            hypothesis_id = f"{hypothesis.id}-retry-{context.attempt}"
            rationale = (
                f"Repair attempt {context.attempt} after failure: {context.failure}"
            )

        facade.validate_overrides(overrides)

        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=CandidateSpec(
                hypothesis_id=hypothesis_id,
                description=hypothesis.description,
                overrides=overrides,
                expect_numeric_equal=hypothesis.expect_numeric_equal,
                target_surface=context.task.domain,
                rationale=rationale,
                patch=hypothesis.patch,
                patch_target_files=hypothesis.patch_target_files,
            ),
        )

    def _repair_overrides(
        self, context: StageContext, overrides: dict[str, object]
    ) -> dict[str, object]:
        """Deterministic repair for config-only surfaces.

        The contract may declare a fallback ladder. Without one, an OOM failure
        reduces the layer count by ``repair_step``; other failures keep the
        candidate unchanged and rely on the bounded retry loop.
        """
        params = context.task.domain_params
        ladder = params.get("candidate_repair_ladder", ())
        if isinstance(ladder, (list, tuple)) and ladder:
            index = min(context.attempt - 1, len(ladder) - 1)
            repaired = dict(ladder[index])
            repaired.update(overrides)
            # A ladder entry is meant to replace the failing setting.
            repaired.update(dict(ladder[index]))
            return repaired

        text = context.failure.lower()
        key = "activation_checkpoint.selection.layer_count"
        if key in overrides and ("out of memory" in text or "oom" in text):
            step = int(params.get("repair_step", 1))
            count = max(0, int(overrides[key]) - step)
            repaired = dict(overrides)
            repaired[key] = count
            return repaired

        return overrides


EXPERTS.register(DevelopmentExpert())

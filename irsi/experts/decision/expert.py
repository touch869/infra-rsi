"""DecisionExpert: choose contract-valid hypotheses from the surface."""

from __future__ import annotations

from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..artifacts import HypothesisSet
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import DECISION_PROMPT_SPEC

__all__ = ["DecisionExpert"]


class DecisionExpert:
    name = "decision"
    stage = "decision"
    prompt_spec = DECISION_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        hypotheses = facade.list_candidates()
        valid = []
        for hypothesis in hypotheses:
            try:
                facade.validate_overrides(hypothesis.overrides)
            except ValueError:
                continue
            valid.append(hypothesis)

        # Non-empty candidates come first; the no-op control is a drift check.
        valid.sort(key=lambda hypothesis: (not hypothesis.overrides, hypothesis.id))
        selected = tuple(valid[: context.task.budget.max_trials])

        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=HypothesisSet(
                hypotheses=selected,
                rationale=(
                    f"Selected {len(selected)} contract-valid hypotheses from "
                    f"{context.task.domain}; non-empty candidates sorted first."
                ),
            ),
        )


EXPERTS.register(DecisionExpert())

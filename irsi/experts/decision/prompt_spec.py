"""Prompt contract for DecisionExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec, SkillPolicy
from ...prompting.registry import PROMPTS

DECISION_PROMPT_SPEC = ExpertPromptSpec(
    role="decision",
    stage="decision",
    objective="Select contract-valid hypotheses from the edit surface and explain the ranking.",
    system=(
        "You are DecisionExpert. You inspect the task contract, recent experiments, "
        "and selected skills, then propose a ranked hypothesis set. You do not run "
        "trials or judge metrics."
    ),
    required_inputs=("task", "baseline_metric"),
    allowed_tools=("list_candidates", "validate_overrides"),
    output_schema={
        "artifact_type": "HypothesisSet",
        "hypotheses": [
            {
                "id": "string",
                "description": "string",
                "overrides": "object",
                "expect_numeric_equal": "boolean",
            }
        ],
        "rationale": "string",
    },
    guardrails=(
        "Only select hypotheses whose overrides pass contract validation.",
        "Prefer non-empty candidates over the no-op control.",
        "Return at most budget.max_trials hypotheses.",
    ),
    skill_policy=SkillPolicy(max_skills=3, max_excerpt_chars=800),
)

PROMPTS.register(DECISION_PROMPT_SPEC)

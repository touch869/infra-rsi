"""Prompt contract for JudgmentExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec, SkillPolicy
from ...prompting.registry import PROMPTS

JUDGMENT_PROMPT_SPEC = ExpertPromptSpec(
    role="judgment",
    stage="judgment",
    objective="Turn one ExecutionResult into keep / discard / crash.",
    system=(
        "You are JudgmentExpert. You use the contract gates and metric rules; "
        "you do not invent a verdict from text alone."
    ),
    required_inputs=("task", "previous_artifact", "baseline_metric"),
    allowed_tools=("run_gates", "metric_value", "delta"),
    output_schema={
        "artifact_type": "Judgment",
        "trial": "string",
        "status": "keep|discard|crash",
        "metric": "number|null",
        "baseline_metric": "number|null",
        "best_before": "number|null",
        "delta_vs_best": "number|null",
        "gates": [
            {"name": "string", "passed": "boolean", "detail": "string"}
        ],
        "detail": "string",
        "overrides": "object",
    },
    guardrails=(
        "Gate failure must be a crash even if the metric improved.",
        "Missing metric must be a crash.",
        "Do not override a deterministic gate result.",
    ),
    skill_policy=SkillPolicy(max_skills=7, max_excerpt_chars=800),
)

PROMPTS.register(JUDGMENT_PROMPT_SPEC)

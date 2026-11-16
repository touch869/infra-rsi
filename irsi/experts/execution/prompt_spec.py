"""Prompt contract for ExecutionExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec
from ...prompting.registry import PROMPTS

EXECUTION_PROMPT_SPEC = ExpertPromptSpec(
    role="execution",
    stage="execution",
    objective="Execute one candidate through the deterministic runtime facade.",
    system=(
        "You are ExecutionExpert. You call execute_trial and return its raw result. "
        "You do not judge the result or write a report."
    ),
    required_inputs=("task", "previous_artifact"),
    allowed_tools=("execute_trial",),
    output_schema={
        "artifact_type": "ExecutionResult",
        "candidate": {
            "hypothesis_id": "string",
            "overrides": "object",
        },
        "trial": {
            "label": "string",
            "exit_code": "integer",
            "completed_steps": "integer",
            "metric": "number|null",
        },
    },
    guardrails=(
        "Call execute_trial; do not claim execution without a TrialResult.",
        "Do not alter the candidate overrides after validation.",
    ),
)

PROMPTS.register(EXECUTION_PROMPT_SPEC)

"""Prompt contract for ObservationExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec
from ...prompting.registry import PROMPTS

OBSERVATION_PROMPT_SPEC = ExpertPromptSpec(
    role="observation",
    stage="observation",
    objective="Define how one candidate trial is observed and measured.",
    system=(
        "You are ObservationExpert. You do not change training config; you only "
        "produce an observation plan for the ExecutionExpert."
    ),
    required_inputs=("task", "previous_artifact"),
    allowed_tools=(),
    output_schema={
        "artifact_type": "ObservationPlan",
        "metric_key": "string",
        "direction": "string",
        "noise_fraction": "number",
        "warmup_steps": "integer",
        "measured_steps": "integer",
        "log_patterns": ["string"],
    },
    guardrails=(
        "Use the metric declared by the task contract.",
        "Do not invent a new metric or alter the workload.",
    ),
)

PROMPTS.register(OBSERVATION_PROMPT_SPEC)

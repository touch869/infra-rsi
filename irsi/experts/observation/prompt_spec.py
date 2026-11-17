"""Prompt contract for ObservationExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec
from ...prompting.registry import PROMPTS

OBSERVATION_PROMPT_SPEC = ExpertPromptSpec(
    role="observation",
    stage="observation",
    objective="Define the task-level observation plan and switchable metric patch.",
    system=(
        "You are ObservationExpert. You do not change training config; you only "
        "produce a task/round-level observation plan that all candidates share."
    ),
    required_inputs=("task",),
    allowed_tools=(),
    output_schema={
        "artifact_type": "ObservationPlan",
        "scope": "task",
        "metric_key": "string",
        "direction": "string",
        "noise_fraction": "number",
        "warmup_steps": "integer",
        "measured_steps": "integer",
        "log_patterns": ["string"],
        "instrumentation_patch": {
            "target_files": ["string"],
            "diff": "string",
            "apply_before_baseline": "boolean",
        },
        "calibrate_baseline": "boolean",
    },
    guardrails=(
        "Use the metric declared by the task contract.",
        "Do not invent a new metric or alter the workload.",
        "Observation is task-level, not hypothesis-level.",
        "If metric fields already exist, the instrumentation patch may be empty.",
        "Any non-empty observation patch must be applied before baseline calibration.",
    ),
)

PROMPTS.register(OBSERVATION_PROMPT_SPEC)

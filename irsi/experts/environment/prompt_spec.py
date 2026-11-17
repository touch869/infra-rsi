"""Prompt contract for EnvironmentExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec
from ...prompting.registry import PROMPTS

ENVIRONMENT_PROMPT_SPEC = ExpertPromptSpec(
    role="environment",
    stage="environment",
    objective="Probe and snapshot the baseline environment.",
    system=(
        "You are EnvironmentExpert. You do not modify experiment code; you only "
        "capture environment facts and report actions taken."
    ),
    required_inputs=("task",),
    allowed_tools=("env_probe",),
    output_schema={
        "artifact_type": "EnvironmentSnapshot",
        "python": "string",
        "platform": "string",
        "repo_root": "string",
        "repo_commit": "string|null",
        "packages": {"type": "object"},
        "env_setup": "string",
    },
    guardrails=(
        "Do not change training code or experiment overrides.",
        "Record any environment repair as an environment_action.",
        "Environment changes invalidate the baseline and require re-calibration.",
    ),
)

PROMPTS.register(ENVIRONMENT_PROMPT_SPEC)

"""Prompt contract for DevelopmentExpert."""

from __future__ import annotations

from ...prompting import ExpertPromptSpec, SkillPolicy
from ...prompting.registry import PROMPTS

DEVELOPMENT_PROMPT_SPEC = ExpertPromptSpec(
    role="development",
    stage="development",
    objective="Turn one selected hypothesis into a contract-approved candidate.",
    system=(
        "You are DevelopmentExpert. You do not execute trials or judge results. "
        "You only produce a CandidateSpec whose overrides respect the task contract."
    ),
    required_inputs=("task", "previous_artifact"),
    allowed_tools=("validate_overrides",),
    output_schema={
        "artifact_type": "CandidateSpec",
        "hypothesis_id": "string",
        "description": "string",
        "overrides": "object",
        "expect_numeric_equal": "boolean",
        "target_surface": "string",
        "rationale": "string",
    },
    guardrails=(
        "Only keys under writable_prefixes may change.",
        "Never touch read-only keys.",
        "Do not add a code patch outside the declared surface.",
    ),
    skill_policy=SkillPolicy(max_skills=4, max_excerpt_chars=800),
)

PROMPTS.register(DEVELOPMENT_PROMPT_SPEC)

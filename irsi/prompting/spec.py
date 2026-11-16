"""Prompt contracts for one expert stage.

The spec is static; the builder injects the current stage context and selected
skills without changing the role, tool set, or output schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "ExpertPromptSpec",
    "PromptBuildError",
    "RenderedPrompt",
    "SkillPolicy",
    "SkillView",
]


class PromptBuildError(ValueError):
    """Raised when a prompt cannot be assembled from its inputs."""


@dataclass(frozen=True)
class SkillPolicy:
    """How many skills and how much of each skill may enter the prompt."""

    max_skills: int = 4
    max_excerpt_chars: int = 1200

    def __post_init__(self) -> None:
        if self.max_skills < 0:
            raise ValueError("max_skills must be >= 0")
        if self.max_excerpt_chars < 0:
            raise ValueError("max_excerpt_chars must be >= 0")


@dataclass(frozen=True)
class SkillView:
    """A selected skill rendered into the prompt as context, not executable code."""

    id: str
    version: int
    title: str
    when_to_use: str
    excerpt: str
    manifest: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("skill id must be non-empty")
        if self.version < 1:
            raise ValueError("skill version must be >= 1")


@dataclass(frozen=True)
class ExpertPromptSpec:
    """Static prompt contract for one expert role."""

    role: str
    stage: str
    objective: str
    system: str
    required_inputs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    guardrails: tuple[str, ...] = ()
    skill_policy: SkillPolicy = field(default_factory=SkillPolicy)
    version: int = 1

    def __post_init__(self) -> None:
        for name in ("role", "stage", "objective", "system"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.version < 1:
            raise ValueError("version must be >= 1")


@dataclass(frozen=True)
class RenderedPrompt:
    """The deterministic result of assembling one stage prompt."""

    role: str
    stage: str
    text: str
    prompt_hash: str
    sections: Mapping[str, str]
    skill_ids: tuple[str, ...]
    token_estimate: int

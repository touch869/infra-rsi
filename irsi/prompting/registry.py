"""Named prompt specs for expert roles."""

from __future__ import annotations

from .spec import ExpertPromptSpec

__all__ = ["PROMPTS", "PromptRegistry"]


class PromptRegistry:
    """A small registry of static expert prompt contracts."""

    def __init__(self) -> None:
        self._specs: dict[str, ExpertPromptSpec] = {}

    def register(self, spec: ExpertPromptSpec) -> ExpertPromptSpec:
        key = spec.role
        if key in self._specs:
            raise ValueError(f"duplicate prompt spec: {key}")
        self._specs[key] = spec
        return spec

    def get(self, role: str) -> ExpertPromptSpec:
        try:
            return self._specs[role]
        except KeyError as exc:
            known = ", ".join(sorted(self._specs)) or "<none>"
            raise KeyError(f"unknown prompt role: {role!r} (known: {known})") from exc

    def by_stage(self, stage: str) -> list[ExpertPromptSpec]:
        return [spec for spec in self._specs.values() if spec.stage == stage]

    def names(self) -> list[str]:
        return sorted(self._specs)


PROMPTS = PromptRegistry()

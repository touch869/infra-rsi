"""Registry of expert role instances."""

from __future__ import annotations

from .base import ExpertRole

__all__ = ["EXPERTS", "ExpertRegistry"]


class ExpertRegistry:
    """Named expert instances, selectable by role or stage."""

    def __init__(self) -> None:
        self._experts: dict[str, ExpertRole] = {}

    def register(self, expert: ExpertRole) -> ExpertRole:
        key = expert.name
        if key in self._experts:
            raise ValueError(f"duplicate expert role: {key}")
        self._experts[key] = expert
        return expert

    def get(self, name: str) -> ExpertRole:
        try:
            return self._experts[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._experts)) or "<none>"
            raise KeyError(f"unknown expert role: {name!r} (known: {known})") from exc

    def by_stage(self, stage: str) -> list[ExpertRole]:
        return [expert for expert in self._experts.values() if expert.stage == stage]

    def names(self) -> list[str]:
        return sorted(self._experts)


EXPERTS = ExpertRegistry()

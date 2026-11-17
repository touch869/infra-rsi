"""Knowledge provider protocol owned by the knowledge package."""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["KnowledgeProvider"]


class KnowledgeProvider(Protocol):
    """Load framework or domain skills from a static skill source."""

    def list_skills(self, query: Any) -> list[Any]:
        ...

    def get_skill(self, skill_id: str, version: int) -> Any:
        ...

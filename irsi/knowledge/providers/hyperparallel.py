"""HyperParallel skill provider, decoupled from the core package."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..catalog import SkillCatalog
from ..skills import Skill

__all__ = ["HPKnowledgeProvider"]


class HPKnowledgeProvider:
    """Load HP skill packages from ``knowledge/skills``."""

    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            root = Path(__file__).resolve().parents[3] / "knowledge" / "skills"
        self.catalog = SkillCatalog.from_root(root)

    def list_skills(self, query: Mapping[str, Any] | None = None) -> list[Skill]:
        if not query:
            return self.catalog.all()
        return self.catalog.list(**dict(query))

    def get_skill(self, skill_id: str, version: int = 1) -> Skill:
        return self.catalog.get(skill_id, version)

"""Skill catalog: load, index, and query skill packages."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .skills import Skill, load_skill

__all__ = ["SkillCatalog"]


class SkillCatalog:
    """A framework-neutral catalog of loaded skill packages."""

    def __init__(self, skills: Iterable[Skill] = ()) -> None:
        self._skills = list(skills)

    @classmethod
    def from_root(cls, root: str | Path) -> "SkillCatalog":
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(f"skill root does not exist: {root_path}")
        skills = [
            load_skill(path.parent)
            for path in sorted(root_path.rglob("skill.yaml"))
        ]
        return cls(skills)

    def all(self) -> list[Skill]:
        return list(self._skills)

    def names(self) -> list[str]:
        return sorted({skill.manifest.id for skill in self._skills})

    def get(self, skill_id: str, version: int | None = None) -> Skill:
        matches = [
            skill
            for skill in self._skills
            if skill.manifest.id == skill_id
            and (version is None or skill.manifest.version == version)
        ]
        if not matches:
            known = ", ".join(self.names()) or "<none>"
            raise KeyError(f"unknown skill: {skill_id!r} (known: {known})")
        matches.sort(key=lambda skill: skill.manifest.version)
        return matches[-1]

    def list(
        self,
        *,
        framework: str | None = None,
        surface: str | None = None,
        stage: str | None = None,
        tags: Iterable[str] = (),
        kind: str | None = None,
    ) -> list[Skill]:
        matched = []
        required_tags = set(tags)
        for skill in self._skills:
            manifest = skill.manifest
            if framework is not None and manifest.framework != framework:
                continue
            if surface is not None and manifest.surface != surface:
                continue
            if stage is not None and stage not in manifest.stages:
                continue
            if kind is not None and manifest.kind != kind:
                continue
            if required_tags and not required_tags.issubset(set(manifest.tags)):
                continue
            matched.append(skill)
        matched.sort(key=lambda skill: (skill.manifest.id, skill.manifest.version))
        return matched

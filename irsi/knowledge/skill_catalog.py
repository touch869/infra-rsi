"""Auto-discovered ``SKILL.md`` packages stored under ``irsi.knowledge``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import yaml

__all__ = [
    "DEFAULT_CATALOG",
    "Skill",
    "SkillCatalog",
    "SkillLoadError",
    "get_skill",
    "list_skills",
]

_PACKAGE_ROOT = Path(__file__).resolve().parent
_FRONTMATTER = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)


class SkillLoadError(ValueError):
    """A ``SKILL.md`` file is missing required metadata or cannot be parsed."""


@dataclass(frozen=True)
class Skill:
    """One loaded skill package rooted at its ``SKILL.md`` directory."""

    name: str
    description: str
    version: int
    root: Path
    path: Path
    metadata: Mapping[str, Any]
    body: str

    def read_text(self, relative: str) -> str:
        """Read a reference, schema, or template next to ``SKILL.md``."""
        target = (self.root / relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"skill resource escapes its root: {relative!r}")
        return target.read_text(encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "path": str(self.path),
            "metadata": dict(self.metadata),
        }


class SkillCatalog:
    """A name/version index over auto-discovered skill packages."""

    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills: dict[tuple[str, int], Skill] = {}
        for skill in skills:
            key = (skill.name, skill.version)
            if key in self._skills:
                raise SkillLoadError(f"duplicate skill {skill.name!r} version {skill.version}")
            self._skills[key] = skill

    @classmethod
    def discover(cls, root: str | Path | None = None) -> "SkillCatalog":
        """Discover every ``SKILL.md`` below ``root`` (the package by default)."""
        base = Path(root) if root is not None else _PACKAGE_ROOT
        if not base.is_dir():
            raise SkillLoadError(f"skill root is not a directory: {base}")
        return cls(_parse_skill(path) for path in sorted(base.rglob("SKILL.md")))

    def list_skills(self, query: Any = None) -> list[Skill]:
        """List skills, optionally filtered by text or metadata equality."""
        items = sorted(self._skills.values(), key=lambda skill: (skill.name, skill.version))
        if not query:
            return items
        if isinstance(query, str):
            needle = query.casefold()
            return [
                skill
                for skill in items
                if needle in skill.name.casefold() or needle in skill.description.casefold()
            ]
        if isinstance(query, Mapping):
            return [
                skill
                for skill in items
                if all(skill.metadata.get(key) == value for key, value in query.items())
            ]
        raise TypeError("skill query must be text, a metadata mapping, or None")

    def get_skill(self, skill_id: str, version: int | None = None) -> Skill:
        """Return one skill by name, optionally restricted to a version."""
        if version is not None:
            skill = self._skills.get((skill_id, version))
            if skill is not None:
                return skill
        else:
            matches = [skill for skill in self._skills.values() if skill.name == skill_id]
            if len(matches) == 1:
                return matches[0]
        raise KeyError(f"unknown skill: {skill_id!r} version={version!r}")

    def __iter__(self):
        return iter(self.list_skills())

    def __len__(self) -> int:
        return len(self._skills)


def _parse_skill(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if match is None:
        raise SkillLoadError(f"{path}: missing YAML frontmatter")
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillLoadError(f"{path}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SkillLoadError(f"{path}: frontmatter must be a mapping")

    name = str(metadata.get("name", "")).strip()
    description = str(metadata.get("description", "")).strip()
    version = metadata.get("version", 1)
    if not name or not description:
        raise SkillLoadError(f"{path}: frontmatter requires name and description")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SkillLoadError(f"{path}: version must be a positive integer")

    return Skill(
        name=name,
        description=description,
        version=version,
        root=path.parent,
        path=path,
        metadata=MappingProxyType(dict(metadata)),
        body=text[match.end() :],
    )


DEFAULT_CATALOG = SkillCatalog.discover()


def get_skill(skill_id: str, version: int | None = None) -> Skill:
    return DEFAULT_CATALOG.get_skill(skill_id, version)


def list_skills(query: Any = None) -> list[Skill]:
    return DEFAULT_CATALOG.list_skills(query)

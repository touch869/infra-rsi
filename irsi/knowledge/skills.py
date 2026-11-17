"""Skill packages: human-readable SKILL.md plus a machine-readable manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..prompting import SkillView

__all__ = ["Skill", "SkillManifest", "load_skill"]


@dataclass(frozen=True)
class SkillManifest:
    """The machine-readable contract of one skill package."""

    id: str
    version: int
    kind: str
    framework: str
    surface: str
    stages: tuple[str, ...]
    title: str
    when_to_use: str
    tags: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("skill id must be non-empty")
        if self.version < 1:
            raise ValueError("skill version must be >= 1")
        if self.kind not in ("domain", "guidance"):
            raise ValueError("skill kind must be 'domain' or 'guidance'")
        if not self.framework.strip() or not self.surface.strip():
            raise ValueError("framework and surface must be non-empty")
        if not self.stages:
            raise ValueError("skill must declare at least one stage")
        if not self.title.strip() or not self.when_to_use.strip():
            raise ValueError("title and when_to_use must be non-empty")


@dataclass(frozen=True)
class Skill:
    """A loaded skill package."""

    manifest: SkillManifest
    body: str
    path: Path

    def to_view(self) -> SkillView:
        """Render the skill as prompt context, not as executable code."""
        return SkillView(
            id=self.manifest.id,
            version=self.manifest.version,
            title=self.manifest.title,
            when_to_use=self.manifest.when_to_use,
            excerpt=self.body,
            manifest={
                "kind": self.manifest.kind,
                "framework": self.manifest.framework,
                "surface": self.manifest.surface,
                "stages": list(self.manifest.stages),
                "tags": list(self.manifest.tags),
                "constraints": list(self.manifest.constraints),
                "source": self.manifest.source,
            },
        )


def load_skill(path: str | Path) -> Skill:
    """Load one skill directory containing ``SKILL.md`` and ``skill.yaml``."""
    skill_dir = Path(path)
    manifest_path = skill_dir / "skill.yaml"
    body_path = skill_dir / "SKILL.md"
    if not manifest_path.is_file() or not body_path.is_file():
        raise FileNotFoundError(f"skill package missing files: {skill_dir}")

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"skill.yaml must be a mapping: {manifest_path}")

    manifest = SkillManifest(
        id=str(raw["id"]),
        version=int(raw["version"]),
        kind=str(raw.get("kind", "domain")),
        framework=str(raw["framework"]),
        surface=str(raw["surface"]),
        stages=tuple(str(stage) for stage in raw.get("stages", ())),
        title=str(raw["title"]),
        when_to_use=str(raw["when_to_use"]),
        tags=tuple(str(tag) for tag in raw.get("tags", ())),
        constraints=tuple(str(item) for item in raw.get("constraints", ())),
        source=str(raw.get("source", "")),
    )
    return Skill(
        manifest=manifest,
        body=body_path.read_text(encoding="utf-8").strip(),
        path=skill_dir,
    )

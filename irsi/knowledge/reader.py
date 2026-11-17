"""Read-only skill resolution for a stage and task surface."""

from __future__ import annotations

from ..contract import InfraTaskSpec
from ..prompting import SkillView
from .catalog import SkillCatalog

__all__ = ["SkillResolver"]


class SkillResolver:
    """Select skills for one expert stage, without executing them."""

    def __init__(self, catalog: SkillCatalog, framework: str = "hyperparallel") -> None:
        self.catalog = catalog
        self.framework = framework

    def resolve(
        self,
        stage: str,
        task: InfraTaskSpec,
        tags: tuple[str, ...] = (),
    ) -> list[SkillView]:
        skills = self.catalog.list(
            framework=self.framework,
            stage=stage,
            tags=tags,
        )
        selected = [
            skill
            for skill in skills
            if self._surface_matches(skill.manifest.surface, task.domain)
        ]
        return [skill.to_view() for skill in selected]

    @staticmethod
    def _surface_matches(skill_surface: str, task_surface: str) -> bool:
        if skill_surface == "*":
            return True
        return task_surface == skill_surface or task_surface.startswith(skill_surface)

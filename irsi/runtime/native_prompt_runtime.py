"""Native prompt runtime: render the stage prompt, then run the expert."""

from __future__ import annotations

from typing import Any

from ..experts.base import ExpertResult
from ..prompting import PromptBuilder, SkillView, StageContext
from ..runtime.facade import RuntimeFacade

__all__ = ["NativePromptRuntime"]


class NativePromptRuntime:
    """Deterministic adapter that records prompt/skill provenance around an expert."""

    def __init__(self, builder: PromptBuilder | None = None) -> None:
        self.builder = builder or PromptBuilder()

    def run(
        self,
        expert: Any,
        context: StageContext,
        skills: tuple[SkillView, ...] = (),
        facade: RuntimeFacade | None = None,
    ) -> ExpertResult:
        prompt = self.builder.render(expert.prompt_spec, context, skills)
        result = expert.run(context, facade)
        return ExpertResult(
            role=result.role,
            stage=result.stage,
            artifact=result.artifact,
            used_skills=prompt.skill_ids,
            prompt_hash=prompt.prompt_hash,
        )

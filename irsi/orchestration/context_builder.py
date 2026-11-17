"""Assemble the minimum stage context from task, records, skills, and artifacts."""

from __future__ import annotations

from typing import Any

from ..contract import InfraTaskSpec
from ..knowledge.reader import SkillResolver
from ..knowledge.runtime.reader import RuntimeKnowledgeReader
from ..prompting import StageContext
from .state import RoundState, Stage

__all__ = ["ContextBuilder"]


class ContextBuilder:
    """Build one StageContext plus the skills selected for that stage."""

    def __init__(
        self,
        task: InfraTaskSpec,
        *,
        reader: RuntimeKnowledgeReader | None = None,
        resolver: SkillResolver | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        self.task = task
        self.reader = reader
        self.resolver = resolver
        self.tags = tags

    def build(
        self,
        state: RoundState,
        stage: Stage,
        *,
        candidate: Any = None,
        failure: str = "",
        attempt: int = 0,
    ) -> tuple[StageContext, tuple[Any, ...]]:
        records = ()
        if self.reader is not None:
            bundle = self.reader.bundle(round_id=state.round_id, limit=10)
            records = tuple(record.to_dict() for record in bundle.records)

        skills = ()
        if self.resolver is not None:
            skills = tuple(self.resolver.resolve(stage.value, self.task, self.tags))

        context = StageContext(
            task=self.task,
            stage=stage.value,
            baseline_metric=state.baseline_metric,
            best_metric=state.best_metric,
            baseline_trial=state.baseline_trial,
            best_trial=state.best_trial,
            records=records,
            previous_artifact=state.previous_artifact,
            candidate=candidate if candidate is not None else state.current_candidate,
            failure=failure,
            attempt=attempt,
        )
        return context, skills

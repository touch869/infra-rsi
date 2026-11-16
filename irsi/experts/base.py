"""Expert role protocol and the result envelope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..prompting import ExpertPromptSpec, StageContext
from ..runtime.facade import RuntimeFacade

__all__ = ["ExpertResult", "ExpertRole"]


@dataclass(frozen=True)
class ExpertResult:
    """One expert's artifact plus the prompt/skill provenance needed for audit."""

    role: str
    stage: str
    artifact: Any
    used_skills: tuple[str, ...] = ()
    prompt_hash: str = ""


class ExpertRole(Protocol):
    """A role that produces one artifact from a stage context and facade."""

    name: str
    stage: str
    prompt_spec: ExpertPromptSpec

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        ...

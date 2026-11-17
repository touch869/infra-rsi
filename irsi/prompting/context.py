"""Stage context assembled by orchestration before a prompt is rendered."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..contract import InfraTaskSpec

__all__ = ["StageContext"]


@dataclass(frozen=True)
class StageContext:
    """The minimum current state one expert needs.

    The builder renders only this slice, never the whole ledger or all logs.
    """

    task: InfraTaskSpec
    stage: str
    baseline_metric: float | None = None
    best_metric: float | None = None
    baseline_trial: Any = None
    best_trial: Any = None
    recent_decisions: tuple[Mapping[str, Any], ...] = ()
    records: tuple[Mapping[str, Any], ...] = ()
    previous_artifact: Any = None
    candidate: Any = None
    notes: tuple[str, ...] = ()
    failure: str = ""
    attempt: int = 0

    def __post_init__(self) -> None:
        if not self.stage.strip():
            raise ValueError("stage must be non-empty")
        if self.attempt < 0:
            raise ValueError("attempt must be >= 0")

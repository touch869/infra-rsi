"""Explicit round state for the code-enforced experiment pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["RoundState", "Stage"]


class Stage(str, Enum):
    """Stages the orchestrator may enter; no agent chooses them."""

    CLEAN_BASELINE = "clean_baseline"
    OBSERVATION = "observation"
    OBSERVED_BASELINE = "observed_baseline"
    NEUTRALITY = "neutrality"
    CALIBRATED = "calibrated"
    DECISION = "decision"
    DEVELOPMENT = "development"
    EXECUTION = "execution"
    JUDGMENT = "judgment"
    ARCHIVE = "archive_report"
    NEXT_CANDIDATE = "next_candidate"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class RoundState:
    """Mutable-by-replacement state for one round."""

    round_id: str
    stage: Stage = Stage.CLEAN_BASELINE
    baseline_trial: Any = None
    best_trial: Any = None
    baseline_metric: float | None = None
    best_metric: float | None = None
    candidate_index: int = 0
    trials_run: int = 0
    hypotheses: tuple[Any, ...] = ()
    previous_artifact: Any = None
    current_candidate: Any = None
    observation_plan: Any = None
    stop_reason: str = ""

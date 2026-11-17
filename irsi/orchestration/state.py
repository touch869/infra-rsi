"""Explicit round state and the code-enforced stage transition table."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

__all__ = [
    "RoundState",
    "Stage",
    "StageTransitionError",
    "TRANSITIONS",
    "advance",
    "fail",
]


class Stage(str, Enum):
    """Stages the orchestrator may enter; no agent chooses them."""

    ENV_SETUP = "environment"
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


TRANSITIONS: dict[Stage, tuple[Stage, ...]] = {
    Stage.ENV_SETUP: (Stage.CLEAN_BASELINE,),
    Stage.CLEAN_BASELINE: (Stage.OBSERVATION,),
    Stage.OBSERVATION: (Stage.OBSERVED_BASELINE,),
    Stage.OBSERVED_BASELINE: (Stage.NEUTRALITY,),
    Stage.NEUTRALITY: (Stage.CALIBRATED,),
    Stage.CALIBRATED: (Stage.DECISION,),
    Stage.DECISION: (Stage.DEVELOPMENT, Stage.DONE),
    Stage.DEVELOPMENT: (Stage.EXECUTION,),
    Stage.EXECUTION: (Stage.JUDGMENT, Stage.DEVELOPMENT),
    Stage.JUDGMENT: (Stage.ARCHIVE,),
    Stage.ARCHIVE: (Stage.NEXT_CANDIDATE,),
    Stage.NEXT_CANDIDATE: (Stage.DECISION, Stage.DONE),
    Stage.DONE: (),
    Stage.FAILED: (),
}


class StageTransitionError(ValueError):
    """Raised when a transition is outside the code-enforced pipeline."""


@dataclass(frozen=True)
class RoundState:
    """Mutable-by-replacement state for one round."""

    round_id: str
    stage: Stage = Stage.ENV_SETUP
    baseline_trial: Any = None
    clean_trial: Any = None
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


def advance(state: RoundState, next_stage: Stage, **changes: Any) -> RoundState:
    """Advance one stage only if the transition table permits it."""
    allowed = TRANSITIONS.get(state.stage, ())
    if next_stage not in allowed:
        raise StageTransitionError(
            f"illegal transition {state.stage.value!r} -> {next_stage.value!r}; "
            f"allowed: {[stage.value for stage in allowed]}"
        )
    return replace(state, stage=next_stage, **changes)


def fail(state: RoundState, reason: str) -> RoundState:
    """Mark the round failed from any active stage."""
    return replace(state, stage=Stage.FAILED, stop_reason=reason)

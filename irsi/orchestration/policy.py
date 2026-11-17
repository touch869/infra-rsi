"""Code-enforced stage order, artifact types, and budget rules."""

from __future__ import annotations

from typing import Any

from ..experts.artifacts import (
    ArchiveBundle,
    CandidateSpec,
    ExecutionResult,
    HypothesisSet,
    Judgment,
    ObservationPlan,
)
from .state import Stage

__all__ = [
    "ARTIFACT_TYPES",
    "CANDIDATE_STAGE_ORDER",
    "StagePolicyError",
    "ensure_budget",
    "require_artifact",
]


class StagePolicyError(ValueError):
    """Raised when the orchestrator would leave the code-enforced pipeline."""


ARTIFACT_TYPES = {
    Stage.DECISION: HypothesisSet,
    Stage.DEVELOPMENT: CandidateSpec,
    Stage.OBSERVATION: ObservationPlan,
    Stage.EXECUTION: ExecutionResult,
    Stage.JUDGMENT: Judgment,
    Stage.ARCHIVE: ArchiveBundle,
}

CANDIDATE_STAGE_ORDER = (
    Stage.DECISION,
    Stage.DEVELOPMENT,
    Stage.EXECUTION,
    Stage.JUDGMENT,
    Stage.ARCHIVE,
    Stage.NEXT_CANDIDATE,
)


def require_artifact(stage: Stage, artifact: Any) -> None:
    """Reject an artifact that does not belong to the stage."""
    expected = ARTIFACT_TYPES.get(stage)
    if expected is None:
        return
    if not isinstance(artifact, expected):
        raise StagePolicyError(
            f"stage {stage.value!r} requires {expected.__name__}, got {type(artifact).__name__}"
        )


def ensure_budget(trials_run: int, max_trials: int) -> None:
    """Raise before a trial would exceed the contract budget."""
    if trials_run >= max_trials:
        raise StagePolicyError(f"trial budget exhausted: {trials_run} >= {max_trials}")

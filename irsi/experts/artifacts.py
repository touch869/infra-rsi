"""Artifacts exchanged between expert stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contract.surfaces.base import Hypothesis
from ..execution.backends.base import TrialResult
from ..gates.base import GateResult

__all__ = [
    "ArchiveBundle",
    "CandidateSpec",
    "ExecutionResult",
    "HypothesisSet",
    "Judgment",
    "ObservationPatch",
    "ObservationPlan",
]


@dataclass(frozen=True)
class HypothesisSet:
    """The hypotheses selected by DecisionExpert."""

    hypotheses: tuple[Hypothesis, ...]
    rationale: str = ""


@dataclass(frozen=True)
class CandidateSpec:
    """A contract-approved candidate produced by DevelopmentExpert.

    ``patch`` is an optional source-code diff. The orchestrator applies it to
    the task repo before execution and reverts it on discard/crash; on keep the
    patch artifact is committed with the step report.
    """

    hypothesis_id: str
    description: str
    overrides: Mapping[str, Any] = field(default_factory=dict)
    expect_numeric_equal: bool = True
    target_surface: str = ""
    rationale: str = ""
    patch: str = ""
    patch_target_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise ValueError("hypothesis_id must be non-empty")
        if self.patch and not self.patch_target_files:
            raise ValueError("a candidate patch must declare patch_target_files")


@dataclass(frozen=True)
class ObservationPatch:
    """A code patch that enables the required metric logging.

    The patch is an artifact, not an action taken by the expert; the runtime
    applies it before the baseline calibration when it is non-empty. It is
    toggleable: clean baseline runs with it off, observed baseline with it on.
    """

    target_files: tuple[str, ...] = ()
    diff: str = ""
    apply_before_baseline: bool = True

    def __post_init__(self) -> None:
        if self.diff and not self.target_files:
            raise ValueError("an observation patch with a diff must declare target files")

    @property
    def is_empty(self) -> bool:
        return not self.diff and not self.target_files


@dataclass(frozen=True)
class ObservationPlan:
    """How the task is observed and whether observation changes performance."""

    metric_key: str
    direction: str
    noise_fraction: float
    warmup_steps: int
    measured_steps: int
    scope: str = "task"
    log_patterns: tuple[str, ...] = ()
    instrumentation_patch: ObservationPatch = field(default_factory=ObservationPatch)
    calibrate_baseline: bool = True


@dataclass(frozen=True)
class ExecutionResult:
    """One executed candidate, with raw trial evidence."""

    candidate: CandidateSpec
    trial: TrialResult


@dataclass(frozen=True)
class Judgment:
    """The deterministic keep / discard / crash verdict for one trial."""

    trial: str
    status: str
    metric: float | None
    baseline_metric: float | None
    best_before: float | None
    delta_vs_best: float | None
    gates: tuple[GateResult, ...] = ()
    detail: str = ""
    overrides: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ("keep", "discard", "crash"):
            raise ValueError("status must be keep, discard, or crash")


@dataclass(frozen=True)
class ArchiveBundle:
    """Step and round report payloads produced by ArchiveReportExpert."""

    step_report: Mapping[str, Any]
    round_report: Mapping[str, Any]
    commit_intent: str = "not recorded"

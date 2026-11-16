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
    "ObservationPlan",
]


@dataclass(frozen=True)
class HypothesisSet:
    """The hypotheses selected by DecisionExpert."""

    hypotheses: tuple[Hypothesis, ...]
    rationale: str = ""


@dataclass(frozen=True)
class CandidateSpec:
    """A contract-approved candidate produced by DevelopmentExpert."""

    hypothesis_id: str
    description: str
    overrides: Mapping[str, Any] = field(default_factory=dict)
    expect_numeric_equal: bool = True
    target_surface: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise ValueError("hypothesis_id must be non-empty")


@dataclass(frozen=True)
class ObservationPlan:
    """How ExecutionExpert should observe the trial."""

    metric_key: str
    direction: str
    noise_fraction: float
    warmup_steps: int
    measured_steps: int
    log_patterns: tuple[str, ...] = ()


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

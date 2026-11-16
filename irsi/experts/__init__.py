"""Six expert roles, each producing one artifact for the experiment loop."""

from .archive_report.expert import ArchiveReportExpert
from .artifacts import (
    ArchiveBundle,
    CandidateSpec,
    ExecutionResult,
    HypothesisSet,
    Judgment,
    ObservationPlan,
)
from .base import ExpertResult, ExpertRole
from .decision.expert import DecisionExpert
from .development.expert import DevelopmentExpert
from .execution.expert import ExecutionExpert
from .judgment.expert import JudgmentExpert
from .observation.expert import ObservationExpert
from .registry import EXPERTS, ExpertRegistry

__all__ = [
    "ArchiveBundle",
    "ArchiveReportExpert",
    "CandidateSpec",
    "DecisionExpert",
    "DevelopmentExpert",
    "ExecutionExpert",
    "ExecutionResult",
    "ExpertRegistry",
    "ExpertResult",
    "ExpertRole",
    "HypothesisSet",
    "Judgment",
    "JudgmentExpert",
    "ObservationExpert",
    "ObservationPlan",
    "EXPERTS",
]

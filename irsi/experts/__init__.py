"""Five expert roles, each producing one artifact for the experiment loop."""

from .archive_report.expert import ArchiveReportExpert
from .artifacts import (
    ArchiveBundle,
    CandidateSpec,
    ExecutionResult,
    HypothesisSet,
    Judgment,
    ObservationPatch,
    ObservationPlan,
)
from .base import ExpertResult, ExpertRole
from .decision.expert import DecisionExpert
from .development.expert import DevelopmentExpert
from .judgment.expert import JudgmentExpert
from .observation.expert import ObservationExpert
from .registry import EXPERTS, ExpertRegistry

__all__ = [
    "ArchiveBundle",
    "ArchiveReportExpert",
    "CandidateSpec",
    "DecisionExpert",
    "DevelopmentExpert",
    "ExecutionResult",
    "ExpertRegistry",
    "ExpertResult",
    "ExpertRole",
    "HypothesisSet",
    "Judgment",
    "JudgmentExpert",
    "ObservationExpert",
    "ObservationPatch",
    "ObservationPlan",
    "EXPERTS",
]

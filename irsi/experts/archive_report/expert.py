"""ArchiveReportExpert: build step and round report payloads."""

from __future__ import annotations

from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..artifacts import ArchiveBundle, Judgment
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import ARCHIVE_REPORT_PROMPT_SPEC

__all__ = ["ArchiveReportExpert"]


class ArchiveReportExpert:
    name = "archive_report"
    stage = "archive_report"
    prompt_spec = ARCHIVE_REPORT_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        artifact = context.previous_artifact
        if not isinstance(artifact, Judgment):
            raise ValueError("ArchiveReportExpert needs a Judgment")

        step_report = {
            "trial": artifact.trial,
            "status": artifact.status,
            "metric": artifact.metric,
            "delta_vs_best": artifact.delta_vs_best,
            "detail": artifact.detail,
            "gates": [
                {"name": gate.name, "passed": gate.passed, "detail": gate.detail}
                for gate in artifact.gates
            ],
            "overrides": dict(artifact.overrides),
        }
        round_report = {
            "task": context.task.name,
            "domain": context.task.domain,
            "baseline_metric": context.baseline_metric,
            "best_metric": context.best_metric,
            "steps": [step_report],
        }
        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=ArchiveBundle(
                step_report=step_report,
                round_report=round_report,
                commit_intent="not recorded (phase 1)",
            ),
        )


EXPERTS.register(ArchiveReportExpert())

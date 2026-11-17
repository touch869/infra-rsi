"""Step/round report assembled from semantic experiment records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..knowledge.runtime.experiment_record import ExperimentRecord
from ..knowledge.runtime.record_store import ExperimentRecordStore

__all__ = ["ReportBuilder", "RoundReport", "StepReport"]


@dataclass(frozen=True)
class StepReport:
    """One candidate step as a report row."""

    record_id: str
    stage: str
    hypothesis_id: Optional[str]
    status: str
    metric: Optional[float]
    baseline_metric: Optional[float]
    detail: str
    gates: tuple[Mapping[str, Any], ...]
    commit: Optional[str]
    rollback: Optional[str]


@dataclass(frozen=True)
class RoundReport:
    """One round's baseline, best step, counts, and ordered steps."""

    round_id: str
    baseline_metric: Optional[float]
    best_record: Optional[ExperimentRecord]
    counts: Mapping[str, int]
    steps: tuple[StepReport, ...]

    def to_dict(self) -> dict[str, Any]:
        best = self.best_record
        return {
            "round_id": self.round_id,
            "baseline_metric": self.baseline_metric,
            "best": {
                "record_id": best.record_id if best else None,
                "hypothesis_id": best.hypothesis_id if best else None,
                "metric": best.metric if best else None,
            },
            "counts": dict(self.counts),
            "steps": [
                {
                    "record_id": step.record_id,
                    "stage": step.stage,
                    "hypothesis_id": step.hypothesis_id,
                    "status": step.status,
                    "metric": step.metric,
                    "baseline_metric": step.baseline_metric,
                    "detail": step.detail,
                    "gates": [dict(gate) for gate in step.gates],
                    "commit": step.commit,
                    "rollback": step.rollback,
                }
                for step in self.steps
            ],
        }


class ReportBuilder:
    """Build a round report from ``ExperimentRecordStore``."""

    def __init__(self, store: ExperimentRecordStore) -> None:
        self.store = store

    def build(self, round_id: str, *, maximize: bool = True) -> RoundReport:
        summary = self.store.summary(round_id, maximize=maximize)
        steps = tuple(
            StepReport(
                record_id=record.record_id,
                stage=record.stage,
                hypothesis_id=record.hypothesis_id,
                status=record.status,
                metric=record.metric,
                baseline_metric=record.baseline_metric,
                detail=record.detail,
                gates=record.gates,
                commit=record.commit,
                rollback=record.rollback,
            )
            for record in summary.steps
        )
        return RoundReport(
            round_id=summary.round_id,
            baseline_metric=summary.baseline_metric,
            best_record=summary.best_record,
            counts=summary.counts,
            steps=steps,
        )

    @staticmethod
    def render_markdown(report: RoundReport) -> str:
        def num(value: Optional[float], digits: int = 6) -> str:
            return "n/a" if value is None else f"{value:.{digits}g}"

        best = report.best_record
        lines = [
            f"# round {report.round_id}",
            "",
            f"- reference baseline: {num(report.baseline_metric)}",
            f"- best: {best.hypothesis_id if best else 'n/a'} = {num(best.metric if best else None)}",
            f"- counts: {dict(report.counts)}",
            "",
            "| step | stage | hypothesis | status | metric | detail |",
            "|---|---|---|---|---|---|",
        ]
        for step in report.steps:
            lines.append(
                f"| {step.record_id} | {step.stage} | {step.hypothesis_id or '-'} | "
                f"{step.status} | {num(step.metric)} | {step.detail} |"
            )
        lines.append("")
        return "\n".join(lines)

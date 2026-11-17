"""Report builder tests: round summary and markdown."""

from __future__ import annotations

from pathlib import Path

from irsi.knowledge import ExperimentRecord, ExperimentRecordStore
from irsi.reporting import ReportBuilder


def _record(step_id: int, *, status: str, metric: float | None, stage: str, hypothesis_id: str | None = None) -> ExperimentRecord:
    return ExperimentRecord(
        record_id="",
        round_id="round-1",
        step_id=step_id,
        stage=stage,
        hypothesis_id=hypothesis_id,
        overrides={"activation_checkpoint.mode": "off"} if hypothesis_id else {},
        baseline_metric=95.0,
        metric=metric,
        status=status,
        detail=f"{stage}: {status}",
        artifacts={},
    )


def test_report_builder_uses_calibrated_reference(tmp_path: Path):
    store = ExperimentRecordStore(tmp_path / "task")
    store.append(_record(0, status="baseline", metric=100.0, stage="baseline"))
    store.append(_record(1, status="baseline", metric=95.0, stage="baseline-observed"))
    store.append(_record(2, status="calibrated", metric=95.0, stage="calibrated"))
    store.append(_record(3, status="keep", metric=120.0, stage="judgment", hypothesis_id="layers-0"))
    store.append(_record(4, status="discard", metric=102.0, stage="judgment", hypothesis_id="layers-6"))
    store.append(_record(5, status="crash", metric=None, stage="judgment", hypothesis_id="layers-12"))

    report = ReportBuilder(store).build("round-1")
    assert report.baseline_metric == 95.0
    assert report.best_record is not None
    assert report.best_record.hypothesis_id == "layers-0"
    assert report.best_record.metric == 120.0
    assert report.counts["keep"] == 1
    assert report.counts["discard"] == 1
    assert report.counts["crash"] == 1

    text = ReportBuilder.render_markdown(report)
    assert "round round-1" in text
    assert "reference baseline: 95" in text
    assert "layers-0" in text
    assert "crash" in text

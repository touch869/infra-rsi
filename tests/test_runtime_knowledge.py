"""Runtime knowledge record store and reader."""

from __future__ import annotations

import json

import pytest

from irsi.knowledge import ExperimentRecord, ExperimentRecordStore, RuntimeKnowledgeReader


def _record(
    step_id: int,
    *,
    status: str,
    metric: float | None,
    stage: str = "judgment",
    hypothesis_id: str | None = None,
    gates: tuple[dict, ...] = (),
) -> ExperimentRecord:
    return ExperimentRecord(
        record_id="",
        round_id="round-1",
        step_id=step_id,
        stage=stage,
        surface="recompute",
        hypothesis_id=hypothesis_id,
        overrides={"activation_checkpoint.mode": "off"} if hypothesis_id else {},
        baseline_metric=100.0,
        metric=metric,
        status=status,
        detail=f"step {step_id}: {status}",
        artifacts={"log": f"trial-{step_id}.log"},
        gates=gates,
        evidence={"engaged": True},
    )


def test_store_append_and_query(tmp_path):
    store = ExperimentRecordStore(tmp_path / "task")
    baseline = store.append(
        _record(0, status="baseline", metric=100.0, stage="baseline")
    )
    kept = store.append(
        _record(
            1,
            status="keep",
            metric=120.0,
            hypothesis_id="layers-0",
            gates=({"name": "bitwise", "passed": True, "detail": "identical"},),
        )
    )
    discarded = store.append(_record(2, status="discard", metric=102.0, hypothesis_id="layers-6"))
    crashed = store.append(
        _record(
            3,
            status="crash",
            metric=None,
            hypothesis_id="layers-12",
            gates=({"name": "bitwise", "passed": False, "detail": "numeric mismatch"},),
        )
    )

    assert baseline.record_id == "round-1-0000"
    assert kept.record_id == "round-1-0001"
    assert baseline.timestamp
    assert store.records_path.read_text(encoding="utf-8").count("\n") == 4

    assert store.get("round-1-0001") == kept
    assert [record.status for record in store.recent(2)] == ["discard", "crash"]
    assert [record.hypothesis_id for record in store.query(status="keep")] == ["layers-0"]

    summary = store.summary("round-1")
    assert summary.baseline_metric == 100.0
    assert summary.best_record == kept
    assert summary.counts == {"baseline": 1, "keep": 1, "discard": 1, "crash": 1}
    assert [record.step_id for record in summary.steps] == [0, 1, 2, 3]


def test_reader_best_failures_and_bundle(tmp_path):
    store = ExperimentRecordStore(tmp_path / "task")
    store.append(_record(0, status="baseline", metric=100.0, stage="baseline"))
    store.append(_record(1, status="keep", metric=120.0, hypothesis_id="layers-0"))
    store.append(_record(2, status="discard", metric=102.0, hypothesis_id="layers-6"))
    store.append(_record(3, status="crash", metric=None, hypothesis_id="layers-12"))

    reader = RuntimeKnowledgeReader(store)

    best = reader.best(surface="recompute")
    assert best is not None
    assert best.metric == 120.0
    assert best.hypothesis_id == "layers-0"

    failures = reader.failures(surface="recompute")
    assert len(failures) == 1
    assert failures[0].status == "crash"

    bundle = reader.bundle(round_id="round-1", limit=2)
    assert [record.status for record in bundle.records] == ["discard", "crash"]
    assert bundle.best_record == best
    assert len(bundle.failures) == 1


def test_record_round_trip_and_optional_fields(tmp_path):
    store = ExperimentRecordStore(tmp_path / "task")
    original = store.append(_record(1, status="keep", metric=120.0, hypothesis_id="layers-0"))

    raw = json.loads(store.records_path.read_text(encoding="utf-8").splitlines()[0])
    rebuilt = ExperimentRecord.from_dict(raw)

    assert rebuilt == original
    assert rebuilt.commit is None
    assert rebuilt.rollback is None
    assert rebuilt.prompt_hash is None
    assert rebuilt.skill_ids == ()
    assert rebuilt.environment_snapshot == {}
    assert rebuilt.observation_patch == {}
    assert rebuilt.neutrality == {}
    assert rebuilt.report == {}


def test_calibrated_and_error_statuses(tmp_path):
    store = ExperimentRecordStore(tmp_path / "task")
    calibrated = store.append(
        _record(0, status="calibrated", metric=100.0, stage="calibrated")
    )
    env_error = store.append(
        _record(1, status="env_error", metric=None, stage="environment")
    )
    patch_error = store.append(
        _record(2, status="patch_error", metric=None, stage="observation")
    )

    assert calibrated.status == "calibrated"
    assert env_error.status == "env_error"
    assert patch_error.status == "patch_error"
    assert [record.status for record in store.recent(3)] == [
        "calibrated",
        "env_error",
        "patch_error",
    ]


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError, match="status"):
        ExperimentRecord(
            record_id="r",
            round_id="round-1",
            step_id=1,
            stage="judgment",
            status="unknown",
        )

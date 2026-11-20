"""Single-trial measurement freezes a baseline and rejects numerical drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from irsi.contract import (
    BudgetSpec,
    ContractLockError,
    GateSpec,
    InfraTaskSpec,
    MetricSpec,
    WorkloadSpec,
    confirm_contract,
    contract_hash,
    load_contract,
)
from irsi.execution.backends.base import TrialResult
from irsi.execution.metric_extractor import StepMetric, TrialMetrics
from irsi.measurement import MeasurementError, measure_current


def _spec() -> InfraTaskSpec:
    return InfraTaskSpec(
        name="measurement-test",
        repo_root="/repo",
        base_config="/repo/train.yaml",
        domain="recompute",
        writable_prefixes=("activation_checkpoint.",),
        metric=MetricSpec(warmup_steps=0, measured_steps=4),
        workload=WorkloadSpec(nproc=1, expect_steps=4),
        gates=(GateSpec("receipt"),),
        budget=BudgetSpec(max_trials=1, timeout_min=1),
    )


def _contract_file(tmp_path: Path) -> Path:
    path = tmp_path / "contract.yaml"
    path.write_text(
        yaml.safe_dump(_spec().to_dict(), sort_keys=False), encoding="utf-8"
    )
    return path


def _metrics(tps: float, *, loss: float = 1.0) -> TrialMetrics:
    rows = tuple(
        StepMetric(
            step=index + 1,
            loss=loss,
            grad_norm=2.0,
            step_time=1.0,
            tokens_per_second=tps,
            peak_mem_gib=1.0,
        )
        for index in range(4)
    )
    return TrialMetrics(steps=rows, exit_code=0)


class FakeBackend:
    name = "fake"

    def __init__(self, metrics: TrialMetrics) -> None:
        self.metrics = metrics

    def run(self, spec, trial_dir, overrides, label):  # noqa: ARG002
        path = Path(trial_dir)
        path.mkdir(parents=True, exist_ok=True)
        log = path / "run.log"
        log.write_text("fake log", encoding="utf-8")
        config = path / "train.yaml"
        config.write_text("fake config", encoding="utf-8")
        return TrialResult(
            label=label,
            backend=self.name,
            metrics=self.metrics,
            log_path=log,
            config_path=config,
            command="fake",
            elapsed_s=0.01,
        )


def test_measure_freezes_and_reuses_a_reference(tmp_path):
    spec = _spec()
    frozen = tmp_path / "baseline.json"
    first = measure_current(
        spec,
        FakeBackend(_metrics(100.0)),
        artifacts_dir=tmp_path / "measurements",
        freeze_baseline=frozen,
        label="baseline",
    )
    assert first.metric == 100.0
    assert frozen.is_file()
    assert (first.run_dir / "measurement.json").is_file()

    second = measure_current(
        spec,
        FakeBackend(_metrics(120.0)),
        artifacts_dir=tmp_path / "measurements",
        reference=frozen,
        label="candidate",
    )
    assert second.metric == 120.0
    assert second.payload["reference"]["passed"] is True


def test_measure_rejects_numerical_drift_from_reference(tmp_path):
    spec = _spec()
    frozen = tmp_path / "baseline.json"
    measure_current(
        spec,
        FakeBackend(_metrics(100.0)),
        artifacts_dir=tmp_path / "measurements",
        freeze_baseline=frozen,
    )

    with pytest.raises(MeasurementError, match="numeric mismatch"):
        measure_current(
            spec,
            FakeBackend(_metrics(100.0, loss=1.1)),
            artifacts_dir=tmp_path / "measurements",
            reference=frozen,
        )
    measurements = list((tmp_path / "measurements").glob("*/measurement.json"))
    assert measurements
    states = [
        json.loads((path.parent / "state.json").read_text(encoding="utf-8"))
        for path in measurements
    ]
    assert any(state["status"] == "REJECTED" for state in states)


def test_measure_rejects_a_reference_from_another_contract(tmp_path):
    frozen = tmp_path / "baseline.json"
    measure_current(
        _spec(),
        FakeBackend(_metrics(100.0)),
        artifacts_dir=tmp_path / "measurements",
        freeze_baseline=frozen,
    )
    other = _spec()
    other = InfraTaskSpec(**{**other.__dict__, "name": "other-task"})

    with pytest.raises(MeasurementError, match="belongs to"):
        measure_current(
            other,
            FakeBackend(_metrics(100.0)),
            artifacts_dir=tmp_path / "measurements",
            reference=frozen,
        )


def test_measure_requires_a_confirmed_contract_before_freezing_baseline(tmp_path):
    contract = _contract_file(tmp_path)
    spec = load_contract(contract)
    with pytest.raises(ContractLockError, match="not confirmed"):
        measure_current(
            spec,
            FakeBackend(_metrics(100.0)),
            artifacts_dir=tmp_path / "measurements",
            contract_path=contract,
            require_confirmed=True,
        )


def test_confirmed_measurement_records_contract_hash_and_lock(tmp_path):
    contract = _contract_file(tmp_path)
    spec = load_contract(contract)
    digest = contract_hash(spec)
    confirm_contract(
        contract,
        confirmation_code=digest[:12],
        statement="确认该评估边界，baseline 后不再修改。",
        confirmed_by="user",
    )

    measurement = measure_current(
        spec,
        FakeBackend(_metrics(100.0)),
        artifacts_dir=tmp_path / "measurements",
        contract_path=contract,
        require_confirmed=True,
        freeze_baseline=tmp_path / "baseline.json",
        label="baseline",
    )
    assert measurement.payload["contract_hash"] == digest
    assert measurement.payload["contract_lock"]["statement"].startswith("确认该评估边界")
    frozen = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    assert frozen["contract_hash"] == digest
    assert frozen["contract_lock"]["contract_hash"] == digest


def test_changed_contract_is_rejected_before_a_new_measurement(tmp_path):
    contract = _contract_file(tmp_path)
    spec = load_contract(contract)
    confirm_contract(
        contract,
        confirmation_code=contract_hash(spec)[:12],
        statement="确认冻结。",
    )
    raw = yaml.safe_load(contract.read_text(encoding="utf-8"))
    raw["workload"]["nproc"] = 2
    contract.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractLockError, match="changed after confirmation"):
        measure_current(
            load_contract(contract),
            FakeBackend(_metrics(100.0)),
            artifacts_dir=tmp_path / "measurements",
            contract_path=contract,
            require_confirmed=True,
        )

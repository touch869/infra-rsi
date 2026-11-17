"""Orchestration: observation, observed baseline, candidate loop, records."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from irsi.contract import BudgetSpec, load_contract
from irsi.execution.backends.base import TrialResult
from irsi.execution.metric_extractor import StepMetric, TrialMetrics
from irsi.knowledge.runtime.record_store import ExperimentRecordStore
from irsi.orchestration import Orchestrator, RoundController, RoundState, Stage, StagePolicyError
from irsi.runtime.facade import RuntimeFacade

TASK_PATH = Path(__file__).resolve().parents[1] / "examples/specs/hyperparallel-recompute.yaml"
TASK = load_contract(TASK_PATH)


def _metrics(tps: float, *, loss: float = 1.0, grad_norm: float = 2.0) -> TrialMetrics:
    rows = tuple(
        StepMetric(
            step=i + 1,
            loss=loss,
            grad_norm=grad_norm,
            step_time=1.0,
            tokens_per_second=tps,
            peak_mem_gib=10.0,
        )
        for i in range(32)
    )
    return TrialMetrics(steps=rows, exit_code=0)


class FakeBackend:
    name = "fake"

    def __init__(self, metrics):
        self._metrics = list(metrics)
        self.calls: list[tuple[str, dict]] = []

    def run(self, spec, trial_dir, overrides, label):  # noqa: ARG002
        path = Path(trial_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "run.log").write_text("fake log", encoding="utf-8")
        config = path / "train.yaml"
        config.write_text("fake config", encoding="utf-8")
        self.calls.append((label, dict(overrides)))
        return TrialResult(
            label=label,
            backend=self.name,
            metrics=self._metrics.pop(0),
            log_path=path / "run.log",
            config_path=config,
            command="fake",
            elapsed_s=0.01,
        )


def test_round_controller_uses_observed_baseline_and_one_candidate(tmp_path):
    task = replace(TASK, budget=BudgetSpec(max_trials=1))
    backend = FakeBackend([_metrics(100.0), _metrics(100.0), _metrics(120.0)])
    store = ExperimentRecordStore(tmp_path / "task")

    controller = RoundController(task, backend, tmp_path / "runs", store=store)
    state = controller.run_round("round-1")

    assert state.stage == Stage.DONE
    assert state.trials_run == 1
    assert state.best_metric == pytest.approx(120.0)
    assert state.baseline_metric == pytest.approx(100.0)
    assert backend.calls[0][0] == "baseline-clean"
    assert backend.calls[1][0] == "baseline-observed"
    assert backend.calls[2][0] == "layers-0"

    records = store.recent(10, round_id="round-1")
    assert [record.status for record in records] == [
        "baseline",
        "baseline",
        "calibrated",
        "keep",
    ]
    assert records[2].neutrality["overhead"] == pytest.approx(0.0)
    assert records[3].metric == pytest.approx(120.0)


def test_orchestrator_rejects_wrong_start_stage(tmp_path):
    backend = FakeBackend([_metrics(100.0)])
    facade = RuntimeFacade(TASK, backend, tmp_path / "runs")
    orchestrator = Orchestrator(TASK, facade)

    with pytest.raises(StagePolicyError, match="CALIBRATED"):
        orchestrator.run_round(RoundState(round_id="round-1", stage=Stage.DECISION))


def test_budget_is_enforced(tmp_path):
    task = replace(TASK, budget=BudgetSpec(max_trials=1))
    backend = FakeBackend([_metrics(100.0), _metrics(100.0), _metrics(120.0)])
    store = ExperimentRecordStore(tmp_path / "task")

    controller = RoundController(task, backend, tmp_path / "runs", store=store)
    state = controller.run_round("round-1")

    assert state.trials_run == 1
    assert state.stop_reason == "budget_exhausted"

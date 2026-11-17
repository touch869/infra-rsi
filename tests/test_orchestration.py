"""Orchestration: observation, observed baseline, candidate loop, records."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from irsi.contract import BudgetSpec, load_contract
from irsi.environment import EnvironmentRepairAgent
from irsi.execution.backends.base import TrialResult
from irsi.execution.metric_extractor import StepMetric, TrialMetrics
from irsi.git import CommitRecorder
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


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


class FailingBackend(FakeBackend):
    """Raise on the first candidate trial to exercise crash recording."""

    def run(self, spec, trial_dir, overrides, label):
        if label == "layers-0":
            raise RuntimeError("out of memory during candidate trial")
        return super().run(spec, trial_dir, overrides, label)


class FlakyEnvBackend(FakeBackend):
    """Fail the first clean baseline with an environment error, then recover."""

    def __init__(self, metrics):
        super().__init__(metrics)
        self.failed = False

    def run(self, spec, trial_dir, overrides, label):
        if not self.failed:
            self.failed = True
            raise OSError("missing dependency")
        return super().run(spec, trial_dir, overrides, label)


class FakePatchManager:
    """No-op patch manager for failure-path tests."""

    def apply(self, patch):
        self.applied = patch

    def revert(self, patch):
        self.reverted = patch


class ObservedFailingBackend(FakeBackend):
    """Fail the observed baseline to exercise patch-error recording."""

    def run(self, spec, trial_dir, overrides, label):
        if label == "baseline-observed":
            raise RuntimeError("observation patch failed")
        return super().run(spec, trial_dir, overrides, label)


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


def test_execution_failure_is_recorded_as_crash(tmp_path):
    task = replace(TASK, budget=BudgetSpec(max_trials=1))
    backend = FailingBackend([_metrics(100.0), _metrics(100.0)])
    store = ExperimentRecordStore(tmp_path / "task")

    controller = RoundController(task, backend, tmp_path / "runs", store=store)
    state = controller.run_round("round-1")

    assert state.stage == Stage.DONE
    assert state.trials_run == 1

    records = store.recent(10, round_id="round-1")
    crash = records[-1]
    assert crash.status == "crash"
    assert crash.metric is None
    assert "execution error" in crash.detail
    assert crash.rollback == "not_committed"


def test_commit_recorder_is_wired_for_keep(tmp_path):
    task = replace(TASK, budget=BudgetSpec(max_trials=1))
    task_dir = tmp_path / "task"
    backend = FakeBackend([_metrics(100.0), _metrics(100.0), _metrics(120.0)])
    store = ExperimentRecordStore(task_dir)
    recorder = CommitRecorder(task_dir)
    recorder.ensure_repo()
    _git(task_dir, "config", "user.email", "test@example.com")
    _git(task_dir, "config", "user.name", "Test")

    controller = RoundController(
        task,
        backend,
        task_dir,
        store=store,
        commit_recorder=recorder,
    )
    state = controller.run_round("round-1")

    assert state.stage == Stage.DONE
    report = task_dir / "step_reports" / "step-0003.json"
    assert report.is_file()
    tracked = _git(task_dir, "ls-files")
    assert "environment_report.json" in tracked
    assert "calibration.json" in tracked
    assert "step_reports/step-0003.json" in tracked
    assert "trials/layers-0/train.yaml" in tracked
    assert _git(task_dir, "log", "--oneline").strip()


def test_environment_repair_retries_clean_baseline(tmp_path):
    task = replace(TASK, env_setup="true", budget=BudgetSpec(max_trials=1))
    backend = FlakyEnvBackend([_metrics(100.0), _metrics(100.0), _metrics(120.0)])
    store = ExperimentRecordStore(tmp_path / "task")

    controller = RoundController(
        task,
        backend,
        tmp_path / "runs",
        store=store,
        repair_agent=EnvironmentRepairAgent(task),
    )
    state = controller.run_round("round-1")

    assert state.stage == Stage.DONE
    assert state.best_metric == pytest.approx(120.0)
    records = store.recent(10, round_id="round-1")
    env = records[0]
    assert env.stage == "environment"
    assert env.status == "env_error"
    assert env.environment_action["success"] is True
    assert records[-1].status == "keep"


def test_observed_baseline_failure_is_recorded_as_patch_error(tmp_path):
    task = replace(
        TASK,
        domain_params={
            **dict(TASK.domain_params),
            "observation_patch": {
                "target_files": ["train.py"],
                "diff": "diff --git a/train.py b/train.py\n",
            },
        },
        budget=BudgetSpec(max_trials=1),
    )
    backend = ObservedFailingBackend([_metrics(100.0)])
    store = ExperimentRecordStore(tmp_path / "task")
    patch_manager = FakePatchManager()

    controller = RoundController(
        task,
        backend,
        tmp_path / "runs",
        store=store,
        patch_manager=patch_manager,
    )
    state = controller.run_round("round-1")

    assert state.stage == Stage.FAILED
    assert state.stop_reason == "observation_unrecoverable"

    records = store.recent(10, round_id="round-1")
    observation = records[-1]
    assert observation.stage == "observation"
    assert observation.status == "patch_error"
    assert observation.observation_patch["target_files"] == ["train.py"]
    assert patch_manager.reverted.diff

"""Five expert roles and the deterministic execution stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from irsi.contract import load_contract
from irsi.environment import EnvironmentSnapshot
from irsi.experts import (
    ArchiveBundle,
    ArchiveReportExpert,
    CandidateSpec,
    DecisionExpert,
    DevelopmentExpert,
    EnvironmentExpert,
    EXPERTS,
    HypothesisSet,
    JudgmentExpert,
    ObservationExpert,
    ObservationPlan,
)
from irsi.execution.backends.base import TrialResult
from irsi.execution.metric_extractor import StepMetric, TrialMetrics
from irsi.execution.stage import ExecutionStage
from irsi.prompting import PROMPTS, SkillView, StageContext
from irsi.runtime.calibration import BaselineCalibrator
from irsi.runtime.facade import RuntimeFacade
from irsi.runtime.native_prompt_runtime import NativePromptRuntime

TASK_PATH = Path(__file__).resolve().parents[1] / "examples/specs/hyperparallel-recompute.yaml"
TASK = load_contract(TASK_PATH)


def _metrics(
    tps: float,
    *,
    loss: float = 1.0,
    grad_norm: float = 2.0,
    steps: int = 32,
    exit_code: int = 0,
) -> TrialMetrics:
    rows = tuple(
        StepMetric(
            step=i + 1,
            loss=loss,
            grad_norm=grad_norm,
            step_time=1.0,
            tokens_per_second=tps,
            peak_mem_gib=10.0,
        )
        for i in range(steps)
    )
    return TrialMetrics(steps=rows, exit_code=exit_code)


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


def test_six_experts_and_prompts_are_registered():
    expected = [
        "archive_report",
        "decision",
        "development",
        "environment",
        "judgment",
        "observation",
    ]
    assert EXPERTS.names() == expected
    assert PROMPTS.names() == expected
    for name in expected:
        assert EXPERTS.get(name).stage == name
        assert PROMPTS.get(name).stage == name


def test_full_expert_pipeline(tmp_path):
    backend = FakeBackend([_metrics(100.0), _metrics(120.0)])
    facade = RuntimeFacade(TASK, backend, tmp_path / "runs")

    baseline = facade.execute_trial({}, "baseline")
    baseline_metric = facade.metric_value(baseline)
    assert baseline_metric == pytest.approx(100.0)

    decision = DecisionExpert().run(
        StageContext(task=TASK, stage="decision", baseline_metric=baseline_metric),
        facade,
    )
    assert isinstance(decision.artifact, HypothesisSet)
    assert decision.artifact.hypotheses[0].id == "layers-0"

    development = DevelopmentExpert().run(
        StageContext(
            task=TASK,
            stage="development",
            previous_artifact=decision.artifact,
            baseline_metric=baseline_metric,
            best_metric=baseline_metric,
            baseline_trial=baseline,
            best_trial=baseline,
        ),
        facade,
    )
    assert isinstance(development.artifact, CandidateSpec)
    assert development.artifact.hypothesis_id == "layers-0"

    # Observation is task-level and does not depend on a candidate.
    observation = ObservationExpert().run(
        StageContext(task=TASK, stage="observation"),
        facade,
    )
    assert isinstance(observation.artifact, ObservationPlan)
    assert observation.artifact.metric_key == TASK.metric.key
    assert observation.artifact.scope == "task"
    assert observation.artifact.calibrate_baseline is True
    assert observation.artifact.instrumentation_patch.is_empty

    execution = ExecutionStage().run(
        StageContext(
            task=TASK,
            stage="execution",
            previous_artifact=observation.artifact,
            candidate=development.artifact,
            baseline_trial=baseline,
        ),
        facade,
    )
    assert execution.trial.label == "layers-0"

    judgment = JudgmentExpert().run(
        StageContext(
            task=TASK,
            stage="judgment",
            previous_artifact=execution,
            baseline_metric=baseline_metric,
            best_metric=baseline_metric,
            baseline_trial=baseline,
            best_trial=baseline,
            recent_decisions=(),
        ),
        facade,
    )
    assert judgment.artifact.status == "keep"
    assert judgment.artifact.delta_vs_best == pytest.approx(0.2)

    archive = ArchiveReportExpert().run(
        StageContext(
            task=TASK,
            stage="archive_report",
            previous_artifact=judgment.artifact,
            baseline_metric=baseline_metric,
            best_metric=baseline_metric,
        ),
        facade,
    )
    assert isinstance(archive.artifact, ArchiveBundle)
    assert archive.artifact.step_report["status"] == "keep"
    assert archive.artifact.step_report["metric"] == pytest.approx(120.0)
    assert archive.artifact.step_report["gates"][1]["name"] == "bitwise"
    assert backend.calls == [("baseline", {}), ("layers-0", development.artifact.overrides)]


def test_judgment_crash_on_bitwise_mismatch(tmp_path):
    backend = FakeBackend([_metrics(100.0), _metrics(130.0, loss=9.9)])
    facade = RuntimeFacade(TASK, backend, tmp_path / "runs")
    baseline = facade.execute_trial({}, "baseline")

    execution = ExecutionStage().run(
        StageContext(
            task=TASK,
            stage="execution",
            previous_artifact=CandidateSpec(
                hypothesis_id="layers-0",
                description="test",
                overrides={
                    "activation_checkpoint.mode": "selective",
                    "activation_checkpoint.selection.source": "model_adapter_safe_regions",
                    "activation_checkpoint.selection.layer_count": 0,
                },
            ),
        ),
        facade,
    )

    judgment = JudgmentExpert().run(
        StageContext(
            task=TASK,
            stage="judgment",
            previous_artifact=execution,
            baseline_metric=100.0,
            best_metric=100.0,
            baseline_trial=baseline,
            best_trial=baseline,
        ),
        facade,
    )
    assert judgment.artifact.status == "crash"
    assert "bitwise" in judgment.artifact.detail


def test_judgment_discard_inside_noise_band(tmp_path):
    backend = FakeBackend([_metrics(100.0), _metrics(102.0)])
    facade = RuntimeFacade(TASK, backend, tmp_path / "runs")
    baseline = facade.execute_trial({}, "baseline")

    execution = ExecutionStage().run(
        StageContext(
            task=TASK,
            stage="execution",
            previous_artifact=CandidateSpec(
                hypothesis_id="layers-0",
                description="test",
                overrides={
                    "activation_checkpoint.mode": "selective",
                    "activation_checkpoint.selection.source": "model_adapter_safe_regions",
                    "activation_checkpoint.selection.layer_count": 0,
                },
            ),
        ),
        facade,
    )

    judgment = JudgmentExpert().run(
        StageContext(
            task=TASK,
            stage="judgment",
            previous_artifact=execution,
            baseline_metric=100.0,
            best_metric=100.0,
            baseline_trial=baseline,
            best_trial=baseline,
        ),
        facade,
    )
    assert judgment.artifact.status == "discard"


def test_baseline_calibration_detects_observation_overhead(tmp_path):
    clean_backend = FakeBackend([_metrics(100.0)])
    observed_backend = FakeBackend([_metrics(95.0)])
    clean_facade = RuntimeFacade(TASK, clean_backend, tmp_path / "clean")
    observed_facade = RuntimeFacade(TASK, observed_backend, tmp_path / "observed")

    clean = clean_facade.execute_trial({}, "baseline-clean")
    observed = observed_facade.execute_trial({}, "baseline-observed")
    calibration = BaselineCalibrator().calibrate(TASK, clean, observed)

    assert calibration.neutrality.clean_metric == pytest.approx(100.0)
    assert calibration.neutrality.observed_metric == pytest.approx(95.0)
    assert calibration.neutrality.overhead == pytest.approx(-0.05)
    assert calibration.neutrality.numeric_identical is True
    assert calibration.reference.metric == pytest.approx(95.0)
    assert calibration.reference.trial.label == "baseline-observed"
    assert calibration.clean.label == "baseline-clean"
    assert calibration.observed.label == "baseline-observed"


def test_baseline_reference_is_observed_inside_noise(tmp_path):
    clean_backend = FakeBackend([_metrics(100.0)])
    observed_backend = FakeBackend([_metrics(101.0)])
    clean_facade = RuntimeFacade(TASK, clean_backend, tmp_path / "clean")
    observed_facade = RuntimeFacade(TASK, observed_backend, tmp_path / "observed")

    clean = clean_facade.execute_trial({}, "baseline-clean")
    observed = observed_facade.execute_trial({}, "baseline-observed")
    calibration = BaselineCalibrator().calibrate(TASK, clean, observed)

    assert calibration.neutrality.overhead == pytest.approx(0.01)
    assert calibration.reference.metric == pytest.approx(101.0)
    assert calibration.reference.trial.label == "baseline-observed"


def test_environment_expert_returns_snapshot(tmp_path):
    facade = RuntimeFacade(TASK, FakeBackend([_metrics(100.0)]), tmp_path / "runs")
    result = EnvironmentExpert().run(
        StageContext(task=TASK, stage="environment"), facade
    )
    assert isinstance(result.artifact, EnvironmentSnapshot)
    assert result.artifact.python
    assert result.artifact.repo_root == TASK.repo_root


def test_native_prompt_runtime_records_provenance(tmp_path):
    backend = FakeBackend([_metrics(100.0)])
    facade = RuntimeFacade(TASK, backend, tmp_path / "runs")
    skill = SkillView(
        id="hp/recompute-layerwise",
        version=1,
        title="Layerwise recompute",
        when_to_use="When per-layer checkpointing is available.",
        excerpt="Use activation_checkpoint.selection.layer_count to choose a layer ladder.",
        manifest={"framework": "hyperparallel", "surface": "recompute"},
    )
    context = StageContext(task=TASK, stage="decision", baseline_metric=100.0)

    result = NativePromptRuntime().run(
        DecisionExpert(), context, (skill,), facade
    )

    assert isinstance(result.artifact, HypothesisSet)
    assert result.prompt_hash
    assert result.used_skills == ("hp/recompute-layerwise",)


def test_judgment_requires_baseline_trial(tmp_path):
    facade = RuntimeFacade(TASK, FakeBackend([_metrics(100.0), _metrics(120.0)]), tmp_path / "runs")
    execution = ExecutionStage().run(
        StageContext(
            task=TASK,
            stage="execution",
            previous_artifact=CandidateSpec(
                hypothesis_id="layers-0",
                description="test",
                overrides={
                    "activation_checkpoint.mode": "selective",
                    "activation_checkpoint.selection.source": "model_adapter_safe_regions",
                    "activation_checkpoint.selection.layer_count": 0,
                },
            ),
        ),
        facade,
    )
    with pytest.raises(ValueError, match="baseline_trial"):
        JudgmentExpert().run(
            StageContext(
                task=TASK,
                stage="judgment",
                previous_artifact=execution,
                baseline_metric=100.0,
                best_metric=100.0,
            ),
            facade,
        )

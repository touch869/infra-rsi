"""Round lifecycle: observation, baseline calibration, then candidate orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contract import InfraTaskSpec
from ..environment.snapshot import EnvironmentSnapshot
from ..experts.observation.expert import ObservationExpert
from ..knowledge.reader import SkillResolver
from ..knowledge.runtime.experiment_record import ExperimentRecord
from ..knowledge.runtime.reader import RuntimeKnowledgeReader
from ..knowledge.runtime.record_store import ExperimentRecordStore
from ..prompting import StageContext
from ..execution.trial_executor import TrialExecutor
from ..runtime.calibration import BaselineCalibrator
from ..runtime.facade import RuntimeFacade
from ..runtime.observation_patch import ObservationPatchManager
from .context_builder import ContextBuilder
from .orchestrator import Orchestrator
from .state import RoundState, Stage

__all__ = ["RoundController"]


class RoundController:
    """One round: task-level observation, observed baseline, then candidates."""

    def __init__(
        self,
        task: InfraTaskSpec,
        backend: object,
        root: str | Path,
        *,
        store: ExperimentRecordStore | None = None,
        reader: RuntimeKnowledgeReader | None = None,
        resolver: SkillResolver | None = None,
        patch_manager: ObservationPatchManager | None = None,
        runtime: Any | None = None,
    ) -> None:
        self.task = task
        self.backend = backend
        self.root = Path(root)
        self.store = store
        self.reader = reader or (
            RuntimeKnowledgeReader(store) if store is not None else None
        )
        self.resolver = resolver
        self.patch_manager = patch_manager
        self.runtime = runtime

    def run_round(self, round_id: str = "round-1") -> RoundState:
        executor = TrialExecutor(self.task, self.backend)
        snapshot = EnvironmentSnapshot.capture(self.task)
        clean_facade = RuntimeFacade(
            self.task, self.backend, self.root / "baseline-clean", executor=executor
        )
        observed_facade = RuntimeFacade(
            self.task, self.backend, self.root / "baseline-observed", executor=executor
        )
        candidate_facade = RuntimeFacade(
            self.task, self.backend, self.root / "trials", executor=executor
        )

        # Observation is task-level and independent of any hypothesis.
        observation_expert = ObservationExpert()
        observation_context = StageContext(task=self.task, stage="observation")
        if self.runtime is None:
            observation_result = observation_expert.run(
                observation_context, observed_facade
            )
        else:
            observation_result = self.runtime.run(
                observation_expert, observation_context, (), observed_facade
            )
        plan = observation_result.artifact

        # Clean baseline is the control; observed baseline is the reference.
        clean = clean_facade.execute_trial({}, "baseline-clean")
        if not plan.instrumentation_patch.is_empty:
            if self.patch_manager is None:
                raise ValueError(
                    "non-empty ObservationPatch requires an ObservationPatchManager"
                )
            self.patch_manager.apply(plan.instrumentation_patch)
        observed = observed_facade.execute_trial({}, "baseline-observed")
        calibration = BaselineCalibrator().calibrate(self.task, clean, observed)
        reference = calibration.reference.trial
        reference_metric = calibration.reference.metric

        if self.store is not None:
            self.store.append(
                ExperimentRecord(
                    record_id="",
                    round_id=round_id,
                    step_id=0,
                    stage="baseline",
                    metric=calibration.neutrality.clean_metric,
                    status="baseline",
                    detail="clean baseline (observation off)",
                    environment_snapshot=snapshot.to_dict(),
                    artifacts={
                        "config": str(calibration.clean.config_path),
                        "log": str(calibration.clean.log_path),
                    },
                )
            )
            self.store.append(
                ExperimentRecord(
                    record_id="",
                    round_id=round_id,
                    step_id=1,
                    stage="baseline-observed",
                    metric=calibration.neutrality.observed_metric,
                    status="baseline",
                    detail="observed baseline (observation on)",
                    artifacts={
                        "config": str(calibration.observed.config_path),
                        "log": str(calibration.observed.log_path),
                    },
                    observation_patch={
                        "target_files": list(plan.instrumentation_patch.target_files),
                        "diff": plan.instrumentation_patch.diff,
                        "apply_before_baseline": plan.instrumentation_patch.apply_before_baseline,
                    },
                )
            )
            self.store.append(
                ExperimentRecord(
                    record_id="",
                    round_id=round_id,
                    step_id=2,
                    stage="calibrated",
                    metric=reference_metric,
                    status="calibrated",
                    detail="reference = observed baseline",
                    baseline_metric=reference_metric,
                    neutrality={
                        "clean_metric": calibration.neutrality.clean_metric,
                        "observed_metric": calibration.neutrality.observed_metric,
                        "overhead": calibration.neutrality.overhead,
                        "numeric_identical": calibration.neutrality.numeric_identical,
                        "peak_mem_delta": calibration.neutrality.peak_mem_delta,
                    },
                )
            )

        state = RoundState(
            round_id=round_id,
            stage=Stage.CALIBRATED,
            baseline_trial=reference,
            best_trial=reference,
            baseline_metric=reference_metric,
            best_metric=reference_metric,
            observation_plan=plan,
        )

        builder = ContextBuilder(
            self.task, reader=self.reader, resolver=self.resolver
        )
        orchestrator = Orchestrator(
            self.task,
            candidate_facade,
            store=self.store,
            builder=builder,
            runtime=self.runtime,
        )
        return orchestrator.run_round(state, observation_plan=plan)

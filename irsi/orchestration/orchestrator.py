"""Code-enforced candidate-stage orchestrator for one round."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..contract import InfraTaskSpec
from ..execution.stage import ExecutionStage
from ..experts import EXPERTS
from ..experts.artifacts import CandidateSpec, Judgment
from ..knowledge.runtime.experiment_record import ExperimentRecord
from ..knowledge.runtime.record_store import ExperimentRecordStore
from ..runtime.facade import RuntimeFacade
from .context_builder import ContextBuilder
from .policy import StagePolicyError, require_artifact
from .state import RoundState, Stage

__all__ = ["Orchestrator"]


def _error_status(exc: Exception) -> str:
    """Classify an execution failure as crash vs environment error."""
    text = str(exc).lower()
    if isinstance(exc, (OSError, EnvironmentError)):
        return "env_error"
    if "out of memory" in text or "oom" in text:
        return "crash"
    return "crash"


class Orchestrator:
    """Run decision → development → execution → judgment → archive per candidate."""

    def __init__(
        self,
        task: InfraTaskSpec,
        facade: RuntimeFacade,
        *,
        store: ExperimentRecordStore | None = None,
        builder: ContextBuilder | None = None,
    ) -> None:
        self.task = task
        self.facade = facade
        self.store = store
        self.builder = builder or ContextBuilder(task)
        self.execution = ExecutionStage()

    def run_round(
        self,
        state: RoundState,
        observation_plan: Any = None,
    ) -> RoundState:
        """Advance from CALIBRATED to DONE, enforcing stage order and budget."""
        if state.stage != Stage.CALIBRATED:
            raise StagePolicyError(
                f"round must start at CALIBRATED, got {state.stage.value!r}"
            )
        state = replace(state, observation_plan=observation_plan)

        # DECISION: one HypothesisSet per round.
        context, _skills = self.builder.build(state, Stage.DECISION)
        decision_result = EXPERTS.get("decision").run(context, self.facade)
        require_artifact(Stage.DECISION, decision_result.artifact)
        hypotheses = decision_result.artifact.hypotheses
        state = replace(
            state,
            stage=Stage.DECISION,
            hypotheses=hypotheses,
            previous_artifact=decision_result.artifact,
        )

        if not hypotheses:
            return replace(state, stage=Stage.DONE, stop_reason="no_hypotheses")

        for index, hypothesis in enumerate(hypotheses):
            if state.trials_run >= self.task.budget.max_trials:
                return replace(state, stage=Stage.DONE, stop_reason="budget_exhausted")

            # DEVELOPMENT: contract-approved CandidateSpec.
            context, _skills = self.builder.build(
                state, Stage.DEVELOPMENT, candidate=hypothesis
            )
            development_result = EXPERTS.get("development").run(context, self.facade)
            require_artifact(Stage.DEVELOPMENT, development_result.artifact)
            candidate = development_result.artifact
            state = replace(
                state,
                stage=Stage.DEVELOPMENT,
                current_candidate=candidate,
                previous_artifact=development_result.artifact,
                candidate_index=index,
            )

            # EXECUTION: deterministic runtime, no agent.
            context, _skills = self.builder.build(
                state, Stage.EXECUTION, candidate=candidate
            )
            try:
                execution = self.execution.run(context, self.facade)
            except Exception as exc:  # noqa: BLE001 - a failed trial is evidence
                judgment = Judgment(
                    trial=f"{candidate.hypothesis_id}-failed",
                    status="crash",
                    metric=None,
                    baseline_metric=state.baseline_metric,
                    best_before=state.best_metric,
                    delta_vs_best=None,
                    gates=(),
                    detail=f"execution error: {exc}",
                    overrides=dict(candidate.overrides),
                )
                state = replace(
                    state,
                    stage=Stage.EXECUTION,
                    previous_artifact=judgment,
                    trials_run=state.trials_run + 1,
                )
                context, _skills = self.builder.build(state, Stage.ARCHIVE)
                archive_result = EXPERTS.get("archive_report").run(context, self.facade)
                require_artifact(Stage.ARCHIVE, archive_result.artifact)
                state = replace(
                    state,
                    stage=Stage.ARCHIVE,
                    previous_artifact=archive_result.artifact,
                )
                self._record(
                    state,
                    candidate,
                    None,
                    judgment,
                    rollback="not_committed",
                    status=_error_status(exc),
                )
                state = replace(state, stage=Stage.NEXT_CANDIDATE)
                continue

            require_artifact(Stage.EXECUTION, execution)
            state = replace(
                state,
                stage=Stage.EXECUTION,
                previous_artifact=execution,
                trials_run=state.trials_run + 1,
            )

            # JUDGMENT: gates + observed baseline.
            context, _skills = self.builder.build(
                state, Stage.JUDGMENT, candidate=candidate
            )
            judgment_result = EXPERTS.get("judgment").run(context, self.facade)
            require_artifact(Stage.JUDGMENT, judgment_result.artifact)
            judgment = judgment_result.artifact
            state = replace(
                state,
                stage=Stage.JUDGMENT,
                previous_artifact=judgment,
            )

            # ARCHIVE: step report payload.
            context, _skills = self.builder.build(state, Stage.ARCHIVE)
            archive_result = EXPERTS.get("archive_report").run(context, self.facade)
            require_artifact(Stage.ARCHIVE, archive_result.artifact)
            state = replace(
                state,
                stage=Stage.ARCHIVE,
                previous_artifact=archive_result.artifact,
            )

            self._record(state, candidate, execution, judgment)

            if judgment.status == "keep":
                state = replace(
                    state,
                    best_trial=execution.trial,
                    best_metric=judgment.metric,
                )

            state = replace(state, stage=Stage.NEXT_CANDIDATE)

        return replace(
            state,
            stage=Stage.DONE,
            stop_reason=(
                "budget_exhausted"
                if state.trials_run >= self.task.budget.max_trials
                else "no_candidates"
            ),
        )

    def _record(
        self,
        state: RoundState,
        candidate: CandidateSpec,
        execution: Any | None,
        judgment: Judgment,
        *,
        rollback: str | None = None,
        status: str | None = None,
    ) -> None:
        if self.store is None:
            return
        gates = tuple(
            {"name": gate.name, "passed": gate.passed, "detail": gate.detail}
            for gate in judgment.gates
        )
        artifacts: dict[str, str] = {}
        evidence: dict[str, Any] = {}
        if execution is not None:
            artifacts = {
                "config": str(execution.trial.config_path),
                "log": str(execution.trial.log_path),
            }
            evidence = {
                "peak_mem_gib": execution.trial.metrics.peak_mem_gib,
                "numeric_hash": execution.trial.metrics.numeric_hash,
            }
        self.store.append(
            ExperimentRecord(
                record_id="",
                round_id=state.round_id,
                step_id=state.trials_run + 2,
                stage="judgment",
                hypothesis_id=candidate.hypothesis_id,
                overrides=dict(candidate.overrides),
                metric=judgment.metric,
                status=status or judgment.status,
                detail=judgment.detail,
                baseline_metric=state.baseline_metric,
                gates=gates,
                artifacts=artifacts,
                evidence=evidence,
                rollback=rollback,
            )
        )

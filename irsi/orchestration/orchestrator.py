"""Code-enforced candidate-stage orchestrator for one round."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..contract import InfraTaskSpec
from ..execution.stage import ExecutionStage
from ..experts import EXPERTS
from ..experts.artifacts import CandidateSpec, Judgment
from ..git.commit_recorder import CommitRecorder
from ..knowledge.runtime.experiment_record import ExperimentRecord
from ..knowledge.runtime.record_store import ExperimentRecordStore
from ..runtime.candidate_patch import CandidatePatchManager
from ..runtime.facade import RuntimeFacade
from .context_builder import ContextBuilder
from .policy import StagePolicyError, require_artifact
from .state import RoundState, Stage, advance

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
    """Run decision → development → execution → judgment → archive per candidate.

    A failed execution may re-enter DEVELOPMENT for a bounded repair attempt
    (``budget.max_repairs``). The orchestrator owns the loop, the patch
    apply/revert, the commit, and the ledger write; experts only produce
    artifacts.
    """

    def __init__(
        self,
        task: InfraTaskSpec,
        facade: RuntimeFacade,
        *,
        store: ExperimentRecordStore | None = None,
        builder: ContextBuilder | None = None,
        runtime: Any | None = None,
        commit_recorder: CommitRecorder | None = None,
        report_root: str | Path | None = None,
    ) -> None:
        self.task = task
        self.facade = facade
        self.store = store
        self.builder = builder or ContextBuilder(task)
        self.runtime = runtime
        self.commit_recorder = commit_recorder
        self.report_root = (
            Path(report_root)
            if report_root is not None
            else (store.root if store is not None else None)
        )
        self.execution = ExecutionStage()
        self.patch_manager = CandidatePatchManager(task.repo_root)

    def _run_expert(self, name: str, context: Any, skills: tuple[Any, ...]) -> Any:
        expert = EXPERTS.get(name)
        if self.runtime is None:
            return expert.run(context, self.facade)
        return self.runtime.run(expert, context, skills, self.facade)

    def _write_step_report(self, state: RoundState, archive: Any, judgment: Judgment) -> Path | None:
        if self.report_root is None:
            return None
        path = (
            self.report_root
            / "step_reports"
            / f"step-{state.trials_run + 2:04d}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "step_report": dict(archive.step_report),
                    "round_report": dict(archive.round_report),
                    "status": judgment.status,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def _commit_step(
        self,
        path: Path | None,
        *,
        files: tuple[str, ...] = (),
        message: str,
    ) -> None:
        if self.commit_recorder is None or path is None or self.report_root is None:
            return
        relative_report = str(path.relative_to(self.report_root))
        self.commit_recorder.commit(
            message,
            files=files,
            report_path=relative_report,
        )

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
        state = advance(state, Stage.DECISION)
        context, skills = self.builder.build(state, Stage.DECISION)
        decision_result = self._run_expert("decision", context, skills)
        require_artifact(Stage.DECISION, decision_result.artifact)
        hypotheses = decision_result.artifact.hypotheses
        state = replace(
            state,
            hypotheses=hypotheses,
            previous_artifact=decision_result.artifact,
        )

        if not hypotheses:
            return advance(state, Stage.DONE, stop_reason="no_hypotheses")

        for index, hypothesis in enumerate(hypotheses):
            if state.stage == Stage.NEXT_CANDIDATE:
                state = advance(state, Stage.DECISION)
            if state.trials_run >= self.task.budget.max_trials:
                return advance(state, Stage.DONE, stop_reason="budget_exhausted")

            # DEVELOPMENT: contract-approved CandidateSpec.
            context, skills = self.builder.build(
                state, Stage.DEVELOPMENT, candidate=hypothesis
            )
            development_result = self._run_expert("development", context, skills)
            require_artifact(Stage.DEVELOPMENT, development_result.artifact)
            candidate = development_result.artifact
            state = advance(
                state,
                Stage.DEVELOPMENT,
                current_candidate=candidate,
                previous_artifact=development_result.artifact,
                candidate_index=index,
            )

            attempts = 0
            while True:
                if state.trials_run >= self.task.budget.max_trials:
                    return advance(
                        state, Stage.DONE, stop_reason="budget_exhausted"
                    )

                # EXECUTION: deterministic runtime, no agent.
                state = advance(
                    state,
                    Stage.EXECUTION,
                    current_candidate=candidate,
                    previous_artifact=development_result.artifact,
                    trials_run=state.trials_run + 1,
                )
                context, _skills = self.builder.build(
                    state, Stage.EXECUTION, candidate=candidate
                )
                try:
                    self.patch_manager.apply(candidate)
                    execution = self.execution.run(context, self.facade)
                except Exception as exc:  # noqa: BLE001 - a failed trial is evidence
                    self.patch_manager.revert(candidate)
                    attempts += 1
                    failure_judgment = Judgment(
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
                    self._record(
                        state,
                        candidate,
                        None,
                        failure_judgment,
                        rollback="not_committed",
                        status=_error_status(exc),
                    )

                    if (
                        attempts <= self.task.budget.max_repairs
                        and state.trials_run < self.task.budget.max_trials
                    ):
                        # EXECUTION -> DEVELOPMENT repair edge, then retry.
                        state = advance(
                            state,
                            Stage.DEVELOPMENT,
                            current_candidate=candidate,
                            previous_artifact=development_result.artifact,
                        )
                        context, skills = self.builder.build(
                            state,
                            Stage.DEVELOPMENT,
                            candidate=hypothesis,
                            failure=str(exc),
                            attempt=attempts,
                        )
                        development_result = self._run_expert(
                            "development", context, skills
                        )
                        require_artifact(Stage.DEVELOPMENT, development_result.artifact)
                        candidate = development_result.artifact
                        state = replace(
                            state,
                            current_candidate=candidate,
                            previous_artifact=development_result.artifact,
                        )
                        continue

                    state = advance(
                        state, Stage.JUDGMENT, previous_artifact=failure_judgment
                    )
                    context, skills = self.builder.build(state, Stage.ARCHIVE)
                    archive_result = self._run_expert(
                        "archive_report", context, skills
                    )
                    require_artifact(Stage.ARCHIVE, archive_result.artifact)
                    state = advance(
                        state, Stage.ARCHIVE, previous_artifact=archive_result.artifact
                    )
                    report_path = self._write_step_report(
                        state, archive_result.artifact, failure_judgment
                    )
                    self._commit_step(
                        report_path,
                        message=(
                            f"step {state.trials_run + 2} "
                            f"{candidate.hypothesis_id} {_error_status(exc)}"
                        ),
                    )
                    state = advance(state, Stage.NEXT_CANDIDATE)
                    break

                require_artifact(Stage.EXECUTION, execution)
                state = replace(state, previous_artifact=execution)

                # JUDGMENT: gates + observed baseline.
                context, skills = self.builder.build(
                    state, Stage.JUDGMENT, candidate=candidate
                )
                judgment_result = self._run_expert("judgment", context, skills)
                require_artifact(Stage.JUDGMENT, judgment_result.artifact)
                judgment = judgment_result.artifact
                state = advance(
                    state, Stage.JUDGMENT, previous_artifact=judgment
                )

                # ARCHIVE: step report payload.
                context, skills = self.builder.build(state, Stage.ARCHIVE)
                archive_result = self._run_expert("archive_report", context, skills)
                require_artifact(Stage.ARCHIVE, archive_result.artifact)
                state = advance(
                    state, Stage.ARCHIVE, previous_artifact=archive_result.artifact
                )

                report_path = self._write_step_report(
                    state, archive_result.artifact, judgment
                )

                files: list[str] = []
                if judgment.status == "keep" and self.report_root is not None:
                    config_path = Path(execution.trial.config_path)
                    try:
                        files.append(
                            str(config_path.relative_to(self.report_root))
                        )
                    except ValueError:
                        files.append(str(config_path))
                    if candidate.patch:
                        patch_path = (
                            self.report_root
                            / f"candidate-{candidate.hypothesis_id}.patch"
                        )
                        patch_path.write_text(candidate.patch, encoding="utf-8")
                        files.append(str(patch_path.relative_to(self.report_root)))
                elif candidate.patch:
                    self.patch_manager.revert(candidate)

                self._commit_step(
                    report_path,
                    files=tuple(files),
                    message=(
                        f"step {state.trials_run + 2} "
                        f"{candidate.hypothesis_id} {judgment.status}"
                    ),
                )

                self._record(
                    state,
                    candidate,
                    execution,
                    judgment,
                    prompt_hash=judgment_result.prompt_hash,
                    skill_ids=judgment_result.used_skills,
                )

                if judgment.status == "keep":
                    state = replace(
                        state,
                        best_trial=execution.trial,
                        best_metric=judgment.metric,
                    )

                state = advance(state, Stage.NEXT_CANDIDATE)
                break

        return advance(
            state,
            Stage.DONE,
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
        prompt_hash: str | None = None,
        skill_ids: tuple[str, ...] = (),
    ) -> None:
        if self.store is None:
            return
        gates = tuple(
            {"name": gate.name, "passed": gate.passed, "detail": gate.detail}
            for gate in judgment.gates
        )
        artifacts: dict[str, str] = {}
        evidence: dict[str, Any] = {}
        if candidate.patch:
            artifacts["patch_target_files"] = ",".join(candidate.patch_target_files)
        if execution is not None:
            artifacts.update(
                {
                    "config": str(execution.trial.config_path),
                    "log": str(execution.trial.log_path),
                }
            )
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
                prompt_hash=prompt_hash,
                skill_ids=skill_ids,
            )
        )

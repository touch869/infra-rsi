"""JudgmentExpert: deterministic keep / discard / crash verdict."""

from __future__ import annotations

from ...prompting import StageContext
from ...runtime.facade import RuntimeFacade
from ..artifacts import ExecutionResult, Judgment
from ..base import ExpertResult
from ..registry import EXPERTS
from .prompt_spec import JUDGMENT_PROMPT_SPEC

__all__ = ["JudgmentExpert"]


class JudgmentExpert:
    name = "judgment"
    stage = "judgment"
    prompt_spec = JUDGMENT_PROMPT_SPEC

    def run(self, context: StageContext, facade: RuntimeFacade) -> ExpertResult:
        artifact = context.previous_artifact
        if not isinstance(artifact, ExecutionResult):
            raise ValueError("JudgmentExpert needs an ExecutionResult")
        if context.baseline_trial is None:
            raise ValueError("JudgmentExpert needs a baseline_trial")

        trial = artifact.trial
        metric = facade.metric_value(trial)
        best_before = (
            context.best_metric
            if context.best_metric is not None
            else context.baseline_metric
        )
        if best_before is None:
            raise ValueError("JudgmentExpert needs best_metric or baseline_metric")

        gates = facade.run_gates(trial, context.baseline_trial, context.best_trial)
        failed = [gate for gate in gates if not gate.passed]

        if failed:
            status = "crash"
            detail = "; ".join(f"{gate.name}: {gate.detail}" for gate in failed)
        elif metric is None:
            status = "crash"
            detail = f"metric {context.task.metric.key!r} missing"
        elif context.task.metric.improved(metric, best_before):
            status = "keep"
            detail = f"{metric:.6g} beats {best_before:.6g} beyond noise"
        else:
            status = "discard"
            detail = f"{metric:.6g} does not beat {best_before:.6g} beyond noise"

        return ExpertResult(
            role=self.name,
            stage=self.stage,
            artifact=Judgment(
                trial=trial.label,
                status=status,
                metric=metric,
                baseline_metric=context.baseline_metric,
                best_before=best_before,
                delta_vs_best=facade.delta(metric, best_before),
                gates=tuple(gates),
                detail=detail,
                overrides=dict(artifact.candidate.overrides),
            ),
        )


EXPERTS.register(JudgmentExpert())

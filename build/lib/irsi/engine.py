"""The experiment state machine: baseline, candidates, gates, decision, ledger."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .execution import backends as _backends  # noqa: F401  (plugin registration)
from .contract import surfaces as _surfaces  # noqa: F401
from . import gates as _gates  # noqa: F401
from .execution.backends.base import Backend, TrialResult
from .contract import InfraTaskSpec, check_overrides_allowed
from .contract.surfaces.base import Hypothesis
from .gates.base import Gate, GateContext, GateResult
from .knowledge.runtime.ledger_store import TaskLedger
from .registry import SURFACES, GATES

__all__ = ["Decision", "Engine", "build_gates"]


def build_gates(spec: InfraTaskSpec) -> list[Gate]:
    """Instantiate the contract's gate plugins in declared order."""
    return [GATES.create(gate.name, **dict(gate.params)) for gate in spec.gates]


@dataclass(frozen=True)
class Decision:
    """The recorded outcome of one candidate trial."""

    trial: str
    status: str
    description: str
    metric: Optional[float]
    baseline_metric: Optional[float]
    best_before: Optional[float]
    delta_vs_best: Optional[float]
    gates: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    why: str = ""
    changes: list[str] = field(default_factory=list)
    test_result: str = ""
    commit_ref: str = ""
    code_restored: bool = False
    rollback_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Engine:
    """Runs one task: baseline, then candidate hypotheses within the budget."""

    def __init__(
        self,
        spec: InfraTaskSpec,
        backend: Backend,
        ledger: TaskLedger,
        gates: list[Gate] | None = None,
    ) -> None:
        self.spec = spec
        self.backend = backend
        self.ledger = ledger
        self.gates = gates if gates is not None else build_gates(spec)
        self.baseline: Optional[TrialResult] = None
        self.best: Optional[TrialResult] = None
        self.baseline_metric: Optional[float] = None
        self.decisions: list[Decision] = []
        self.baseline_gates: list[GateResult] = []

    # -- metric helpers --------------------------------------------------
    def metric_of(self, trial: TrialResult) -> Optional[float]:
        return trial.metrics.value(
            self.spec.metric.key,
            warmup_steps=self.spec.metric.warmup_steps,
            measured_steps=self.spec.metric.measured_steps,
        )

    def _delta(self, value: Optional[float], reference: Optional[float]) -> Optional[float]:
        if value is None or reference in (None, 0):
            return None
        return (value - reference) / reference

    # -- one trial -------------------------------------------------------
    def _run_trial(
        self,
        label: str,
        overrides: dict[str, Any],
        *,
        baseline: Optional[TrialResult],
    ) -> TrialResult:
        check_overrides_allowed(self.spec, overrides)
        self.ledger.event("trial_start", trial=label, overrides=overrides)
        trial = self.backend.run(self.spec, self.ledger.trial_dir(label), overrides, label)
        self.ledger.event("trial_end", **trial.summary())
        return trial

    def _gate_context(self, trial: TrialResult) -> GateContext:
        return GateContext(spec=self.spec, trial=trial, baseline=self.baseline, best=self.best)

    # -- baseline --------------------------------------------------------
    def run_baseline(self) -> TrialResult:
        """Measure the frozen baseline; no hypothesis is applied."""
        self.ledger.set_state("BASELINE")
        trial = self._run_trial("baseline", {}, baseline=None)
        results = [gate.check(GateContext(self.spec, trial)) for gate in self.gates]
        self.baseline_gates = results
        self.ledger.write_json(
            "baseline.json",
            {"summary": trial.summary(), "gates": [g.__dict__ for g in results]},
        )
        failed = [g for g in results if not g.passed]
        if failed:
            detail = "; ".join(f"{g.name}: {g.detail}" for g in failed)
            self.ledger.set_state("FAILED", reason=detail)
            raise RuntimeError(f"baseline failed gates: {detail}")
        metric = self.metric_of(trial)
        if metric is None:
            self.ledger.set_state("FAILED", reason="baseline metric missing")
            raise RuntimeError(f"baseline has no value for metric {self.spec.metric.key!r}")
        self.baseline = trial
        self.best = trial
        self.baseline_metric = metric
        return trial

    # -- candidates ------------------------------------------------------
    def _record(self, decision: Decision) -> None:
        path = f"decisions/{decision.trial}.json"
        self.ledger.write_json(path, decision.to_dict())
        self.ledger.append_jsonl("candidates.jsonl", decision.to_dict())
        self.ledger.append_result(
            commit_ref=decision.commit_ref,
            trial=decision.trial,
            metric=decision.metric,
            status=decision.status,
            delta_vs_best=decision.delta_vs_best,
            description=decision.description,
        )
        self.ledger.append_experiment_log(
            record_id=decision.trial,
            trial=decision.trial,
            decision=decision.status,
            why=decision.why,
            changes=decision.changes,
            test_result=decision.test_result,
            commit_ref=decision.commit_ref,
            code_restored=decision.code_restored,
            rollback_ref=decision.rollback_ref,
            evidence=decision.artifacts,
        )
        self.decisions.append(decision)

    @staticmethod
    def _changes(overrides: dict[str, Any]) -> list[str]:
        if not overrides:
            return ["no-op control: no overrides"]
        return [f"{key}={value!r}" for key, value in sorted(overrides.items())]

    @staticmethod
    def _test_result(
        status: str,
        detail: str,
        metric: Optional[float],
        delta_vs_best: Optional[float],
    ) -> str:
        if metric is None:
            return f"{status}: {detail}"
        delta = "n/a" if delta_vs_best is None else f"{delta_vs_best:+.2%}"
        return f"{status}: metric {metric:.6g}, delta vs best {delta}; {detail}"

    def run_candidate(self, index: int, hypothesis: Hypothesis) -> Decision:
        """Execute one hypothesis and record keep/discard/crash."""
        label = f"h{index:02d}-{hypothesis.id}"
        best_before = self.metric_of(self.best) if self.best else self.baseline_metric
        try:
            trial = self._run_trial(label, dict(hypothesis.overrides), baseline=self.baseline)
        except Exception as exc:  # noqa: BLE001 - a failed trial is evidence, not a crash
            self.ledger.event("trial_error", trial=label, error=str(exc))
            decision = Decision(
                trial=label,
                status="crash",
                description=hypothesis.description,
                metric=None,
                baseline_metric=self.baseline_metric,
                best_before=best_before,
                delta_vs_best=None,
                detail=f"backend error: {exc}",
                overrides=dict(hypothesis.overrides),
                why=hypothesis.description,
                changes=self._changes(dict(hypothesis.overrides)),
                test_result=f"crash: backend error: {exc}",
                commit_ref=f"Experiment-Record: {label}",
                code_restored=True,
                rollback_ref=self.best.label if self.best else "baseline",
            )
            self._record(decision)
            return decision

        gate_results = [gate.check(self._gate_context(trial)) for gate in self.gates]
        metric = self.metric_of(trial)
        delta = self._delta(metric, best_before)
        artifacts = {"config": str(trial.config_path), "log": str(trial.log_path)}

        if not all(result.passed for result in gate_results):
            failed = "; ".join(f"{g.name}: {g.detail}" for g in gate_results if not g.passed)
            status = "crash"
            detail = failed
        elif metric is None:
            status = "crash"
            detail = f"metric {self.spec.metric.key!r} missing"
        elif self.spec.metric.improved(metric, best_before or 0.0):
            status = "keep"
            detail = f"{metric:.6g} beats {best_before:.6g} beyond noise"
        else:
            status = "discard"
            detail = f"{metric:.6g} does not beat {best_before:.6g} beyond noise"

        decision = Decision(
            trial=label,
            status=status,
            description=hypothesis.description,
            metric=metric,
            baseline_metric=self.baseline_metric,
            best_before=best_before,
            delta_vs_best=delta,
            gates=[result.__dict__ for result in gate_results],
            detail=detail,
            overrides=dict(hypothesis.overrides),
            artifacts=artifacts,
            why=hypothesis.description,
            changes=self._changes(dict(hypothesis.overrides)),
            test_result=self._test_result(status, detail, metric, delta),
            commit_ref=f"Experiment-Record: {label}",
            code_restored=status != "keep",
            rollback_ref=(self.best.label if self.best else "baseline") if status != "keep" else None,
        )
        self._record(decision)
        if status == "keep":
            self.best = trial
        return decision

    # -- whole task ------------------------------------------------------
    def run(self, max_trials: int | None = None) -> dict[str, Any]:
        """Run the baseline and up to ``max_trials`` candidates; return the report."""
        limit = max_trials or self.spec.budget.max_trials
        self.run_baseline()
        candidates = SURFACES.create(self.spec.domain, spec=self.spec)
        if not isinstance(candidates, (list, tuple)):
            raise TypeError("domain plugin must return a sequence of Hypothesis")
        for index, hypothesis in enumerate(candidates[:limit], start=1):
            self.ledger.set_state("RUNNING", trial=f"h{index:02d}-{hypothesis.id}")
            self.run_candidate(index, hypothesis)
        report = self.report()
        self.ledger.write_json("report.json", report)
        (self.ledger.root / "report.md").write_text(self.render_markdown(report), encoding="utf-8")
        self.ledger.set_state("COMPLETED", best=report["best"]["trial"])
        return report

    def report(self) -> dict[str, Any]:
        """Structured summary of the run."""
        if self.baseline is None:
            raise RuntimeError("baseline has not been measured")
        best_metric = self.metric_of(self.best) if self.best else self.baseline_metric
        kept = [d for d in self.decisions if d.status == "keep"]
        controls = [d for d in self.decisions if not d.overrides and d.metric is not None]
        control_delta = (
            sum(self._delta(d.metric, self.baseline_metric) or 0.0 for d in controls) / len(controls)
            if controls
            else None
        )
        gain_vs_control = (
            self._delta(best_metric, controls[0].metric) if controls and best_metric is not None else None
        )
        drift_suspected = (
            control_delta is not None and abs(control_delta) > self.spec.metric.noise_fraction
        )
        robust = (
            gain_vs_control is not None and gain_vs_control > self.spec.metric.noise_fraction
        )
        return {
            "task": self.ledger.root.name,
            "name": self.spec.name,
            "domain": self.spec.domain,
            "metric_key": self.spec.metric.key,
            "metric_direction": self.spec.metric.direction,
            "noise_fraction": self.spec.metric.noise_fraction,
            "baseline": {
                "trial": self.baseline.label,
                "metric": self.baseline_metric,
                "peak_mem_gib": self.baseline.metrics.peak_mem_gib,
                "numeric_hash": self.baseline.metrics.numeric_hash,
                "gates": [g.__dict__ for g in self.baseline_gates],
            },
            "best": {
                "trial": self.best.label if self.best else None,
                "metric": best_metric,
                "peak_mem_gib": self.best.metrics.peak_mem_gib if self.best else None,
                "numeric_hash": self.best.metrics.numeric_hash if self.best else None,
                "gain_vs_baseline": self._delta(best_metric, self.baseline_metric),
                "gain_vs_control": gain_vs_control,
            },
            "drift": {
                "control_trials": [d.trial for d in controls],
                "control_delta_vs_baseline": control_delta,
                "suspected": drift_suspected,
            },
            "robust": robust,
            "counts": {
                "trials": len(self.decisions),
                "kept": len(kept),
                "discarded": sum(1 for d in self.decisions if d.status == "discard"),
                "crashed": sum(1 for d in self.decisions if d.status == "crash"),
            },
            "decisions": [d.to_dict() for d in self.decisions],
        }

    @staticmethod
    def render_markdown(report: dict[str, Any]) -> str:
        """Human-readable report for the run directory."""
        def num(value: Optional[float], digits: int = 6) -> str:
            return "n/a" if value is None else f"{value:.{digits}g}"

        baseline = report["baseline"]
        best = report["best"]
        drift = report["drift"]
        gain = best["gain_vs_baseline"]
        control_gain = best["gain_vs_control"]
        gain_text = "n/a" if gain is None else f"{gain * 100:+.2f}%"
        control_text = "n/a" if control_gain is None else f"{control_gain * 100:+.2f}%"
        control_delta = drift["control_delta_vs_baseline"]
        control_delta_text = "n/a" if control_delta is None else f"{control_delta * 100:+.2f}%"
        lines = [
            f"# {report['name']} · {report['domain']}",
            "",
            f"- metric: `{report['metric_key']}` ({report['metric_direction']}, "
            f"noise {report['noise_fraction']:.0%})",
            f"- baseline: {num(baseline['metric'])}"
            f" (peak {num(baseline['peak_mem_gib'], 3)} GiB)",
            f"- best: {best['trial']} = {num(best['metric'])}"
            f" (peak {num(best['peak_mem_gib'], 3)} GiB), gain {gain_text}",
            f"- control drift: {control_delta_text}"
            f" ({'suspected' if drift['suspected'] else 'within noise'}), "
            f"gain vs control {control_text}, robust={report['robust']}",
            "",
            "| trial | status | metric | delta vs best | detail |",
            "|---|---|---|---|---|",
        ]
        for decision in report["decisions"]:
            delta = decision["delta_vs_best"]
            delta_text = "n/a" if delta is None else f"{delta * 100:+.2f}%"
            lines.append(
                f"| {decision['trial']} | {decision['status']} | {num(decision['metric'])} | "
                f"{delta_text} | {decision['detail']} |"
            )
        lines.append("")
        return "\n".join(lines)

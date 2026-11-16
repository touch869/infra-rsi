"""Engine state machine with a fake backend: keep / discard / crash and the ledger."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from irsi.execution.backends.base import TrialResult
from irsi.contract import load_contract
from irsi.contract.surfaces.base import Hypothesis
from irsi.engine import Engine
from irsi.knowledge.runtime.ledger_store import TaskLedger
from irsi.execution.metric_extractor import StepMetric, TrialMetrics
from irsi.registry import SURFACES


@SURFACES.register("fake-test-domain")
def _fake_domain(spec):  # noqa: ARG001
    return [
        Hypothesis("win", "faster", {"activation_checkpoint.mode": "off"}),
        Hypothesis("tie", "no-op", {}),
        Hypothesis("bad", "numerically wrong", {"activation_checkpoint.mode": "selective"}),
    ]


CONTRACT = """
name: engine-test
repo_root: /repo
base_config: /repo/train.yaml
domain: fake-test-domain
writable_prefixes:
  - activation_checkpoint.
metric:
  key: performance/tokens_per_second
  direction: maximize
  noise_fraction: 0.02
  warmup_steps: 0
  measured_steps: 4
workload:
  nproc: 1
  expect_steps: 4
gates:
  - name: receipt
  - name: bitwise
budget:
  max_trials: 3
  timeout_min: 1
"""


def _metrics(tps: float, *, loss: float = 1.0, steps: int = 4, exit_code: int = 0) -> TrialMetrics:
    rows = tuple(
        StepMetric(step=i + 1, loss=loss, grad_norm=2.0, step_time=1.0, tokens_per_second=tps, peak_mem_gib=1.0)
        for i in range(steps)
    )
    return TrialMetrics(steps=rows, exit_code=exit_code)


class FakeBackend:
    name = "fake"

    def __init__(self, metrics):
        self._metrics = list(metrics)
        self.calls = []

    def run(self, spec, trial_dir, overrides, label):  # noqa: ARG002
        path = Path(trial_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "run.log").write_text("fake log", encoding="utf-8")
        config = path / "train.yaml"
        config.write_text("fake config", encoding="utf-8")
        self.calls.append(label)
        return TrialResult(
            label=label,
            backend=self.name,
            metrics=self._metrics.pop(0),
            log_path=path / "run.log",
            config_path=config,
            command="fake",
            elapsed_s=0.01,
        )


def _spec(tmp_path) -> object:
    path = tmp_path / "contract.yaml"
    path.write_text(textwrap.dedent(CONTRACT), encoding="utf-8")
    return load_contract(path)


def test_keep_discard_and_recovery(tmp_path):
    spec = _spec(tmp_path)
    backend = FakeBackend([_metrics(100.0), _metrics(120.0), _metrics(101.0)])
    ledger = TaskLedger(tmp_path / "task", {"name": spec.name})
    report = Engine(spec, backend, ledger).run(max_trials=2)

    assert report["baseline"]["metric"] == 100.0
    assert report["best"]["trial"] == "h01-win"
    assert report["best"]["gain_vs_baseline"] == pytest.approx(0.2)
    statuses = [d["status"] for d in report["decisions"]]
    assert statuses == ["keep", "discard"]
    assert report["drift"]["control_trials"] == ["h02-tie"]
    assert report["drift"]["suspected"] is False
    assert report["best"]["gain_vs_control"] == pytest.approx(120.0 / 101.0 - 1.0)
    assert report["robust"] is True
    assert (tmp_path / "task" / "results.tsv").read_text(encoding="utf-8").count("\n") == 3
    assert len((tmp_path / "task" / "candidates.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert (tmp_path / "task" / "report.md").is_file()
    state = json.loads((tmp_path / "task" / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "COMPLETED"


def test_bitwise_mismatch_is_a_crash(tmp_path):
    spec = _spec(tmp_path)
    backend = FakeBackend([_metrics(100.0), _metrics(130.0, loss=9.9)])
    ledger = TaskLedger(tmp_path / "task", {"name": spec.name})
    report = Engine(spec, backend, ledger).run(max_trials=1)
    decision = report["decisions"][0]
    assert decision["status"] == "crash"
    assert "bitwise" in decision["detail"]
    assert report["best"]["trial"] == "baseline"


def test_incomplete_window_is_a_crash(tmp_path):
    spec = _spec(tmp_path)
    backend = FakeBackend([_metrics(100.0), _metrics(120.0, steps=2)])
    ledger = TaskLedger(tmp_path / "task", {"name": spec.name})
    report = Engine(spec, backend, ledger).run(max_trials=1)
    assert report["decisions"][0]["status"] == "crash"
    assert "incomplete_window" in report["decisions"][0]["detail"]


def test_override_outside_surface_never_reaches_backend(tmp_path):
    @SURFACES.register("bad-surface-domain")
    def _bad_domain(spec):  # noqa: ARG001
        return [Hypothesis("oops", "writes outside surface", {"training.seed": 1})]

    body = CONTRACT.replace("domain: fake-test-domain", "domain: bad-surface-domain")
    path = tmp_path / "contract.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    spec = load_contract(path)
    backend = FakeBackend([_metrics(100.0)])
    ledger = TaskLedger(tmp_path / "task", {"name": spec.name})
    report = Engine(spec, backend, ledger).run(max_trials=1)
    assert report["decisions"][0]["status"] == "crash"
    assert "read-only" in report["decisions"][0]["detail"] or "writable" in report["decisions"][0]["detail"]
    assert backend.calls == ["baseline"]

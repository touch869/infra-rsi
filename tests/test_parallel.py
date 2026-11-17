"""Parallel surface and gates: topology validation, engagement, numeric parity."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from irsi.contract import surfaces as _surfaces  # noqa: F401  (plugin registration)
from irsi.contract import check_overrides_allowed, load_contract
from irsi.execution.backends.base import TrialResult
from irsi.execution.metric_extractor import StepMetric, TrialMetrics, parse_log
from irsi.gates.base import GateContext
from irsi.registry import GATES, SURFACES


def _parallel_contract(tmp_path, ladder: str, allow_sp: bool = False):
    body = f"""
    name: parallel-demo
    repo_root: /repo
    base_config: /repo/train.yaml
    domain: parallel
    domain_params:
      num_attention_heads: 16
      num_key_value_heads: 8
      allow_sequence_parallel: {str(allow_sp).lower()}
      parallel_ladder: {ladder}
    writable_prefixes:
      - accelerator.
      - fsdp_config.dp_shard_size
    read_only_keys:
      - training.
      - activation_checkpoint.
    metric:
      key: performance/tokens_per_second
      direction: maximize
      noise_fraction: 0.05
      warmup_steps: 2
      measured_steps: 2
    workload:
      nproc: 8
      expect_steps: 4
    gates:
      - name: receipt
      - name: parallel-engagement
      - name: numeric-parity
    budget:
      max_trials: 4
      timeout_min: 5
    """
    path = tmp_path / "contract.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_contract(path)


def _trial(
    tmp_path,
    label: str,
    log_text: str,
    config_text: str,
    steps: list[StepMetric] | None = None,
) -> TrialResult:
    log_path = tmp_path / f"{label}.log"
    config_path = tmp_path / f"{label}.yaml"
    log_path.write_text(log_text, encoding="utf-8")
    config_path.write_text(config_text, encoding="utf-8")
    metrics = TrialMetrics(tuple(steps or ()))
    return TrialResult(
        label=label,
        backend="hyperparallel",
        metrics=metrics,
        log_path=log_path,
        config_path=config_path,
        command="train",
        elapsed_s=1.0,
    )


def _steps(values: list[tuple[float, float]]) -> list[StepMetric]:
    return [
        StepMetric(
            step=i + 1,
            loss=loss,
            grad_norm=grad,
            step_time=1.0,
            tokens_per_second=100.0,
            peak_mem_gib=1.0,
        )
        for i, (loss, grad) in enumerate(values)
    ]


def test_parallel_candidates_cover_the_ladder(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: tp2-dp4, tp_size: 2, dp_shard_size: 4}]")
    candidates = SURFACES.create("parallel", spec=spec)
    assert [c.id for c in candidates] == ["control", "tp2-dp4"]
    for candidate in candidates:
        check_overrides_allowed(spec, candidate.overrides)
    override = candidates[1].overrides
    assert override["accelerator.tp_size"] == 2
    assert override["accelerator.loss_parallel"] is True
    assert override["accelerator.sequence_parallel"] is False
    assert override["fsdp_config.dp_shard_size"] == 4


def test_parallel_rejects_sequence_parallel_without_contract_flag(tmp_path):
    spec = _parallel_contract(
        tmp_path,
        "[{id: tp2-sp, tp_size: 2, dp_shard_size: 4, sequence_parallel: true}]",
    )
    with pytest.raises(ValueError, match="sequence_parallel"):
        SURFACES.create("parallel", spec=spec)


def test_parallel_rejects_tp_without_loss_parallel(tmp_path):
    spec = _parallel_contract(
        tmp_path,
        "[{id: tp2-nolp, tp_size: 2, dp_shard_size: 4, loss_parallel: false}]",
    )
    with pytest.raises(ValueError, match="loss_parallel"):
        SURFACES.create("parallel", spec=spec)


def test_parallel_rejects_incompatible_dp_shard(tmp_path):
    spec = _parallel_contract(
        tmp_path,
        "[{id: tp2-bad, tp_size: 2, dp_shard_size: 3}]",
    )
    with pytest.raises(ValueError, match="must divide dp_size"):
        SURFACES.create("parallel", spec=spec)


def test_parallel_rejects_tp_not_dividing_heads(tmp_path):
    spec = _parallel_contract(
        tmp_path,
        "[{id: tp3, tp_size: 3, dp_shard_size: 1}]",
    )
    with pytest.raises(ValueError, match="num_attention_heads"):
        SURFACES.create("parallel", spec=spec)


def test_engagement_gate_passes_on_runtime_mesh(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: tp2-dp4, tp_size: 2, dp_shard_size: 4}]")
    log = (
        "Built device mesh (4, 1, 2), dense FSDP mesh (1, 4, 2) and expert FSDP mesh None\n"
        "Running ShardingPlanner.plan(tp=2, cp=1, ep=1, sequence_parallel=False, loss_parallel=True)\n"
    )
    config = textwrap.dedent(
        """
        accelerator:
          tp_size: 2
          cp_size: 1
          ep_size: 1
          pp_size: 1
          sequence_parallel: false
          loss_parallel: true
        fsdp_config:
          dp_shard_size: 4
        """
    )
    trial = _trial(tmp_path, "tp2", log, config)
    result = GATES.create("parallel-engagement").check(GateContext(spec, trial))
    assert result.passed, result.detail


def test_engagement_gate_fails_without_mesh(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: tp2-dp4, tp_size: 2, dp_shard_size: 4}]")
    config = textwrap.dedent(
        """
        accelerator:
          tp_size: 2
          cp_size: 1
          ep_size: 1
          pp_size: 1
          sequence_parallel: false
          loss_parallel: true
        fsdp_config:
          dp_shard_size: 4
        """
    )
    trial = _trial(tmp_path, "tp2", "no topology marker\n", config)
    result = GATES.create("parallel-engagement").check(GateContext(spec, trial))
    assert not result.passed
    assert "not engaged" in result.detail


def test_numeric_parity_passes_within_tolerance(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: tp2-dp4, tp_size: 2, dp_shard_size: 4}]")
    baseline = _trial(
        tmp_path,
        "baseline",
        "",
        "accelerator:\n  tp_size: 1\nfsdp_config:\n  dp_shard_size: 8\n",
        _steps([(1.0, 2.0), (1.1, 2.1)]),
    )
    candidate = _trial(
        tmp_path,
        "candidate",
        "",
        "accelerator:\n  tp_size: 2\nfsdp_config:\n  dp_shard_size: 4\n",
        _steps([(1.0005, 2.0005), (1.1005, 2.1005)]),
    )
    result = GATES.create("numeric-parity", rtol=1e-3, atol=1e-6).check(
        GateContext(spec, candidate, baseline)
    )
    assert result.passed, result.detail


def test_engagement_gate_accepts_tp1_without_plan(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: dp1, tp_size: 1, dp_shard_size: 1}]")
    log = "Built device mesh (8, 1, 1), dense FSDP mesh (8, 1, 1) and expert FSDP mesh None\n"
    config = textwrap.dedent(
        """
        accelerator:
          tp_size: 1
          cp_size: 1
          ep_size: 1
          pp_size: 1
          sequence_parallel: false
          loss_parallel: false
        fsdp_config:
          dp_shard_size: 1
        """
    )
    trial = _trial(tmp_path, "dp1", log, config)
    result = GATES.create("parallel-engagement").check(GateContext(spec, trial))
    assert result.passed, result.detail


def test_numeric_parity_loss_only_ignores_grad_norm(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: tp2-dp4, tp_size: 2, dp_shard_size: 4}]")
    baseline = _trial(
        tmp_path,
        "baseline",
        "",
        "accelerator:\n  tp_size: 1\nfsdp_config:\n  dp_shard_size: 8\n",
        _steps([(1.0, 2.0)]),
    )
    candidate = _trial(
        tmp_path,
        "candidate",
        "",
        "accelerator:\n  tp_size: 2\nfsdp_config:\n  dp_shard_size: 4\n",
        _steps([(1.01, 3.0)]),
    )
    result = GATES.create("numeric-parity", rtol=0.05, atol=1e-4, fields=("loss",)).check(
        GateContext(spec, candidate, baseline)
    )
    assert result.passed, result.detail


def test_numeric_parity_loss_only_fails_on_loss_divergence(tmp_path):
    spec = _parallel_contract(tmp_path, "[{id: tp2-dp4, tp_size: 2, dp_shard_size: 4}]")
    baseline = _trial(
        tmp_path,
        "baseline",
        "",
        "accelerator:\n  tp_size: 1\nfsdp_config:\n  dp_shard_size: 8\n",
        _steps([(1.0, 2.0)]),
    )
    candidate = _trial(
        tmp_path,
        "candidate",
        "",
        "accelerator:\n  tp_size: 2\nfsdp_config:\n  dp_shard_size: 4\n",
        _steps([(1.2, 2.0)]),
    )
    result = GATES.create("numeric-parity", rtol=0.05, atol=1e-4, fields=("loss",)).check(
        GateContext(spec, candidate, baseline)
    )
    assert not result.passed
    assert "first divergence" in result.detail


def test_shipped_parallel_contract_is_loadable():
    root = Path(__file__).resolve().parents[1]
    spec = load_contract(root / "contracts" / "qwen3-0.6b-parallel.yaml")
    assert spec.domain == "parallel"
    assert spec.writable_prefixes == ("accelerator.", "fsdp_config.dp_shard_size")
    candidates = SURFACES.create("parallel", spec=spec)
    assert [c.id for c in candidates] == [
        "control",
        "dp4",
        "dp2",
        "dp1",
        "tp2-dp4",
        "tp2-dp2",
        "tp2-dp1",
        "tp4-dp2",
        "tp8-dp1",
    ]
    for candidate in candidates:
        check_overrides_allowed(spec, candidate.overrides)

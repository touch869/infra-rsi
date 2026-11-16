"""Contract loading, dotted overrides and the key-level edit surface."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from irsi.contract import apply_overrides, check_overrides_allowed, load_contract


def _write(tmp_path, body: str):
    path = tmp_path / "contract.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


CONTRACT = """
name: demo
repo_root: /repo
base_config: /repo/train.yaml
domain: recompute
writable_prefixes:
  - activation_checkpoint.
read_only_keys:
  - training.seed
base_overrides:
  training.train_iters: 4
  activation_checkpoint.mode: full
metric:
  key: performance/tokens_per_second
  direction: maximize
  noise_fraction: 0.05
  warmup_steps: 2
  measured_steps: 2
workload:
  nproc: 2
  expect_steps: 4
gates:
  - name: receipt
  - name: bitwise
budget:
  max_trials: 2
  timeout_min: 5
"""


def test_load_contract(tmp_path):
    spec = load_contract(_write(tmp_path, CONTRACT))
    assert spec.name == "demo"
    assert spec.writable_prefixes == ("activation_checkpoint.",)
    assert spec.metric.noise_fraction == 0.05
    assert spec.workload.nproc == 2
    assert [g.name for g in spec.gates] == ["receipt", "bitwise"]


def test_apply_overrides_creates_nested_mappings():
    config = {"a": {"b": 1}, "keep": True}
    merged = apply_overrides(config, {"a.c": 2, "d.e": 3})
    assert merged["a"] == {"b": 1, "c": 2}
    assert merged["d"] == {"e": 3}
    assert config["a"] == {"b": 1}  # original is untouched


def test_apply_overrides_refuses_to_cross_scalars():
    with pytest.raises(ValueError):
        apply_overrides({"a": 1}, {"a.b": 2})


def test_writable_surface_allows_prefix(tmp_path):
    spec = load_contract(_write(tmp_path, CONTRACT))
    check_overrides_allowed(spec, {"activation_checkpoint.mode": "off"})
    check_overrides_allowed(spec, {})


def test_writable_surface_rejects_outside_keys(tmp_path):
    spec = load_contract(_write(tmp_path, CONTRACT))
    with pytest.raises(ValueError, match="outside the writable surface"):
        check_overrides_allowed(spec, {"mixed_precision.enabled": True})


def test_writable_surface_read_only_wins(tmp_path):
    spec = load_contract(_write(tmp_path, CONTRACT))
    with pytest.raises(ValueError, match="read-only"):
        check_overrides_allowed(spec, {"training.seed": 1})


def test_invalid_direction_is_rejected(tmp_path):
    body = CONTRACT.replace("direction: maximize", "direction: sideways")
    with pytest.raises(ValueError):
        load_contract(_write(tmp_path, body))


def test_shipped_contracts_freeze_the_sac_escape_hatch():
    """The plan forbids the cached-tensor mutation escape hatch; contracts enforce it."""
    root = Path(__file__).resolve().parents[1]
    for name in ("tiny-qwen3.yaml", "medium-qwen3.yaml"):
        spec = load_contract(root / "contracts" / name)
        with pytest.raises(ValueError, match="read-only"):
            check_overrides_allowed(
                spec, {"activation_checkpoint.allow_cache_entry_mutation": True}
            )

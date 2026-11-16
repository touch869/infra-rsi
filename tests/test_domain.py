"""Domain plugins emit only contract-approved overrides."""

from __future__ import annotations

import textwrap

import pytest

from irsi.contract import surfaces as _surfaces  # noqa: F401  (plugin registration)
from irsi.contract import check_overrides_allowed, load_contract
from irsi.registry import SURFACES


def _spec(tmp_path, layer_counts: str):
    body = f"""
    name: demo
    repo_root: /repo
    base_config: /repo/train.yaml
    domain: recompute-layerwise
    domain_params:
      layer_counts: {layer_counts}
    writable_prefixes:
      - activation_checkpoint.
    read_only_keys:
      - activation_checkpoint.allow_cache_entry_mutation
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
    budget:
      max_trials: 3
      timeout_min: 5
    """
    path = tmp_path / "contract.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_contract(path)


def test_domain_params_are_loaded(tmp_path):
    spec = _spec(tmp_path, "[0, 4, 8]")
    assert spec.domain_params == {"layer_counts": [0, 4, 8]}


def test_layerwise_candidates_cover_the_ladder(tmp_path):
    spec = _spec(tmp_path, "[8, 0, 4, 8]")
    candidates = SURFACES.create("recompute-layerwise", spec=spec)
    assert [c.id for c in candidates] == ["control", "layers-0", "layers-4", "layers-8"]
    for candidate in candidates:
        check_overrides_allowed(spec, candidate.overrides)
    layer8 = candidates[-1].overrides
    assert layer8["activation_checkpoint.selection.layer_count"] == 8
    assert (
        layer8["activation_checkpoint.selection.source"]
        == "model_adapter_safe_regions"
    )


def test_layerwise_rejects_empty_counts(tmp_path):
    spec = _spec(tmp_path, "[]")
    with pytest.raises(ValueError, match="non-empty"):
        SURFACES.create("recompute-layerwise", spec=spec)


def test_layerwise_rejects_negative_counts(tmp_path):
    spec = _spec(tmp_path, "[-1]")
    with pytest.raises(ValueError, match="non-negative"):
        SURFACES.create("recompute-layerwise", spec=spec)


def test_layerwise_rejects_bool_counts(tmp_path):
    spec = _spec(tmp_path, "[true]")
    with pytest.raises(ValueError, match="non-negative integers"):
        SURFACES.create("recompute-layerwise", spec=spec)

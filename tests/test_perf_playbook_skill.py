"""The perf-playbook skill is discovered and its offline tooling runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT / "irsi" / "knowledge" / "skills" / "strategy" / "perf-playbook"
    / "ascend" / "hyperparallel"
)


def test_perf_playbook_is_discovered_with_its_variant_metadata():
    skill = get_skill("perf-playbook", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "strategy"
    assert skill.metadata["environment"] == "ascend"
    assert skill.metadata["framework"] == "hyperparallel"


def test_perf_playbook_bundle_keeps_references_scripts_and_template():
    expected = {
        "references/feature-scenarios.md",
        "references/ascend-fusion/index.md",
        "references/ascend-fusion/catalog.json",
        "references/cases/qwen3-muon-qk-rms-20261105.md",
        "scripts/extra_flops.py",
        "scripts/fetch_ascend_docs.py",
        "templates/tuning-summary.md",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_extra_flops_help_runs():
    result = subprocess.run(
        [sys.executable, str(PROFILE / "scripts" / "extra_flops.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--spec" in result.stdout


def test_fusion_catalog_query_is_offline():
    result = subprocess.run(
        [
            sys.executable,
            str(PROFILE / "scripts" / "fetch_ascend_docs.py"),
            "--query",
            "rmsnorm",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    hits = json.loads(result.stdout)
    assert any(entry["symbol"] == "torch_npu.npu_rms_norm" for entry in hits)

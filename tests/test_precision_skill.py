"""The precision skill is discovered and exposes its msprobe tooling."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "irsi" / "knowledge" / "analysis" / "precision" / "ascend" / "generic"


def _load_module(name: str, relative: str):
    path = PROFILE / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_precision_is_discovered_under_its_variant_directory():
    skill = get_skill("precision", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "analysis"
    assert skill.metadata["environment"] == "ascend"
    assert skill.metadata["framework"] == "generic"


def test_precision_bundle_keeps_references_scripts_and_template():
    expected = {
        "references/align-flow.md",
        "references/triage-nan-spike-diverge.md",
        "scripts/collect_dump.py",
        "scripts/diff_dump.py",
        "scripts/precision_hook.py",
        "templates/precision-report.md",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_precision_cli_help_does_not_require_msprobe():
    for script in ("collect_dump.py", "diff_dump.py"):
        result = subprocess.run(
            [sys.executable, str(PROFILE / "scripts" / script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout


def test_collect_dump_expands_steps_and_nests_task_options():
    module = _load_module("precision_collect_dump", "scripts/collect_dump.py")
    assert module.parse_steps("0-2,4") == [0, 1, 2, 4]
    config = module.build_config(Path("/tmp/dump"), [0, 1], "statistics", "L1", [])
    assert config["step"] == [0, 1]
    assert config["statistics"]["summary_mode"] == "statistics"

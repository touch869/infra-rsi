"""The strategy-optimizer skill is discovered and its executable assets load."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT / "irsi" / "knowledge" / "skills" / "strategy" / "strategy-optimizer"
    / "generic" / "hyperparallel"
)


def test_strategy_optimizer_is_discovered_under_its_variant_directory():
    skill = get_skill("strategy-optimizer", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "strategy"
    assert skill.metadata["environment"] == "generic"
    assert skill.metadata["framework"] == "hyperparallel"


def test_strategy_optimizer_bundle_keeps_scripts_references_and_workflow():
    expected = {
        "README.md",
        "SUMMARY.md",
        "references/config-templates.md",
        "references/decision-rules.md",
        "references/output-format.md",
        "references/psa-cost-model.md",
        "references/validation-metrics.md",
        "scripts/run_optimization.py",
        "scripts/distributed_scheduler.py",
        "scripts/safety_checks.py",
        "scripts/metrics_output.py",
        "scripts/compare_benchmarks.py",
        "workflows/orchestration.md",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_strategy_optimizer_architecture_and_help_are_valid():
    architecture = subprocess.run(
        [sys.executable, str(PROFILE / "scripts" / "check_skill_architecture.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert architecture.returncode == 0
    assert "Architecture: PASS" in architecture.stdout

    help_result = subprocess.run(
        [sys.executable, str(PROFILE / "scripts" / "run_optimization.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--psa-config" in help_result.stdout

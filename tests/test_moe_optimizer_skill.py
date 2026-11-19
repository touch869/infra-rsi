"""The moe-optimizer skill is discovered and its workflow validation passes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT / "irsi" / "knowledge" / "skills" / "strategy" / "moe-optimizer"
    / "generic" / "hyperparallel"
)


def test_moe_optimizer_is_discovered_under_its_variant_directory():
    skill = get_skill("moe-optimizer", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "strategy"
    assert skill.metadata["environment"] == "generic"
    assert skill.metadata["framework"] == "hyperparallel"


def test_moe_optimizer_bundle_keeps_workflows_and_references():
    expected = {
        "README.md",
        "validate_skill.py",
        "workflows/01-baseline-profiling.md",
        "workflows/02-problem-diagnosis.md",
        "workflows/03-strategy-generation.md",
        "workflows/04-validation.md",
        "workflows/05-iterative-refinement.md",
        "references/case-studies.md",
        "references/optimization-strategies.md",
        "references/workflow.md",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_moe_optimizer_validation_passes():
    result = subprocess.run(
        [sys.executable, str(PROFILE / "validate_skill.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "7/7 tests passed" in result.stdout

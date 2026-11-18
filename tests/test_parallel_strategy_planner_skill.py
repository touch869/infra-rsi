"""The parallel-strategy-planner skill is discovered with all its resources."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT / "irsi" / "knowledge" / "strategy" / "parallel-strategy-planner"
    / "generic" / "hyperparallel"
)


def test_strategy_planner_is_discovered_under_its_variant_directory():
    skill = get_skill("parallel-strategy-planner", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "strategy"
    assert skill.metadata["environment"] == "generic"
    assert skill.metadata["framework"] == "hyperparallel"


def test_strategy_planner_bundle_keeps_workflows_examples_and_references():
    expected = {
        "MOE_INTEGRATION.md",
        "validate_moe_integration.py",
        "examples/moe_strategy_example.py",
        "references/io-contract.md",
        "references/known-hardware.md",
        "references/known-models.md",
        "references/memory-estimation.md",
        "references/moe-strategy-rules.md",
        "references/strategy-rules.md",
        "workflows/01-collect-model-info.md",
        "workflows/02-global-baseline.md",
        "workflows/03-strategy-search.md",
        "workflows/04-cost-analysis.md",
        "workflows/05-scoring-output.md",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_moe_integration_validation_passes():
    result = subprocess.run(
        [sys.executable, str(PROFILE / "validate_moe_integration.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "4/4 tests passed" in result.stdout

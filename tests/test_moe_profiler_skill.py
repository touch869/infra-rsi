"""The MoE profiler skill is discovered and self-contained after migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "irsi" / "knowledge" / "skills" / "analysis" / "moe-profiler" / "ascend" / "hyperparallel"


def test_moe_profiler_is_discovered_under_its_environment_directory():
    skill = get_skill("moe-profiler", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "analysis"
    assert skill.metadata["environment"] == "ascend"
    assert skill.metadata["framework"] == "hyperparallel"


def test_moe_profiler_bundle_keeps_references_and_scripts():
    expected = {
        "references/input-contract.md",
        "references/moe-metrics.md",
        "references/load-imbalance-patterns.md",
        "references/communication-overhead-analysis.md",
        "scripts/extract_moe_facts.py",
        "scripts/_moe_load_analysis.py",
        "scripts/_moe_comm_analysis.py",
        "scripts/_moe_routing_check.py",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_routing_validator_import_degrades_until_validation_is_migrated():
    path = PROFILE / "scripts" / "_moe_routing_check.py"
    spec = importlib.util.spec_from_file_location("moe_routing_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.RoutingValidator().validate(["missing-checkpoint.pt"])
    assert result["routing_status"] == "UNVERIFIED"
    assert result["gradient_status"] == "UNVERIFIED"
    assert result["warnings"]

"""Validation skills are discovered with their resources and runnable tooling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "irsi" / "knowledge" / "validation"
SKILLS = {
    "bringup-benchmark": VALIDATION / "bringup-benchmark" / "generic" / "hyperparallel",
    "formal-verification": VALIDATION / "formal-verification" / "generic" / "hyperparallel",
    "hf-model-precision-validation": (
        VALIDATION / "hf-model-precision-validation" / "ascend" / "hyperparallel"
    ),
    "routing-validator": VALIDATION / "routing-validator" / "generic" / "generic",
    "strategy-validator": VALIDATION / "strategy-validator" / "generic" / "hyperparallel",
}


def test_validation_skills_are_discovered_under_their_variants():
    for name, root in SKILLS.items():
        skill = get_skill(name, 1)
        assert skill.path == root / "SKILL.md"
        assert skill.metadata["category"] == "validation"


def test_validation_bundles_keep_their_key_resources():
    expected = {
        "bringup-benchmark": {
            "catalog/validation.yaml",
            "references/injections/drop-tied-alias-exclusion.patch",
            "scripts/bench.py",
            "templates/trial_meta.example.json",
        },
        "formal-verification": {
            "profiles.json",
            "references/training-invariants.md",
            "scripts/verify.py",
        },
        "hf-model-precision-validation": {
            "references/matrix-acceptance.md",
            "references/vlm-matrix-and-tolerances.md",
            "scripts/run_vlm_matrix.py",
            "scripts/compare_vlm_matrix.py",
        },
        "routing-validator": {
            "references/evidence-contract.md",
            "scripts/validate_routing.py",
            "validate_skill.py",
        },
        "strategy-validator": {
            "references/moe-metrics.md",
            "workflows/01-baseline-analysis.md",
            "workflows/04-comparison-report.md",
            "validate_skill_structure.py",
        },
    }
    for name, relatives in expected.items():
        assert all((SKILLS[name] / relative).is_file() for relative in relatives)


def test_validation_skill_clis_and_self_checks_run():
    commands = {
        "bringup-benchmark": [SKILLS["bringup-benchmark"] / "scripts" / "bench.py", "--help"],
        "formal-verification": [SKILLS["formal-verification"] / "scripts" / "verify.py", "--help"],
        "routing-validator": [SKILLS["routing-validator"] / "validate_skill.py"],
        "strategy-validator": [SKILLS["strategy-validator"] / "validate_skill_structure.py"],
    }
    for name, command in commands.items():
        result = subprocess.run(
            [sys.executable, *map(str, command)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{name}: {result.stdout}\n{result.stderr}"


def test_migrated_validation_docs_have_no_old_repository_paths():
    for root in SKILLS.values():
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            assert "skills/validation/" not in text, path
            assert "../../../reference/perf-playbook/" not in text, path
            assert "parallel-strategy-analyzer" not in text, path

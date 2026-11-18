"""The profiling skill is environment-scoped and self-contained after migration."""

from __future__ import annotations

from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "irsi" / "knowledge" / "analysis" / "profiling" / "ascend" / "hyperparallel"


def test_profiling_is_discovered_under_its_environment_directory():
    skill = get_skill("profiling", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "analysis"
    assert skill.metadata["environment"] == "ascend"
    assert skill.metadata["framework"] == "hyperparallel"


def test_profiling_bundle_keeps_scripts_references_and_template():
    expected = {
        "scripts/collect_prof.py",
        "scripts/prof_hook.py",
        "scripts/breakdown.py",
        "references/output-files.md",
        "references/breakdown-dimensions.md",
        "templates/perf-breakdown.html",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_skill_commands_point_at_the_migrated_path():
    skill = (PROFILE / "SKILL.md").read_text(encoding="utf-8")
    assert "irsi/knowledge/analysis/profiling/ascend/hyperparallel/scripts" in skill
    assert "skills/analysis/profiling/scripts" not in skill

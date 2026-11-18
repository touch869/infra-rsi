"""Skill packages are discovered automatically and exposed through the CLI."""

from __future__ import annotations

import json

import pytest

from irsi.cli import main
from irsi.knowledge import DEFAULT_CATALOG, SkillCatalog, SkillLoadError, get_skill


def test_package_skill_is_loaded_automatically():
    skills = DEFAULT_CATALOG.list_skills()
    assert [skill.name for skill in skills] == [
        "bringup-benchmark", "experiment-record", "formal-verification",
        "hf-model-precision-validation", "memory-analysis", "moe-optimizer",
        "moe-profiler", "parallel-strategy-planner", "perf-playbook",
        "precision", "profiling", "routing-validator",
        "sapp-parallel-strategy", "strategy-optimizer", "strategy-validator"]
    skill = get_skill("experiment-record", 1)
    assert "append-only" in skill.description
    assert skill.read_text("references/field-dictionary.md").startswith("# Field Dictionary")
    assert "step" in json.loads(skill.read_text("schemas/experiment-record.schema.json"))["required"]
    profiling = get_skill("profiling", 1)
    assert profiling.metadata["environment"] == "ascend"
    assert profiling.metadata["framework"] == "hyperparallel"
    assert "torch_npu" in profiling.read_text("scripts/prof_hook.py")
    moe_profiler = get_skill("moe-profiler", 1)
    assert moe_profiler.metadata["environment"] == "ascend"
    assert moe_profiler.metadata["framework"] == "hyperparallel"
    assert "extract_moe_facts.py" in moe_profiler.read_text("SKILL.md")
    moe_optimizer = get_skill("moe-optimizer", 1)
    assert moe_optimizer.metadata["category"] == "strategy"
    assert moe_optimizer.metadata["environment"] == "generic"
    assert moe_optimizer.metadata["framework"] == "hyperparallel"
    strategy = get_skill("parallel-strategy-planner", 1)
    assert strategy.metadata["category"] == "strategy"
    assert strategy.metadata["environment"] == "generic"
    assert strategy.metadata["framework"] == "hyperparallel"
    assert "moe-strategy-rules.md" in strategy.read_text("SKILL.md")
    sapp = get_skill("sapp-parallel-strategy", 1)
    assert sapp.metadata["environment"] == "ascend"
    assert sapp.metadata["framework"] == "hyperparallel"
    assert "HYPER_PARALLEL_ROOT" in sapp.read_text("SKILL.md")
    optimizer = get_skill("strategy-optimizer", 1)
    assert optimizer.metadata["category"] == "strategy"
    assert optimizer.metadata["environment"] == "generic"
    assert optimizer.metadata["framework"] == "hyperparallel"
    assert "run_optimization.py" in optimizer.read_text("SKILL.md")
    playbook = get_skill("perf-playbook", 1)
    assert playbook.metadata["category"] == "strategy"
    assert playbook.metadata["environment"] == "ascend"
    assert playbook.metadata["framework"] == "hyperparallel"
    assert "feature-scenarios.md" in playbook.read_text("SKILL.md")
    precision = get_skill("precision", 1)
    assert precision.metadata["environment"] == "ascend"
    assert precision.metadata["framework"] == "generic"
    assert "msprobe" in precision.read_text("SKILL.md")
    memory = get_skill("memory-analysis", 1)
    assert memory.metadata["environment"] == "ascend"
    assert memory.metadata["framework"] == "generic"
    assert "torch_npu" in memory.read_text("scripts/mem_hook.py")
    bringup = get_skill("bringup-benchmark", 1)
    assert bringup.metadata["category"] == "validation"
    assert bringup.metadata["environment"] == "generic"
    assert bringup.metadata["framework"] == "hyperparallel"
    formal = get_skill("formal-verification", 1)
    assert formal.metadata["category"] == "validation"
    assert formal.read_text("profiles.json").find("../../rules") == -1
    hf_precision = get_skill("hf-model-precision-validation", 1)
    assert hf_precision.metadata["category"] == "validation"
    assert hf_precision.metadata["environment"] == "ascend"
    routing = get_skill("routing-validator", 1)
    assert routing.metadata["category"] == "validation"
    assert routing.metadata["environment"] == "generic"
    assert routing.metadata["framework"] == "generic"
    strategy_validator = get_skill("strategy-validator", 1)
    assert strategy_validator.metadata["category"] == "validation"
    assert strategy_validator.metadata["framework"] == "hyperparallel"


def test_catalog_discovers_a_new_skill_directory(tmp_path):
    root = tmp_path / "skills" / "demo"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: demo\nversion: 2\ndescription: demo skill\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    catalog = SkillCatalog.discover(tmp_path / "skills")
    assert catalog.get_skill("demo", 2).body.startswith("\n# Demo")
    assert catalog.get_skill("demo").version == 2


def test_invalid_frontmatter_fails_loudly(tmp_path):
    root = tmp_path / "skills" / "broken"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("no frontmatter\n", encoding="utf-8")
    with pytest.raises(SkillLoadError, match="frontmatter"):
        SkillCatalog.discover(tmp_path / "skills")


def test_cli_lists_and_shows_the_packaged_skill(capsys):
    assert main(["skills", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["name"] for item in listed] == [
        "bringup-benchmark", "experiment-record", "formal-verification",
        "hf-model-precision-validation", "memory-analysis", "moe-optimizer",
        "moe-profiler", "parallel-strategy-planner", "perf-playbook",
        "precision", "profiling", "routing-validator",
        "sapp-parallel-strategy", "strategy-optimizer", "strategy-validator"]

    assert main(["skills", "experiment-record", "--body"]) == 0
    shown = capsys.readouterr().out
    assert "# Experiment Record" in shown

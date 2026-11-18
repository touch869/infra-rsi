"""Skill packages are discovered automatically and exposed through the CLI."""

from __future__ import annotations

import json

import pytest

from irsi.cli import main
from irsi.knowledge import DEFAULT_CATALOG, SkillCatalog, SkillLoadError, get_skill


def test_package_skill_is_loaded_automatically():
    skills = DEFAULT_CATALOG.list_skills()
    assert [skill.name for skill in skills] == ["experiment-record"]
    skill = get_skill("experiment-record", 1)
    assert "append-only" in skill.description
    assert skill.read_text("references/field-dictionary.md").startswith("# Field Dictionary")
    assert "step" in json.loads(skill.read_text("schemas/experiment-record.schema.json"))["required"]


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
    assert [item["name"] for item in listed] == ["experiment-record"]

    assert main(["skills", "experiment-record", "--body"]) == 0
    shown = capsys.readouterr().out
    assert "# Experiment Record" in shown

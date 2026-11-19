"""The experiment-record schema and templates enforce the per-step contract."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "irsi" / "knowledge" / "skills" / "runtime" / "experiment-record"


def test_schema_requires_step_evidence_and_commit_accounting():
    schema = json.loads((RECORD / "schemas" / "experiment-record.schema.json").read_text(encoding="utf-8"))
    assert "step" in schema["required"]
    step = schema["properties"]["step"]
    assert set(step["required"]) == {"why", "changes", "test_result", "commit"}
    commit = step["properties"]["commit"]
    assert set(commit["required"]) == {"commit_ref", "docs_included", "code_restored"}
    assert commit["properties"]["docs_included"]["const"] is True


def test_templates_request_the_three_step_answers_and_commit_disposition():
    log = (RECORD / "templates" / "experiment_log.md").read_text(encoding="utf-8")
    for heading in ("**Why:**", "**What changed:**", "**Test result:**", "**Commit:**", "**Evidence:**"):
        assert heading in log

    header = (RECORD / "templates" / "results.tsv").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("timestamp\tcommit\ttrial\t")


def test_skill_is_concise_and_matches_runtime_artifacts():
    skill = (RECORD / "SKILL.md").read_text(encoding="utf-8")
    assert len(skill.splitlines()) <= 200
    for artifact in ("results.tsv", "candidates.jsonl", "experiment_log.md", "events.jsonl", "report.md"):
        assert artifact in skill
    for stale in ("history.jsonl", "REPORT.md", "autoresearch"):
        assert stale not in skill
    for working_file in ("ideas.md", "learnings.md"):
        assert working_file in skill


def test_idea_and_learning_templates_are_present():
    ideas = (RECORD / "templates" / "ideas.md").read_text(encoding="utf-8")
    learnings = (RECORD / "templates" / "learnings.md").read_text(encoding="utf-8")
    assert "# Experiment ideas" in ideas
    assert "Retry when:" in ideas
    assert "# Experiment learnings" in learnings
    assert "applicability limits" in learnings

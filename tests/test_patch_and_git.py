"""Observation patch apply/revert and git commit recorder."""

from __future__ import annotations

import subprocess
from pathlib import Path

from irsi.experts import ObservationPatch
from irsi.git import CommitRecorder
from irsi.runtime import ObservationPatchManager


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def test_observation_patch_apply_and_revert(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")

    file = repo / "train.py"
    file.write_text("a\nb\n", encoding="utf-8")

    patch = ObservationPatch(
        target_files=("train.py",),
        diff=(
            "diff --git a/train.py b/train.py\n"
            "--- a/train.py\n"
            "+++ b/train.py\n"
            "@@ -1,2 +1,3 @@\n"
            " a\n"
            " b\n"
            "+c\n"
        ),
    )

    manager = ObservationPatchManager(repo)
    manager.apply(patch)
    assert file.read_text(encoding="utf-8") == "a\nb\nc\n"

    manager.revert(patch)
    assert file.read_text(encoding="utf-8") == "a\nb\n"


def test_commit_recorder_commits_report_and_reverts(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    candidate = repo / "candidate.txt"
    candidate.write_text("v1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    candidate.write_text("v2\n", encoding="utf-8")
    (repo / "report.md").write_text("# report\n", encoding="utf-8")

    recorder = CommitRecorder(repo)
    commit = recorder.commit(
        "candidate patch + report",
        files=("candidate.txt",),
        report_path="report.md",
    )
    assert commit
    assert candidate.read_text(encoding="utf-8") == "v2\n"

    recorder.revert(commit)
    assert candidate.read_text(encoding="utf-8") == "v1\n"
    assert not (repo / "report.md").exists()

"""Environment snapshot capture."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from irsi.contract import load_contract
from irsi.environment import EnvironmentSnapshot

TASK_PATH = Path(__file__).resolve().parents[1] / "examples/specs/hyperparallel-recompute.yaml"
TASK = load_contract(TASK_PATH)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def test_environment_snapshot_capture(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "base.yaml").write_text("model: qwen3\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    spec = replace(TASK, repo_root=str(repo))
    snapshot = EnvironmentSnapshot.capture(spec)

    assert snapshot.repo_root == str(repo)
    assert snapshot.repo_commit
    assert snapshot.python
    payload = snapshot.to_dict()
    assert payload["repo_commit"] == snapshot.repo_commit
    assert payload["platform"] == snapshot.platform

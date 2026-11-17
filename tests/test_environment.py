"""Environment snapshot capture."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from irsi.contract import load_contract
from irsi.environment import EnvironmentRepairAgent, EnvironmentSnapshot

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


def test_environment_repair_agent_reruns_env_setup():
    spec = replace(TASK, env_setup="true")
    agent = EnvironmentRepairAgent(spec)

    diagnosis = agent.diagnose(OSError("missing dependency"))
    assert diagnosis.kind == "env_error"

    action = agent.repair(OSError("missing dependency"))
    assert action.action == "env_setup"
    assert action.success is True


def test_environment_repair_agent_refuses_without_env_setup():
    spec = replace(TASK, env_setup="")
    agent = EnvironmentRepairAgent(spec)
    action = agent.repair(OSError("missing dependency"))
    assert action.action == "no_env_setup"
    assert action.success is False


def test_environment_repair_agent_respects_attempt_budget():
    spec = replace(TASK, env_setup="true")
    agent = EnvironmentRepairAgent(spec, max_attempts=1)
    first = agent.repair(OSError("missing dependency"))
    second = agent.repair(OSError("missing dependency"))
    assert first.success is True
    assert second.action == "exhausted"
    assert second.success is False


def test_environment_repair_agent_uses_allowlisted_package_command():
    spec = replace(
        TASK,
        env_setup="",
        domain_params={
            "environment_repair": {
                "commands": ["true"],
            }
        },
    )
    agent = EnvironmentRepairAgent(spec)
    diagnosis = agent.diagnose(ModuleNotFoundError("No module named 'foo'"))
    assert diagnosis.kind == "package_error"

    action = agent.repair(ModuleNotFoundError("No module named 'foo'"))
    assert action.action == "allowlisted_command"
    assert action.command == "true"
    assert action.success is True

    command, action_name = agent._select_command(diagnosis)
    assert action_name == "allowlisted_command"
    assert command == "true"

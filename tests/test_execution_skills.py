"""Execution skills are discovered, runnable, and use migrated shared assets."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "irsi" / "knowledge" / "execution"
AUTORESEARCH = EXECUTION / "autoresearch"
MFU_RISER = EXECUTION / "mfu-riser" / "ascend" / "hyperparallel"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_execution_skills_are_discovered_under_their_paths():
    autoresearch = get_skill("autoresearch", 1)
    assert autoresearch.path == AUTORESEARCH / "SKILL.md"
    assert autoresearch.metadata["category"] == "execution"
    mfu_riser = get_skill("mfu-riser", 1)
    assert mfu_riser.path == MFU_RISER / "SKILL.md"
    assert mfu_riser.metadata["category"] == "execution"
    assert mfu_riser.metadata["environment"] == "ascend"
    assert mfu_riser.metadata["framework"] == "hyperparallel"


def test_execution_bundles_keep_scripts_references_and_templates():
    expected = {
        AUTORESEARCH: {
            "scripts/autoresearch.py",
            "scripts/config.py",
            "scripts/loop.py",
            "templates/manual.md",
        },
        MFU_RISER: {
            "references/acceptance.md",
            "references/contracts.md",
            "references/planner.md",
            "scripts/audit_rank_steps.py",
            "scripts/collect_state.py",
            "scripts/mfu_riser.py",
            "scripts/riser_contract.py",
        },
    }
    for root, relatives in expected.items():
        assert all((root / relative).is_file() for relative in relatives)


def test_execution_help_commands_run():
    commands = [
        AUTORESEARCH / "scripts" / "autoresearch.py",
        MFU_RISER / "scripts" / "mfu_riser.py",
        MFU_RISER / "scripts" / "collect_state.py",
        MFU_RISER / "scripts" / "audit_rank_steps.py",
    ]
    for script in commands:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{script}: {result.stdout}\n{result.stderr}"


def test_autoresearch_init_uses_runtime_experiment_templates(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    result = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "init",
            "--run-dir", str(run_dir),
            "--target", "target.py",
            "--benchmark-cmd", "python -c 'print(1)'",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    shared = ROOT / "irsi" / "knowledge" / "runtime" / "experiment-record" / "templates"
    for name in ("ideas.md", "results.tsv", "learnings.md", "experiment_log.md"):
        assert (run_dir / name).read_text(encoding="utf-8") == (shared / name).read_text(encoding="utf-8")


def test_mfu_collect_state_targets_migrated_profiling_parser():
    module = _load_module("mfu_collect_state", MFU_RISER / "scripts" / "collect_state.py")
    expected = (
        ROOT / "irsi" / "knowledge" / "analysis" / "profiling"
        / "ascend" / "hyperparallel" / "scripts" / "breakdown.py"
    )
    assert module.KNOWLEDGE == ROOT / "irsi" / "knowledge"
    assert expected.is_file()


def test_execution_docs_have_no_old_repository_paths():
    for path in EXECUTION.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "skills/workflows/" not in text, path
        assert "../../reference/perf-playbook/" not in text, path
        assert "parallel-strategy-analyzer" not in text, path

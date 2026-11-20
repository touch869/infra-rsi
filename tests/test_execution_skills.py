"""Execution skills are discovered, runnable, and use migrated shared assets."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "irsi" / "knowledge" / "skills" / "execution"
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
    shared = ROOT / "irsi" / "knowledge" / "skills" / "runtime" / "experiment-record" / "templates"
    for name in ("ideas.md", "results.tsv", "learnings.md", "experiment_log.md"):
        assert (run_dir / name).read_text(encoding="utf-8") == (shared / name).read_text(encoding="utf-8")


def test_autoresearch_init_can_use_a_separate_baseline_command(tmp_path):
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
            "--baseline-cmd", "python -m irsi.cli measure --contract contract.yaml",
            "--benchmark-cmd", "python -m irsi.cli measure --reference baseline.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["baseline_cmd"][:3] == ["python", "-m", "irsi.cli"]
    assert payload["benchmark_cmd"][:3] == ["python", "-m", "irsi.cli"]


def test_autoresearch_baseline_uses_its_own_command(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "baseline.sh").write_text("echo IRSI_MEASURE_METRIC=10\n", encoding="utf-8")
    (tmp_path / "benchmark.sh").write_text("echo IRSI_MEASURE_METRIC=20\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    run_dir = tmp_path / "run"
    init = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "init",
            "--run-dir", str(run_dir),
            "--target", "target.py",
            "--baseline-cmd", f"sh {tmp_path / 'baseline.sh'}",
            "--benchmark-cmd", f"sh {tmp_path / 'benchmark.sh'}",
            "--metric-pattern", r"IRSI_MEASURE_METRIC=(?P<metric>[0-9.]+)",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert init.returncode == 0, f"{init.stdout}\n{init.stderr}"
    baseline = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "baseline", "--run-dir", str(run_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert baseline.returncode == 0, f"{baseline.stdout}\n{baseline.stderr}"
    receipt = json.loads((run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["record_type"] == "baseline"
    assert receipt["result"]["metric"] == 10.0


def test_autoresearch_init_infers_baseline_artifact(tmp_path):
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
            "--baseline-cmd",
            "python -m irsi.cli measure --freeze-baseline run/baseline.json",
            "--benchmark-cmd", "python -m irsi.cli measure --reference run/baseline.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["baseline_artifact"] == "baseline.json"


def test_autoresearch_init_rejects_baseline_artifact_outside_run(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "init",
            "--run-dir", str(tmp_path / "run"),
            "--target", "target.py",
            "--benchmark-cmd", "python -c 'print(1)'",
            "--baseline-artifact", "../outside.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "inside the run directory" in result.stderr


def test_autoresearch_baseline_commits_traceability_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "baseline.py").write_text(
        """
import json
import subprocess

head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
payload = {
    "schema": "infra-rsi-measurement/v1",
    "task": "traceability-test",
    "identity": {"metric": "tokens/s"},
    "contract_hash": "a" * 64,
    "contract_lock": {
        "contract_hash": "a" * 64,
        "confirmation_code": "a" * 12,
        "statement": "confirmed",
    },
    "metric": 10.0,
    "numeric_hash": "b" * 64,
    "source_commit": head,
}
open("run/baseline.json", "w", encoding="utf-8").write(json.dumps(payload))
print("IRSI_MEASURE_METRIC=10.0")
""",
        encoding="utf-8",
    )
    (tmp_path / "benchmark.py").write_text(
        'print("IRSI_MEASURE_METRIC=20.0")\n', encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    run_dir = tmp_path / "run"
    init = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "init",
            "--run-dir", str(run_dir),
            "--target", "target.py",
            "--baseline-cmd", "python baseline.py --freeze-baseline run/baseline.json",
            "--benchmark-cmd", "python benchmark.py",
            "--metric-pattern", r"IRSI_MEASURE_METRIC=(?P<metric>[0-9.]+)",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert init.returncode == 0, f"{init.stdout}\n{init.stderr}"
    baseline = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "baseline", "--run-dir", str(run_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert baseline.returncode == 0, f"{baseline.stdout}\n{baseline.stderr}"

    committed = subprocess.check_output(
        ["git", "-C", str(tmp_path), "show", "--name-only", "--format="],
        text=True,
    ).splitlines()
    assert {
        "run/run.json",
        "run/manual.md",
        "run/baseline.json",
        "run/results.tsv",
        "run/candidates.jsonl",
        "run/experiment_log.md",
        "run/ideas.md",
        "run/learnings.md",
    } <= set(committed)
    assert subprocess.check_output(
        ["git", "-C", str(tmp_path), "status", "--porcelain"], text=True
    ).strip() == ""

    receipt = json.loads((run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    trace = receipt["extensions"]["autoresearch"]["traceability"]
    for key, relative in (
        ("run_config", "run/run.json"),
        ("manual", "run/manual.md"),
        ("baseline_artifact", "run/baseline.json"),
    ):
        expected = hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
        assert trace[key]["path"] == relative
        assert trace[key]["sha256"] == expected
    assert trace["baseline_artifact"]["contract_hash"] == "a" * 64
    assert trace["baseline_artifact"]["numeric_hash"] == "b" * 64

    (run_dir / "run.json").write_text(
        (run_dir / "run.json").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    (tmp_path / "target.py").write_text("value = 2\n", encoding="utf-8")
    blocked = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "iterate", "--run-dir", str(run_dir),
            "--description", "change target",
            "--why", "test protected traceability files",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode != 0
    assert "traceability files changed after baseline" in blocked.stderr


def test_autoresearch_baseline_requires_configured_evidence(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True)
    (tmp_path / "target.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "baseline.sh").write_text("echo IRSI_MEASURE_METRIC=10\n", encoding="utf-8")
    (tmp_path / "benchmark.sh").write_text("echo IRSI_MEASURE_METRIC=20\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    run_dir = tmp_path / "run"
    init = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "init",
            "--run-dir", str(run_dir),
            "--target", "target.py",
            "--baseline-cmd", "sh baseline.sh",
            "--benchmark-cmd", "sh benchmark.sh",
            "--baseline-artifact", "baseline.json",
            "--metric-pattern", r"IRSI_MEASURE_METRIC=(?P<metric>[0-9.]+)",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert init.returncode == 0, f"{init.stdout}\n{init.stderr}"
    baseline = subprocess.run(
        [
            sys.executable,
            str(AUTORESEARCH / "scripts" / "autoresearch.py"),
            "baseline", "--run-dir", str(run_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert baseline.returncode != 0
    assert "baseline artifact was not written" in baseline.stderr


def test_mfu_collect_state_targets_migrated_profiling_parser():
    module = _load_module("mfu_collect_state", MFU_RISER / "scripts" / "collect_state.py")
    expected = (
        ROOT / "irsi" / "knowledge" / "skills" / "analysis" / "profiling"
        / "ascend" / "hyperparallel" / "scripts" / "breakdown.py"
    )
    assert module.KNOWLEDGE == ROOT / "irsi" / "knowledge" / "skills"
    assert expected.is_file()


def test_execution_docs_have_no_old_repository_paths():
    for path in EXECUTION.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "skills/workflows/" not in text, path
        assert "../../reference/perf-playbook/" not in text, path
        assert "parallel-strategy-analyzer" not in text, path

"""The sapp-parallel-strategy skill is discovered with its pricing data and scripts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT / "irsi" / "knowledge" / "skills" / "strategy" / "sapp-parallel-strategy"
    / "ascend" / "hyperparallel"
)


def test_sapp_strategy_is_discovered_under_its_variant_directory():
    skill = get_skill("sapp-parallel-strategy", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "strategy"
    assert skill.metadata["environment"] == "ascend"
    assert skill.metadata["framework"] == "hyperparallel"


def test_sapp_strategy_bundle_keeps_calibration_timing_and_templates():
    expected = {
        "calibration/a3.json",
        "calibration/clusters.json",
        "references/status.md",
        "references/timers.json",
        "references/trust.json",
        "references/timed/deepseek_v41_a3/README.md",
        "references/timed/deepseek_v41_a3/runs.csv",
        "references/timed/deepseek_v41_a3/steps.csv",
        "scripts/answer.py",
        "scripts/ask.py",
        "scripts/check.py",
        "scripts/launch.py",
        "scripts/plan.py",
        "scripts/readback.py",
        "scripts/timing.py",
        "templates/deepseek_v41.yaml",
        "templates/deepseek_v41/config.json",
        "templates/deepseek_v41/engram_depth_preserving_d8.json.gz",
        "templates/deepseek_v41_description.yaml",
        "templates/qwen3_5_moe.yaml",
        "templates/qwen3_5_moe/config.json",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_ask_script_exposes_the_pricing_interface():
    result = subprocess.run(
        [sys.executable, str(PROFILE / "scripts" / "ask.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--family" in result.stdout
    assert "--cluster" in result.stdout


def test_ask_script_resolves_hyperparallel_checkout_from_environment(tmp_path):
    checkout = tmp_path / "hyper-parallel"
    (checkout / "hyper_parallel").mkdir(parents=True)
    (checkout / "hyper_parallel" / "__init__.py").write_text("", encoding="utf-8")
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import ask\n"
        "print(ask.repo_root())\n"
    )
    env = dict(os.environ, HYPER_PARALLEL_ROOT=str(checkout))
    result = subprocess.run(
        [sys.executable, "-c", code, str(PROFILE / "scripts")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == str(checkout)

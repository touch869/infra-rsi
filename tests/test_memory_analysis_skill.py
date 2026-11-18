"""The memory-analysis skill is discovered and produces a migrated report."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from irsi.knowledge import get_skill


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "irsi" / "knowledge" / "analysis" / "memory-analysis" / "ascend" / "generic"


def _load_breakdown():
    path = PROFILE / "scripts" / "breakdown.py"
    spec = importlib.util.spec_from_file_location("memory_breakdown", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_analysis_is_discovered_under_its_environment_directory():
    skill = get_skill("memory-analysis", 1)
    assert skill.path == PROFILE / "SKILL.md"
    assert skill.metadata["category"] == "analysis"
    assert skill.metadata["environment"] == "ascend"
    assert skill.metadata["framework"] == "generic"


def test_memory_analysis_bundle_keeps_scripts_references_and_template():
    expected = {
        "scripts/collect_snapshot.py",
        "scripts/mem_hook.py",
        "scripts/breakdown.py",
        "references/snapshot-format.md",
        "references/breakdown-dimensions.md",
        "templates/memory-breakdown.html",
    }
    assert all((PROFILE / relative).is_file() for relative in expected)


def test_breakdown_renders_a_json_snapshot(tmp_path):
    block = {
        "size": 1024 * 1024,
        "requested_size": 1024 * 1024,
        "state": "active_allocated",
        "frames": [{"filename": "/workspace/train.py", "line": 12, "name": "forward"}],
    }
    snapshot = {
        "segments": [{
            "total_size": 2 * 1024 * 1024,
            "allocated_size": 1024 * 1024,
            "active_size": 1024 * 1024,
            "blocks": [
                block,
                {"size": 1024 * 1024, "state": "inactive", "frames": []},
            ],
        }],
        "device_traces": [],
    }
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    (tmp_path / "snapshot.json.stats.json").write_text(json.dumps({
        "memory_reserved": 2 * 1024 * 1024,
        "memory_allocated": 1024 * 1024,
        "max_memory_allocated": 1024 * 1024,
    }), encoding="utf-8")

    report = tmp_path / "report.html"
    record = tmp_path / "report.json"
    assert _load_breakdown().main([
        "--snapshot", str(snapshot_path), "--out", str(report), "--json", str(record),
    ]) == 0
    html = report.read_text(encoding="utf-8")
    assert "<!--TOTAL_ROWS-->" not in html
    assert "Activations" in html
    assert json.loads(record.read_text(encoding="utf-8"))["stats"]["allocated_mib"] == 1.0

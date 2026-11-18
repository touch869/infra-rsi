"""Append-only evidence on disk: one directory per task, one subdirectory per trial."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

__all__ = ["TaskLedger"]

_RESULTS_HEADER = (
    "timestamp\tcommit\ttrial\tmetric\tstatus\tdelta_vs_best\tdescription\n"
)
_EXPERIMENT_LOG_HEADER = (
    "# Experiment log\n\n"
    "Append one entry per experiment step. Never rewrite previous entries.\n"
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "trial"


class TaskLedger:
    """Owns the on-disk layout of one task."""

    def __init__(self, root: str | Path, task: Mapping[str, Any]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "trials").mkdir(exist_ok=True)
        self.write_json("task.json", dict(task))
        self.write_json("state.json", {"status": "CREATED", "updated": _now()})

    # -- paths -----------------------------------------------------------
    @property
    def results_path(self) -> Path:
        return self.root / "results.tsv"

    @property
    def candidates_path(self) -> Path:
        return self.root / "candidates.jsonl"

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def experiment_log_path(self) -> Path:
        return self.root / "experiment_log.md"

    def trial_dir(self, label: str) -> Path:
        path = self.root / "trials" / _slug(label)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- writes ----------------------------------------------------------
    def write_json(self, name: str | Path, payload: Any) -> Path:
        """Atomically write a JSON document relative to the task root."""
        path = Path(name)
        if not path.is_absolute():
            path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def append_jsonl(self, name: str, payload: Mapping[str, Any]) -> None:
        path = self.root / name
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n")

    def event(self, kind: str, **fields: Any) -> None:
        self.append_jsonl("events.jsonl", {"ts": _now(), "kind": kind, **fields})

    def append_result(
        self,
        *,
        trial: str,
        metric: float | None,
        status: str,
        delta_vs_best: float | None,
        description: str,
        commit_ref: str | None = None,
    ) -> None:
        if not self.results_path.exists():
            self.results_path.write_text(_RESULTS_HEADER, encoding="utf-8")
        value = "nan" if metric is None else f"{metric:.6g}"
        delta = "" if delta_vs_best is None else f"{delta_vs_best:+.6f}"
        commit = commit_ref or "pending"
        with self.results_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f"{_now()}\t{_tsv(commit)}\t{_tsv(trial)}\t{value}\t{status}\t"
                f"{delta}\t{_tsv(description)}\n"
            )

    def append_experiment_log(
        self,
        *,
        record_id: str,
        trial: str,
        decision: str,
        why: str,
        changes: list[str],
        test_result: str,
        commit_ref: str,
        code_restored: bool,
        rollback_ref: str | None,
        evidence: Mapping[str, str] | None = None,
    ) -> None:
        """Append one human-readable step entry to ``experiment_log.md``."""
        if not self.experiment_log_path.exists():
            self.experiment_log_path.write_text(_EXPERIMENT_LOG_HEADER, encoding="utf-8")

        change_lines = "\n".join(f"  - `{change}`" for change in changes)
        rollback = rollback_ref or "not applicable"
        evidence_lines = "\n".join(
            f"  - {kind}: `{path}`" for kind, path in (evidence or {}).items()
        ) or "  - none recorded"
        entry = (
            f"\n## {trial} - {decision} ({record_id})\n\n"
            f"- **Experiment identity:** trial `{trial}`, record `{record_id}`.\n"
            f"- **Why:** {why}\n"
            f"- **What changed:**\n{change_lines}\n"
            f"- **Test result:** {test_result}\n"
            f"- **Commit:** `{commit_ref}`; docs included; "
            f"code restored: `{str(code_restored).lower()}`; rollback: `{rollback}`.\n"
            f"- **Evidence:**\n{evidence_lines}\n"
        )
        with self.experiment_log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(entry)

    def set_state(self, status: str, **extra: Any) -> None:
        self.write_json("state.json", {"status": status, "updated": _now(), **extra})


def _tsv(value: str) -> str:
    """Keep one result row on one TSV line."""
    return value.replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")

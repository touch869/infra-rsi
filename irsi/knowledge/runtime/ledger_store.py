"""Append-only evidence on disk: one directory per task, one subdirectory per trial."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

__all__ = ["TaskLedger"]

_RESULTS_HEADER = "timestamp\ttrial\tmetric\tstatus\tdelta_vs_best\tdescription\n"


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
    ) -> None:
        if not self.results_path.exists():
            self.results_path.write_text(_RESULTS_HEADER, encoding="utf-8")
        value = "nan" if metric is None else f"{metric:.6g}"
        delta = "" if delta_vs_best is None else f"{delta_vs_best:+.6f}"
        with self.results_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{_now()}\t{trial}\t{value}\t{status}\t{delta}\t{description}\n")

    def set_state(self, status: str, **extra: Any) -> None:
        self.write_json("state.json", {"status": status, "updated": _now(), **extra})

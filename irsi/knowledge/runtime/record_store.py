"""Append-only store for semantic experiment records."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .experiment_record import ExperimentRecord

__all__ = ["ExperimentRecordStore", "RoundSummary"]


@dataclass(frozen=True)
class RoundSummary:
    """One round's baseline, best record, counts, and ordered steps."""

    round_id: str
    baseline_metric: float | None
    best_record: ExperimentRecord | None
    counts: Mapping[str, int]
    steps: tuple[ExperimentRecord, ...]


class ExperimentRecordStore:
    """Append semantic records to ``records.jsonl`` and query them read-only."""

    def __init__(self, root: str | Path, *, records_path: str | Path | None = None) -> None:
        self.root = Path(root)
        self.records_path = Path(records_path) if records_path is not None else self.root / "records.jsonl"

    def append(self, record: ExperimentRecord) -> ExperimentRecord:
        """Append one record; generate id/timestamp if absent."""
        normalized = record
        if not normalized.record_id:
            normalized = replace(
                normalized,
                record_id=f"{normalized.round_id}-{normalized.step_id:04d}",
            )
        if not normalized.timestamp:
            normalized = replace(
                normalized,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True)
        with self.records_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return normalized

    def all(self) -> list[ExperimentRecord]:
        if not self.records_path.is_file():
            return []
        records = []
        for line in self.records_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(ExperimentRecord.from_dict(json.loads(line)))
        return records

    def get(self, record_id: str) -> ExperimentRecord | None:
        for record in self.all():
            if record.record_id == record_id:
                return record
        return None

    def recent(self, limit: int = 10, *, round_id: str | None = None) -> list[ExperimentRecord]:
        return self.query(round_id=round_id, limit=limit)

    def query(
        self,
        *,
        round_id: str | None = None,
        status: str | None = None,
        surface: str | None = None,
        stage: str | None = None,
        limit: int | None = None,
    ) -> list[ExperimentRecord]:
        records = []
        for record in self.all():
            if round_id is not None and record.round_id != round_id:
                continue
            if status is not None and record.status != status:
                continue
            if surface is not None and record.surface != surface:
                continue
            if stage is not None and record.stage != stage:
                continue
            records.append(record)

        records.sort(key=lambda record: (record.round_id, record.step_id, record.timestamp))
        if limit is not None:
            records = records[-limit:]
        return records

    def summary(self, round_id: str, *, maximize: bool = True) -> RoundSummary:
        records = self.query(round_id=round_id)
        counts: dict[str, int] = {}
        for record in records:
            counts[record.status] = counts.get(record.status, 0) + 1

        calibrated = next((record for record in records if record.stage == "calibrated"), None)
        baseline = next((record for record in records if record.stage == "baseline"), None)
        if calibrated is not None:
            baseline_metric = calibrated.baseline_metric
            if baseline_metric is None:
                baseline_metric = calibrated.metric
        else:
            baseline_metric = baseline.metric if baseline is not None else None

        kept = [record for record in records if record.status == "keep" and record.metric is not None]
        if kept:
            best = max(kept, key=lambda record: record.metric) if maximize else min(
                kept, key=lambda record: record.metric
            )
        else:
            best = None

        return RoundSummary(
            round_id=round_id,
            baseline_metric=baseline_metric,
            best_record=best,
            counts=counts,
            steps=tuple(records),
        )

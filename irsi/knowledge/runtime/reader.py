"""Read-only runtime knowledge queries for orchestration and experts."""

from __future__ import annotations

from dataclasses import dataclass

from .experiment_record import ExperimentRecord
from .record_store import ExperimentRecordStore

__all__ = ["KnowledgeBundle", "RuntimeKnowledgeReader"]


@dataclass(frozen=True)
class KnowledgeBundle:
    """Runtime evidence handed to one stage; it is not a skill bundle."""

    records: tuple[ExperimentRecord, ...]
    best_record: ExperimentRecord | None
    failures: tuple[ExperimentRecord, ...]


class RuntimeKnowledgeReader:
    """Read-only facade over the experiment record store."""

    def __init__(self, store: ExperimentRecordStore) -> None:
        self.store = store

    def recent(self, limit: int = 10, *, round_id: str | None = None) -> list[ExperimentRecord]:
        return self.store.recent(limit, round_id=round_id)

    def best(
        self,
        surface: str | None = None,
        *,
        round_id: str | None = None,
        maximize: bool = True,
    ) -> ExperimentRecord | None:
        records = self.store.query(
            round_id=round_id,
            surface=surface,
            status="keep",
        )
        records = [record for record in records if record.metric is not None]
        if not records:
            return None
        return max(records, key=lambda record: record.metric) if maximize else min(
            records, key=lambda record: record.metric
        )

    def failures(self, surface: str | None = None, limit: int = 10) -> list[ExperimentRecord]:
        return self.store.query(status="crash", surface=surface, limit=limit)

    def bundle(
        self,
        *,
        round_id: str | None = None,
        limit: int = 10,
    ) -> KnowledgeBundle:
        records = tuple(self.store.recent(limit, round_id=round_id))
        best = self.best(round_id=round_id)
        failures = tuple(self.store.query(status="crash", round_id=round_id, limit=limit))
        return KnowledgeBundle(records=records, best_record=best, failures=failures)

"""Semantic experiment record stored by the runtime knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["ExperimentRecord"]


@dataclass(frozen=True)
class ExperimentRecord:
    """A compact record of one stage or trial.

    Only the first block is required for phase 1; the rest is audit/traceability
    metadata that can stay empty until the corresponding runtime exists.
    """

    record_id: str
    round_id: str
    step_id: int
    stage: str
    hypothesis_id: str | None = None
    overrides: Mapping[str, Any] = field(default_factory=dict)
    metric: float | None = None
    status: str = ""
    detail: str = ""
    artifacts: Mapping[str, str] = field(default_factory=dict)
    timestamp: str = ""
    surface: str | None = None
    baseline_metric: float | None = None
    gates: tuple[Mapping[str, Any], ...] = ()
    environment_snapshot: Mapping[str, Any] = field(default_factory=dict)
    environment_action: Mapping[str, Any] = field(default_factory=dict)
    observation_patch: Mapping[str, Any] = field(default_factory=dict)
    neutrality: Mapping[str, Any] = field(default_factory=dict)
    commit: str | None = None
    rollback: str | None = None
    prompt_hash: str | None = None
    skill_ids: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    report: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.round_id.strip():
            raise ValueError("round_id must be non-empty")
        if self.step_id < 0:
            raise ValueError("step_id must be >= 0")
        if not self.stage.strip():
            raise ValueError("stage must be non-empty")
        if self.status not in (
            "baseline",
            "calibrated",
            "keep",
            "discard",
            "crash",
            "env_error",
            "patch_error",
        ):
            raise ValueError(
                "status must be baseline, calibrated, keep, discard, crash, "
                "env_error, or patch_error"
            )

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection for ``records.jsonl``."""
        return {
            "record_id": self.record_id,
            "round_id": self.round_id,
            "step_id": self.step_id,
            "stage": self.stage,
            "surface": self.surface,
            "hypothesis_id": self.hypothesis_id,
            "overrides": dict(self.overrides),
            "baseline_metric": self.baseline_metric,
            "metric": self.metric,
            "status": self.status,
            "detail": self.detail,
            "gates": [dict(gate) for gate in self.gates],
            "artifacts": dict(self.artifacts),
            "environment_snapshot": dict(self.environment_snapshot),
            "environment_action": dict(self.environment_action),
            "observation_patch": dict(self.observation_patch),
            "neutrality": dict(self.neutrality),
            "commit": self.commit,
            "rollback": self.rollback,
            "timestamp": self.timestamp,
            "prompt_hash": self.prompt_hash,
            "skill_ids": list(self.skill_ids),
            "evidence": dict(self.evidence),
            "report": dict(self.report),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExperimentRecord":
        """Rebuild a record from JSON."""
        return cls(
            record_id=str(raw.get("record_id", "")),
            round_id=str(raw["round_id"]),
            step_id=int(raw["step_id"]),
            stage=str(raw["stage"]),
            surface=raw.get("surface"),
            hypothesis_id=raw.get("hypothesis_id"),
            overrides=dict(raw.get("overrides", {})),
            baseline_metric=raw.get("baseline_metric"),
            metric=raw.get("metric"),
            status=str(raw.get("status", "")),
            detail=str(raw.get("detail", "")),
            gates=tuple(dict(gate) for gate in raw.get("gates", ())),
            artifacts=dict(raw.get("artifacts", {})),
            environment_snapshot=dict(raw.get("environment_snapshot", {})),
            environment_action=dict(raw.get("environment_action", {})),
            observation_patch=dict(raw.get("observation_patch", {})),
            neutrality=dict(raw.get("neutrality", {})),
            commit=raw.get("commit"),
            rollback=raw.get("rollback"),
            timestamp=str(raw.get("timestamp", "")),
            prompt_hash=raw.get("prompt_hash"),
            skill_ids=tuple(str(skill) for skill in raw.get("skill_ids", ())),
            evidence=dict(raw.get("evidence", {})),
            report=dict(raw.get("report", {})),
        )

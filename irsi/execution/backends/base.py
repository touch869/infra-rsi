"""Backend protocol and the result of one executed trial."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from ...contract import InfraTaskSpec
from ..metric_extractor import TrialMetrics

__all__ = ["Backend", "TrialResult"]


@dataclass(frozen=True)
class TrialResult:
    """Everything the engine and the gates need to know about one trial."""

    label: str
    backend: str
    metrics: TrialMetrics
    log_path: Path
    config_path: Path
    command: str
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return (
            self.metrics.exit_code == 0
            and not self.metrics.timed_out
            and not self.metrics.traceback
        )

    def summary(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "backend": self.backend,
            "exit_code": self.metrics.exit_code,
            "timed_out": self.metrics.timed_out,
            "traceback": self.metrics.traceback,
            "completed_steps": self.metrics.completed_steps,
            "last_step": self.metrics.last_step,
            "peak_mem_gib": self.metrics.peak_mem_gib,
            "numeric_hash": self.metrics.numeric_hash,
            "elapsed_s": round(self.elapsed_s, 3),
            "config_path": str(self.config_path),
            "log_path": str(self.log_path),
        }


class Backend(Protocol):
    """Executes one trial of a task under a set of overrides."""

    name: str

    def run(
        self,
        spec: InfraTaskSpec,
        trial_dir: Path,
        overrides: Mapping[str, Any],
        label: str,
    ) -> TrialResult:
        """Run one trial and return its parsed metrics."""
        ...

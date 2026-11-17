"""Unified deterministic trial execution primitive."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..contract import InfraTaskSpec, check_overrides_allowed
from .backends.base import Backend, TrialResult

__all__ = ["TrialExecutor"]


class TrialExecutor:
    """Run one trial; no expert, no prompt, no judgment."""

    def __init__(self, spec: InfraTaskSpec, backend: Backend) -> None:
        self.spec = spec
        self.backend = backend

    def execute(
        self,
        overrides: Mapping[str, Any],
        label: str,
        trial_dir: str | Path,
    ) -> TrialResult:
        check_overrides_allowed(self.spec, overrides)
        return self.backend.run(
            self.spec,
            Path(trial_dir),
            dict(overrides),
            label,
        )

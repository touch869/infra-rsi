"""Gate protocol and its evaluation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from ..execution.backends.base import TrialResult
from ..contract import InfraTaskSpec

__all__ = ["Gate", "GateContext", "GateResult"]


@dataclass(frozen=True)
class GateContext:
    """Everything a gate may look at; gates never mutate the trial."""

    spec: InfraTaskSpec
    trial: TrialResult
    baseline: Optional[TrialResult] = None
    best: Optional[TrialResult] = None


@dataclass(frozen=True)
class GateResult:
    """One gate's verdict."""

    name: str
    passed: bool
    detail: str = ""


class Gate(Protocol):
    """A named pass/fail check."""

    name: str

    def check(self, ctx: GateContext) -> GateResult:
        """Return this gate's verdict for ``ctx``."""
        ...

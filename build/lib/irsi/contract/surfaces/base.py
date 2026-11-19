"""Hypothesis type shared by every edit-surface domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["Hypothesis"]


@dataclass(frozen=True)
class Hypothesis:
    """One candidate change, expressed only as contract-approved overrides."""

    id: str
    description: str
    overrides: Mapping[str, Any] = field(default_factory=dict)
    expect_numeric_equal: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("hypothesis id must be non-empty")

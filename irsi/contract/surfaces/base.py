"""Hypothesis type shared by every edit-surface domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

__all__ = ["Hypothesis", "SurfacePlugin"]


@dataclass(frozen=True)
class Hypothesis:
    """One candidate change, expressed as overrides and/or a source patch."""

    id: str
    description: str
    overrides: Mapping[str, Any] = field(default_factory=dict)
    expect_numeric_equal: bool = True
    patch: str = ""
    patch_target_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("hypothesis id must be non-empty")
        if self.patch and not self.patch_target_files:
            raise ValueError("a source patch must declare patch_target_files")


class SurfacePlugin(Protocol):
    """Framework-specific modification surface contract."""

    framework: str
    surface: str

    def validate(self, spec: Any) -> None:
        ...

    def candidates(self, spec: Any) -> list[Any]:
        ...

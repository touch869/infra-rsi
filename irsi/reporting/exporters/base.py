"""Exporter protocol: format or destination is a plugin, not a report."""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["Exporter"]


class Exporter(Protocol):
    """Serialize one report bundle to a durable output."""

    def export(self, bundle: Any, path: str) -> None:
        ...

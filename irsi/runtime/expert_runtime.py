"""Expert runtime protocol: prompt execution belongs to the runtime, not the expert."""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["ExpertRuntime"]


class ExpertRuntime(Protocol):
    """Run one expert with a stage prompt and deterministic runtime facade."""

    def run(self, expert: str, context: Any, facade: Any) -> Any:
        ...

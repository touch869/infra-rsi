"""Apply or revert an ObservationPatch against a repo checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..experts.artifacts import ObservationPatch

__all__ = ["ObservationPatchManager"]


class ObservationPatchManager:
    """Toggle an observation patch without changing training semantics."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)

    def apply(self, patch: ObservationPatch) -> None:
        if patch.is_empty:
            return
        self._git(("apply",), patch.diff)

    def revert(self, patch: ObservationPatch) -> None:
        if patch.is_empty:
            return
        self._git(("apply", "-R"), patch.diff)

    def _git(self, args: tuple[str, ...], diff: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            input=diff,
            text=True,
            check=True,
        )

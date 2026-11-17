"""Apply or revert a candidate source patch against the task repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..experts.artifacts import CandidateSpec

__all__ = ["CandidatePatchManager"]


class CandidatePatchManager:
    """Toggle a candidate's source-code patch without changing the contract."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)

    def apply(self, candidate: CandidateSpec) -> None:
        if not candidate.patch:
            return
        self._git(("apply",), candidate.patch)

    def revert(self, candidate: CandidateSpec) -> None:
        if not candidate.patch:
            return
        self._git(("apply", "-R"), candidate.patch)

    def _git(self, args: tuple[str, ...], diff: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            input=diff,
            text=True,
            check=True,
        )

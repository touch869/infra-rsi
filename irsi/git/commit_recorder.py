"""Git commit/revert recorder for candidate reports."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["CommitRecorder"]


class CommitRecorder:
    """Commit candidate changes together with their report, and revert on discard."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)

    def commit(
        self,
        message: str,
        *,
        files: tuple[str, ...] = (),
        report_path: str | Path | None = None,
    ) -> str:
        paths = list(files)
        if report_path is not None:
            paths.append(str(report_path))
        if paths:
            self._git("add", *paths)
        self._git("commit", "-m", message)
        return self._git("rev-parse", "--short", "HEAD").strip()

    def revert(self, commit: str) -> str:
        self._git("revert", "--no-edit", commit)
        return self._git("rev-parse", "--short", "HEAD").strip()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout

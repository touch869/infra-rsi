"""Capture the baseline environment snapshot for audit."""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping

from ..contract import InfraTaskSpec

__all__ = ["EnvironmentSnapshot"]


@dataclass(frozen=True)
class EnvironmentSnapshot:
    """Deterministic environment facts used to explain the baseline world."""

    python: str
    platform: str
    repo_root: str
    repo_commit: str | None
    packages: Mapping[str, str] = field(default_factory=dict)
    env_setup: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "python": self.python,
            "platform": self.platform,
            "repo_root": self.repo_root,
            "repo_commit": self.repo_commit,
            "packages": dict(self.packages),
            "env_setup": self.env_setup,
        }

    @classmethod
    def capture(cls, spec: InfraTaskSpec) -> "EnvironmentSnapshot":
        commit = None
        try:
            completed = subprocess.run(
                ["git", "-C", spec.repo_root, "rev-parse", "HEAD"],
                check=True,
                text=True,
                capture_output=True,
            )
            commit = completed.stdout.strip()
        except subprocess.SubprocessError:
            commit = None

        packages: dict[str, str] = {}
        for name in ("torch", "torch_npu", "mindspore", "hyperparallel"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                continue

        return cls(
            python=sys.version.split()[0],
            platform=platform.platform(),
            repo_root=spec.repo_root,
            repo_commit=commit,
            packages=packages,
            env_setup=spec.env_setup,
        )

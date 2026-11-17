"""Bounded environment repair agent."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..contract import InfraTaskSpec

__all__ = ["EnvironmentAction", "EnvironmentDiagnosis", "EnvironmentRepairAgent"]


@dataclass(frozen=True)
class EnvironmentDiagnosis:
    """Classification of an execution failure."""

    kind: str
    reason: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "reason": self.reason, "action": self.action}


@dataclass(frozen=True)
class EnvironmentAction:
    """One recorded repair action."""

    action: str
    command: str
    success: bool
    detail: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "command": self.command,
            "success": self.success,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class EnvironmentRepairAgent:
    """Repair environment failures only through allowlisted env_setup commands."""

    def __init__(
        self,
        spec: InfraTaskSpec,
        *,
        max_attempts: int = 2,
        timeout_min: float = 10.0,
    ) -> None:
        self.spec = spec
        self.max_attempts = max_attempts
        self.timeout_min = timeout_min
        self.attempts = 0

    def diagnose(self, error: Exception) -> EnvironmentDiagnosis:
        text = str(error).lower()
        if isinstance(error, (OSError, EnvironmentError)):
            return EnvironmentDiagnosis("env_error", str(error), "rerun_env_setup")
        if "no module named" in text or "not found" in text:
            return EnvironmentDiagnosis("env_error", str(error), "rerun_env_setup")
        if "out of memory" in text or "oom" in text:
            return EnvironmentDiagnosis("resource_error", str(error), "none")
        return EnvironmentDiagnosis("backend_error", str(error), "none")

    def repair(self, error: Exception) -> EnvironmentAction:
        diagnosis = self.diagnose(error)
        now = datetime.now(timezone.utc).isoformat()

        if diagnosis.action == "none":
            return EnvironmentAction("none", "", False, diagnosis.reason, now)

        if self.attempts >= self.max_attempts:
            return EnvironmentAction(
                "exhausted", "", False, "max repair attempts reached", now
            )

        command = self.spec.env_setup.strip()
        if not command:
            return EnvironmentAction(
                "no_env_setup", "", False, "no env_setup command", now
            )

        self.attempts += 1
        try:
            subprocess.run(
                ["bash", "-lc", command],
                check=True,
                timeout=self.timeout_min * 60.0,
            )
            return EnvironmentAction(
                "env_setup", command, True, "env_setup succeeded", now
            )
        except subprocess.CalledProcessError as exc:
            return EnvironmentAction("env_setup", command, False, str(exc), now)
        except subprocess.TimeoutExpired as exc:
            return EnvironmentAction(
                "env_setup", command, False, f"timeout: {exc}", now
            )

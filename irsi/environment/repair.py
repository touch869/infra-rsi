"""Bounded environment repair agent with an explicit command allowlist."""

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
    """Repair environment failures only through contract-allowlisted commands.

    The allowlist is ``domain_params.environment_repair.commands`` plus the
    task's ``env_setup`` and an optional requirements file. The agent never
    invents a command; it diagnoses the failure and runs one allowed action.
    """

    def __init__(
        self,
        spec: InfraTaskSpec,
        *,
        max_attempts: int = 2,
        timeout_min: float = 10.0,
        commands: tuple[str, ...] | None = None,
        requirements: str | None = None,
    ) -> None:
        self.spec = spec
        self.max_attempts = max_attempts
        self.timeout_min = timeout_min
        self.attempts = 0

        repair_config = spec.domain_params.get("environment_repair", {})
        if not isinstance(repair_config, dict):
            repair_config = {}
        self.commands = tuple(
            str(command) for command in repair_config.get("commands", ())
        ) if commands is None else tuple(str(command) for command in commands)
        self.requirements = (
            str(requirements)
            if requirements is not None
            else (
                str(repair_config["requirements"])
                if repair_config.get("requirements")
                else None
            )
        )

    def diagnose(self, error: Exception) -> EnvironmentDiagnosis:
        text = str(error).lower()
        if isinstance(error, (OSError, EnvironmentError)):
            return EnvironmentDiagnosis("env_error", str(error), "rerun_env_setup")
        if "no module named" in text:
            return EnvironmentDiagnosis("package_error", str(error), "install_package")
        if "permission denied" in text or "read-only file system" in text:
            return EnvironmentDiagnosis(
                "permission_error", str(error), "allowlisted_command"
            )
        if "npu" in text or "device" in text or "hccl" in text:
            return EnvironmentDiagnosis(
                "device_error", str(error), "allowlisted_command"
            )
        if "out of memory" in text or "oom" in text:
            return EnvironmentDiagnosis("resource_error", str(error), "none")
        if "timed out" in text or "timeout" in text:
            return EnvironmentDiagnosis("backend_error", str(error), "none")
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

        command, action_name = self._select_command(diagnosis)
        if not command:
            action = "no_env_setup" if diagnosis.kind == "env_error" else "no_repair_command"
            return EnvironmentAction(
                action, "", False, "no allowlisted repair command", now
            )

        self.attempts += 1
        try:
            subprocess.run(
                ["bash", "-lc", command],
                check=True,
                timeout=self.timeout_min * 60.0,
            )
            return EnvironmentAction(action_name, command, True, "repair succeeded", now)
        except subprocess.CalledProcessError as exc:
            return EnvironmentAction(action_name, command, False, str(exc), now)
        except subprocess.TimeoutExpired as exc:
            return EnvironmentAction(
                action_name, command, False, f"timeout: {exc}", now
            )

    def _select_command(self, diagnosis: EnvironmentDiagnosis) -> tuple[str, str]:
        env_setup = self.spec.env_setup.strip()

        if diagnosis.kind == "env_error":
            return env_setup, "env_setup"

        if diagnosis.kind == "package_error":
            if self.requirements:
                command = (
                    f"{self.spec.python} -m pip install -r {self.requirements}"
                )
                return command, "install_requirements"
            for candidate in self.commands:
                if candidate.strip().startswith("pip install"):
                    return candidate.strip(), "install_package"
            if self.commands:
                return self.commands[0].strip(), "allowlisted_command"
            return env_setup, "env_setup"

        if diagnosis.kind in ("permission_error", "device_error"):
            if self.commands:
                return self.commands[0].strip(), "allowlisted_command"
            return env_setup, "env_setup"

        return "", "none"

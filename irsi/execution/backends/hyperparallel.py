"""HyperParallel backend: render a trial YAML and run it with torchrun."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

import yaml

from ...contract import InfraTaskSpec, apply_overrides, check_overrides_allowed
from ..metric_extractor import parse_log
from ...registry import BACKENDS
from .base import TrialResult

__all__ = ["HyperParallelBackend"]


@BACKENDS.register("hyperparallel")
class HyperParallelBackend:
    """Executes trials by launching ``scripts/train_lm.py`` on Ascend NPUs."""

    name = "hyperparallel"

    def __init__(self, timeout_min: float | None = None) -> None:
        self._timeout_min = timeout_min

    def render_config(self, spec: InfraTaskSpec, overrides: Mapping[str, Any], path: Path) -> Path:
        """Write the fully merged trial configuration next to its log."""
        check_overrides_allowed(spec, overrides)
        base = yaml.safe_load(Path(spec.base_config).read_text(encoding="utf-8"))
        if not isinstance(base, dict):
            raise ValueError(f"base config is not a mapping: {spec.base_config}")
        merged = apply_overrides(base, {**dict(spec.base_overrides), **dict(overrides)})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return path

    def _command(self, spec: InfraTaskSpec, config_path: Path) -> str:
        pythonpath = os.pathsep.join([spec.repo_root, *spec.extra_pythonpath])
        parts: list[str] = []
        if spec.env_setup:
            parts.append(spec.env_setup)
        parts.append(f"cd {shlex.quote(spec.repo_root)}")
        parts.append(f"export PYTHONPATH={shlex.quote(pythonpath)}:$PYTHONPATH")
        parts.append(
            f"{shlex.quote(spec.python)} -m torch.distributed.run "
            f"--nproc_per_node={spec.workload.nproc} "
            f"scripts/train_lm.py {shlex.quote(str(config_path))}"
        )
        return " && ".join(parts)

    def run(
        self,
        spec: InfraTaskSpec,
        trial_dir: Path,
        overrides: Mapping[str, Any],
        label: str,
    ) -> TrialResult:
        """Run one trial, persist its log and metrics, and return the parsed result."""
        trial_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.render_config(spec, overrides, trial_dir / "train.yaml")
        log_path = trial_dir / "run.log"
        command = self._command(spec, config_path)
        timeout_s = (self._timeout_min or spec.budget.timeout_min) * 60.0

        started = time.monotonic()
        timed_out = False
        with log_path.open("w", encoding="utf-8") as handle:
            process = subprocess.Popen(
                ["bash", "-lc", command],
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                exit_code = process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate(process)
                exit_code = process.returncode if process.returncode is not None else -9
        elapsed = time.monotonic() - started

        text = log_path.read_text(encoding="utf-8", errors="replace")
        metrics = parse_log(text, exit_code=exit_code, timed_out=timed_out)
        result = TrialResult(
            label=label,
            backend=self.name,
            metrics=metrics,
            log_path=log_path,
            config_path=config_path,
            command=command,
            elapsed_s=elapsed,
        )
        (trial_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "summary": result.summary(),
                    "steps": [step.__dict__ for step in metrics.steps],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return result

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        """Terminate the whole process group so torchrun workers die with the shell."""
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

"""Run one contract trial for an external experiment controller.

The optimization controller is responsible for choosing ideas, editing source,
deciding when to iterate, and keeping the experiment ledger.  This module only
provides the deterministic measurement primitive it needs:

* render the contract's configuration and run the current committed source;
* apply the contract's receipt and memory gates;
* freeze a comparable baseline, or compare a later trial with that baseline.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .contract import (
    InfraTaskSpec,
    contract_hash,
    verify_contract_lock,
)
from .engine import Engine
from .execution.backends.base import Backend
from .knowledge.runtime.ledger_store import TaskLedger

__all__ = [
    "Measurement",
    "MeasurementError",
    "measure_current",
]

SCHEMA = "infra-rsi-measurement/v1"
_IDENTITY_FIELDS = (
    "name",
    "repo_root",
    "base_config",
    "domain",
    "base_overrides",
    "read_only_keys",
    "metric",
    "workload",
    "gates",
)


class MeasurementError(RuntimeError):
    """A trial completed but did not satisfy the frozen baseline identity."""


@dataclass(frozen=True)
class Measurement:
    """Stable result emitted to the experiment controller."""

    run_dir: Path
    metric: float
    numeric_hash: str
    peak_mem_gib: float | None
    payload: Mapping[str, Any]


def measure_current(
    spec: InfraTaskSpec,
    backend: Backend,
    *,
    artifacts_dir: str | Path,
    reference: str | Path | None = None,
    freeze_baseline: str | Path | None = None,
    contract_path: str | Path | None = None,
    require_confirmed: bool = False,
    label: str = "measure",
) -> Measurement:
    """Measure the current committed source once and optionally freeze it.

    ``reference`` validates numerical equivalence with an earlier frozen
    measurement.  It is intentionally checked outside the in-process bitwise
    gate, because a candidate run has no baseline from the same process.
    """
    reference_payload = _load_reference(reference, spec) if reference else None
    digest = contract_hash(spec)
    lock = (
        verify_contract_lock(contract_path, spec, require=require_confirmed)
        if contract_path is not None
        else None
    )
    run_dir = _new_run_dir(Path(artifacts_dir), label)
    ledger = TaskLedger(
        run_dir,
        {
            "contract_path": str(Path(contract_path).resolve()) if contract_path else "",
            "measurement_label": label,
            **spec.to_dict(),
        },
    )
    engine = Engine(spec, backend, ledger)
    trial = engine.run_baseline()
    metric = engine.metric_of(trial)
    if metric is None:
        raise MeasurementError(
            f"trial produced no value for contract metric {spec.metric.key!r}"
        )

    identity = _identity(spec)
    reference_result = None
    reference_error = ""
    if reference_payload is not None:
        if reference_payload.get("contract_hash") != digest:
            raise MeasurementError(
                "reference measurement was produced by a different contract; "
                "freeze a new baseline"
            )
        if reference_payload.get("identity") != identity:
            raise MeasurementError(
                "reference measurement identity differs from the contract; "
                "start a fresh baseline"
            )
        passed = reference_payload.get("numeric_hash") == trial.metrics.numeric_hash
        reference_result = {
            "path": str(reference),
            "passed": passed,
            "metric": reference_payload.get("metric"),
            "numeric_hash": reference_payload.get("numeric_hash"),
        }
        if not passed:
            reference_error = (
                "numeric mismatch against frozen baseline: "
                f"{reference_payload.get('numeric_hash')} -> {trial.metrics.numeric_hash}"
            )

    payload = {
        "schema": SCHEMA,
        "task": spec.name,
        "identity": identity,
        "contract_hash": digest,
        "contract_lock": dict(lock) if lock else None,
        "run_dir": str(run_dir),
        "source_commit": _git_head(spec.repo_root),
        "metric_key": spec.metric.key,
        "metric": metric,
        "numeric_hash": trial.metrics.numeric_hash,
        "peak_mem_gib": trial.metrics.peak_mem_gib,
        "completed_steps": trial.metrics.completed_steps,
        "gates": [gate.__dict__ for gate in engine.baseline_gates],
        "reference": reference_result,
        "log": str(trial.log_path),
        "config": str(trial.config_path),
    }
    ledger.write_json("measurement.json", payload)
    accepted = not reference_error
    ledger.set_state(
        "MEASURED" if accepted else "REJECTED",
        metric=metric,
        numeric_hash=trial.metrics.numeric_hash,
        detail=reference_error or None,
    )
    if reference_error:
        raise MeasurementError(reference_error)
    if freeze_baseline is not None:
        _write_json(Path(freeze_baseline), payload)
    return Measurement(
        run_dir=run_dir,
        metric=metric,
        numeric_hash=trial.metrics.numeric_hash,
        peak_mem_gib=trial.metrics.peak_mem_gib,
        payload=payload,
    )


def _identity(spec: InfraTaskSpec) -> dict[str, Any]:
    projected = spec.to_dict()
    return {key: projected[key] for key in _IDENTITY_FIELDS}


def _load_reference(path: str | Path, spec: InfraTaskSpec) -> dict[str, Any]:
    payload = _load_json(Path(path))
    if payload.get("schema") != SCHEMA:
        raise MeasurementError(f"unsupported reference schema in {path}")
    if payload.get("task") != spec.name:
        raise MeasurementError(
            f"reference belongs to {payload.get('task')!r}, not {spec.name!r}"
        )
    if not payload.get("numeric_hash"):
        raise MeasurementError(f"reference has no numeric_hash: {path}")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_dir():
        for name in ("measurement.json", "baseline.json"):
            candidate = path / name
            if candidate.is_file():
                path = candidate
                break
        else:
            raise MeasurementError(f"no measurement artifact in {path}")
    if not path.is_file():
        raise MeasurementError(f"measurement artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MeasurementError(f"measurement artifact is not an object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _new_run_dir(root: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", label.strip()).strip("-") or "measure"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{stamp}-{slug}"


def _git_head(repo_root: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""

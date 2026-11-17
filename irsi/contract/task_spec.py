"""Task contract: the frozen definition of what a run may change and how it is judged."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

__all__ = [
    "BudgetSpec",
    "GateSpec",
    "InfraTaskSpec",
    "MetricSpec",
    "WorkloadSpec",
    "apply_overrides",
    "check_overrides_allowed",
    "load_contract",
]

_DOTTED_KEY = "dotted override keys must be non-empty strings"


@dataclass(frozen=True)
class MetricSpec:
    """How the primary metric is read and compared."""

    key: str = "performance/tokens_per_second"
    direction: str = "maximize"
    noise_fraction: float = 0.02
    warmup_steps: int = 5
    measured_steps: int = 10

    def __post_init__(self) -> None:
        if self.direction not in ("maximize", "minimize"):
            raise ValueError("metric.direction must be 'maximize' or 'minimize'")
        if not 0.0 <= self.noise_fraction < 1.0:
            raise ValueError("metric.noise_fraction must be in [0, 1)")
        if self.warmup_steps < 0:
            raise ValueError("metric.warmup_steps must be >= 0")
        if self.measured_steps < 1:
            raise ValueError("metric.measured_steps must be >= 1")

    def improved(self, candidate: float, reference: float) -> bool:
        """Whether ``candidate`` beats ``reference`` beyond the noise band."""
        if reference == 0:
            return candidate > 0
        if self.direction == "maximize":
            return candidate > reference * (1.0 + self.noise_fraction)
        return candidate < reference * (1.0 - self.noise_fraction)


@dataclass(frozen=True)
class WorkloadSpec:
    """The frozen comparison identity."""

    nproc: int = 8
    seed: int = 42
    determinism: bool = True
    expect_steps: int = 20
    input_hash: str = ""

    def __post_init__(self) -> None:
        if self.nproc < 1:
            raise ValueError("workload.nproc must be >= 1")
        if self.expect_steps < 1:
            raise ValueError("workload.expect_steps must be >= 1")


@dataclass(frozen=True)
class GateSpec:
    """One gate plugin and its parameters."""

    name: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BudgetSpec:
    """Resource limits for one task."""

    max_trials: int = 6
    timeout_min: float = 25.0
    max_repairs: int = 1

    def __post_init__(self) -> None:
        if self.max_trials < 1:
            raise ValueError("budget.max_trials must be >= 1")
        if self.timeout_min <= 0:
            raise ValueError("budget.timeout_min must be > 0")
        if self.max_repairs < 0:
            raise ValueError("budget.max_repairs must be >= 0")


@dataclass(frozen=True)
class InfraTaskSpec:
    """Everything one task needs; immutable once loaded."""

    name: str
    repo_root: str
    base_config: str
    domain: str
    domain_params: Mapping[str, Any] = field(default_factory=dict)
    base_overrides: Mapping[str, Any] = field(default_factory=dict)
    writable_prefixes: tuple[str, ...] = ()
    read_only_keys: tuple[str, ...] = ()
    python: str = "python"
    env_setup: str = ""
    extra_pythonpath: tuple[str, ...] = ()
    metric: MetricSpec = field(default_factory=MetricSpec)
    workload: WorkloadSpec = field(default_factory=WorkloadSpec)
    gates: tuple[GateSpec, ...] = (GateSpec("receipt"),)
    budget: BudgetSpec = field(default_factory=BudgetSpec)
    memory_budget_gib: float = 24.0

    def __post_init__(self) -> None:
        for key in ("name", "repo_root", "base_config", "domain"):
            if not str(getattr(self, key)).strip():
                raise ValueError(f"{key} must be a non-empty string")
        if not self.gates:
            raise ValueError("at least one gate is required")
        if not self.writable_prefixes:
            raise ValueError("writable_prefixes must declare the editable key surface")
        if self.memory_budget_gib <= 0:
            raise ValueError("memory_budget_gib must be > 0")

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection used in ``task.json``."""
        return {
            "name": self.name,
            "repo_root": self.repo_root,
            "base_config": self.base_config,
            "domain": self.domain,
            "domain_params": dict(self.domain_params),
            "base_overrides": dict(self.base_overrides),
            "writable_prefixes": list(self.writable_prefixes),
            "read_only_keys": list(self.read_only_keys),
            "python": self.python,
            "env_setup": self.env_setup,
            "extra_pythonpath": list(self.extra_pythonpath),
            "metric": self.metric.__dict__,
            "workload": self.workload.__dict__,
            "gates": [{"name": g.name, "params": dict(g.params)} for g in self.gates],
            "budget": self.budget.__dict__,
            "memory_budget_gib": self.memory_budget_gib,
        }


def apply_overrides(config: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``config`` with dotted ``overrides`` applied.

    A dotted key such as ``activation_checkpoint.mode`` creates missing nested
    mappings and refuses to overwrite a scalar with a mapping.
    """
    import copy

    result = copy.deepcopy(dict(config))
    for dotted, value in overrides.items():
        if not isinstance(dotted, str) or not dotted:
            raise ValueError(_DOTTED_KEY)
        parts = dotted.split(".")
        cursor: dict[str, Any] = result
        for part in parts[:-1]:
            if not part:
                raise ValueError(f"invalid dotted key: {dotted!r}")
            child = cursor.get(part)
            if child is None:
                child = {}
                cursor[part] = child
            if not isinstance(child, dict):
                raise ValueError(f"override {dotted!r} crosses non-mapping key {part!r}")
            cursor = child
        cursor[parts[-1]] = copy.deepcopy(value)
    return result


def _matches(key: str, prefix: str) -> bool:
    base = prefix.rstrip(".")
    return key == base or key.startswith(base + ".")


def check_overrides_allowed(spec: InfraTaskSpec, overrides: Mapping[str, Any]) -> None:
    """Enforce the key-level edit surface before a trial is launched.

    A read-only key always wins over a writable prefix; anything outside the
    declared prefixes is rejected rather than silently applied.
    """
    for key in overrides:
        if any(_matches(key, ro) for ro in spec.read_only_keys):
            raise ValueError(f"override {key!r} is read-only")
        if not any(_matches(key, prefix) for prefix in spec.writable_prefixes):
            raise ValueError(
                f"override {key!r} is outside the writable surface "
                f"{list(spec.writable_prefixes)}"
            )


def _require_mapping(raw: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return raw


def load_contract(path: str | Path) -> InfraTaskSpec:
    """Load and validate a contract YAML file."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("contract must be a YAML mapping")
    metric_raw = _require_mapping(raw.get("metric", {}), "metric")
    workload_raw = _require_mapping(raw.get("workload", {}), "workload")
    budget_raw = _require_mapping(raw.get("budget", {}), "budget")
    gates_raw = raw.get("gates", [{"name": "receipt"}])
    if not isinstance(gates_raw, Sequence) or isinstance(gates_raw, (str, bytes)):
        raise ValueError("gates must be a sequence")
    gates = tuple(
        GateSpec(name=str(item["name"]), params=dict(item.get("params", {})))
        if isinstance(item, Mapping)
        else GateSpec(name=str(item))
        for item in gates_raw
    )
    overrides = _require_mapping(raw.get("base_overrides", {}), "base_overrides")
    domain_params = _require_mapping(raw.get("domain_params", {}), "domain_params")
    return InfraTaskSpec(
        name=str(raw["name"]),
        repo_root=str(raw["repo_root"]),
        base_config=str(raw["base_config"]),
        domain=str(raw["domain"]),
        domain_params=dict(domain_params),
        base_overrides=dict(overrides),
        writable_prefixes=tuple(str(k) for k in raw.get("writable_prefixes", ())),
        read_only_keys=tuple(str(k) for k in raw.get("read_only_keys", ())),
        python=str(raw.get("python", "python")),
        env_setup=str(raw.get("env_setup", "")),
        extra_pythonpath=tuple(str(p) for p in raw.get("extra_pythonpath", ())),
        metric=MetricSpec(**dict(metric_raw)),
        workload=WorkloadSpec(**dict(workload_raw)),
        gates=gates,
        budget=BudgetSpec(**dict(budget_raw)),
        memory_budget_gib=float(raw.get("memory_budget_gib", 24.0)),
    )

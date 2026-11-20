"""Generate, summarize and confirm a frozen evaluation contract."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .task_spec import BudgetSpec, GateSpec, InfraTaskSpec, MetricSpec, WorkloadSpec, load_contract

__all__ = [
    "ContractDraft",
    "ContractLockError",
    "confirm_contract",
    "contract_hash",
    "contract_draft_path",
    "contract_lock_path",
    "contract_summary",
    "create_contract_draft",
    "load_contract_draft",
    "load_contract_lock",
    "verify_contract_lock",
]

DRAFT_SCHEMA = "infra-rsi-contract-draft/v1"
LOCK_SCHEMA = "infra-rsi-contract-lock/v1"

_DEFAULT_READ_ONLY = (
    "activation_checkpoint.allow_cache_entry_mutation",
    "training.seed",
    "training.enable_full_determinism",
    "training.global_batch_size",
    "training.micro_batch_size",
    "mixed_precision",
    "compile",
    "accelerator",
    "fsdp_config",
)
_MANDATORY_READ_ONLY = ("activation_checkpoint.allow_cache_entry_mutation",)


class ContractLockError(RuntimeError):
    """The confirmed contract is missing, stale or does not match its lock."""


@dataclass(frozen=True)
class ContractDraft:
    """A generated contract plus the material shown to the user."""

    spec: InfraTaskSpec
    path: Path
    summary: str
    contract_hash: str
    confirmation_code: str
    manifest_path: Path


def create_contract_draft(
    *,
    objective: str,
    out: str | Path,
    base_config: str | Path,
    repo_root: str | Path | None = None,
    name: str | None = None,
    domain: str = "source-edit",
    writable_prefixes: Sequence[str] = (),
    read_only_keys: Sequence[str] = (),
    python: str | None = None,
    env_setup: str | None = None,
    extra_pythonpath: Sequence[str] = (),
    nproc: int | None = None,
    seed: int | None = None,
    steps: int | None = None,
    warmup_steps: int | None = None,
    measured_steps: int | None = None,
    memory_budget_gib: float = 24.0,
    max_trials: int = 6,
    timeout_min: float = 25.0,
) -> ContractDraft:
    """Infer a contract from the workload config and write a reviewable draft."""
    if not objective.strip():
        raise ValueError("objective must be non-empty")
    config_path = Path(base_config).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"base config not found: {config_path}")
    config = _load_mapping(config_path)
    root = _git_root(repo_root) if repo_root is not None else _git_root(config_path.parent)
    config_steps = _deep_get(config, "training.train_iters")
    resolved_steps = int(steps if steps is not None else config_steps or 20)
    resolved_warmup = int(
        warmup_steps
        if warmup_steps is not None
        else min(8, max(0, resolved_steps - 1))
    )
    resolved_measured = int(
        measured_steps
        if measured_steps is not None
        else min(16, max(1, resolved_steps - resolved_warmup))
    )
    if resolved_warmup + resolved_measured > resolved_steps:
        raise ValueError("warmup_steps + measured_steps exceeds the expected training window")
    config_nproc = _deep_get(config, "fsdp_config.dp_shard_size")
    resolved_nproc = int(nproc if nproc is not None else config_nproc or 8)
    config_seed = _deep_get(config, "training.seed")
    resolved_seed = int(seed if seed is not None else config_seed if config_seed is not None else 42)
    resolved_name = name or config_path.stem.replace("_", "-")
    resolved_prefixes = tuple(writable_prefixes) or _infer_writable_prefixes(objective)
    inferred_read_only = tuple(read_only_keys) or _visible_read_only(
        resolved_prefixes, _DEFAULT_READ_ONLY
    )
    resolved_read_only = tuple(
        dict.fromkeys((*inferred_read_only, *_MANDATORY_READ_ONLY))
    )
    resolved_env = env_setup
    if resolved_env is None:
        resolved_env = (
            "source /usr/local/Ascend/ascend-toolkit/latest/set_env.sh"
            if _deep_get(config, "training.backend") == "hccl"
            else ""
        )
    resolved_pythonpath = tuple(extra_pythonpath) or (str(config_path.parent.parent),)
    resolved_python = python or sys.executable or "python"

    spec = InfraTaskSpec(
        name=resolved_name,
        repo_root=str(root),
        base_config=str(config_path),
        domain=domain,
        base_overrides={"training.train_iters": resolved_steps},
        writable_prefixes=resolved_prefixes,
        read_only_keys=resolved_read_only,
        python=resolved_python,
        env_setup=resolved_env,
        extra_pythonpath=resolved_pythonpath,
        metric=MetricSpec(
            key="performance/tokens_per_second",
            direction="maximize",
            noise_fraction=0.03,
            warmup_steps=resolved_warmup,
            measured_steps=resolved_measured,
        ),
        workload=WorkloadSpec(
            nproc=resolved_nproc,
            seed=resolved_seed,
            determinism=_config_bool(config, "training.enable_full_determinism", default=True),
            expect_steps=resolved_steps,
        ),
        gates=(
            GateSpec("receipt"),
            GateSpec("bitwise"),
            GateSpec("memory", {"limit_gib": float(memory_budget_gib)}),
        ),
        budget=BudgetSpec(max_trials=int(max_trials), timeout_min=float(timeout_min)),
        memory_budget_gib=float(memory_budget_gib),
    )
    path = Path(out).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"contract draft already exists: {path}")
    _write_yaml(path, spec.to_dict())
    digest = contract_hash(spec)
    code = digest[:12]
    summary = contract_summary(spec, objective=objective, confirmation_code=code)
    manifest_path = contract_draft_path(path)
    _write_json(
        manifest_path,
        {
            "schema": DRAFT_SCHEMA,
            "objective": objective,
            "contract_path": str(path),
            "contract_hash": digest,
            "confirmation_code": code,
            "summary": summary,
            "created_at": _now(),
        },
    )
    path.with_suffix(path.suffix + ".summary.md").write_text(
        summary + "\n", encoding="utf-8"
    )
    return ContractDraft(
        spec=spec,
        path=path,
        summary=summary,
        contract_hash=digest,
        confirmation_code=code,
        manifest_path=manifest_path,
    )


def contract_summary(
    spec: InfraTaskSpec,
    *,
    objective: str = "",
    confirmation_code: str | None = None,
) -> str:
    """Render the natural-language evaluation summary shown before confirmation."""
    memory_limits = [
        f"{gate.params.get('limit_gib')} GiB"
        for gate in spec.gates
        if gate.name == "memory" and gate.params.get("limit_gib") is not None
    ]
    lines = ["# 评估配置确认", ""]
    if objective:
        lines.extend([f"- **优化目标：** {objective}"])
    lines.extend(
        [
            f"- **工作负载：** `{spec.repo_root}`，配置 `{spec.base_config}`",
            f"- **并行规模：** {spec.workload.nproc} 个进程；seed={spec.workload.seed}；"
            f"确定性和预期步数={spec.workload.expect_steps}",
            f"- **指标：** `{spec.metric.key}`，{spec.metric.direction}；"
            f"噪声带 {spec.metric.noise_fraction:.0%}；"
            f"预热 {spec.metric.warmup_steps} 步，测量 {spec.metric.measured_steps} 步",
            "- **正确性门槛：** "
            + ", ".join(
                f"{gate.name}"
                + (f" ({', '.join(f'{k}={v}' for k, v in gate.params.items())})" if gate.params else "")
                for gate in spec.gates
            ),
            f"- **允许修改的配置面：** {', '.join(spec.writable_prefixes)}",
            f"- **只读键：** {', '.join(spec.read_only_keys) or '无'}",
            f"- **预算：** 最多 {spec.budget.max_trials} 次 trial，单次 {spec.budget.timeout_min:g} 分钟",
            f"- **显存上限：** {', '.join(memory_limits) or f'{spec.memory_budget_gib:g} GiB'}",
        ]
    )
    if confirmation_code:
        lines.extend(
            [
                "",
                f"合同 hash：`{contract_hash(spec)}`",
                f"确认码：`{confirmation_code}`",
            ]
        )
    return "\n".join(lines)


def confirm_contract(
    contract_path: str | Path,
    *,
    confirmation_code: str,
    statement: str,
    confirmed_by: str = "user",
) -> dict[str, Any]:
    """Lock the reviewed contract hash after the user's explicit confirmation."""
    path = Path(contract_path).resolve()
    spec = load_contract(path)
    digest = contract_hash(spec)
    expected = digest[:12]
    if confirmation_code.strip().lower() != expected:
        raise ContractLockError(
            f"confirmation code does not match the contract hash; expected {expected}"
        )
    if not statement.strip():
        raise ContractLockError("a natural-language confirmation statement is required")
    manifest_path = contract_draft_path(path)
    manifest: Mapping[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("contract_hash") != digest:
            raise ContractLockError("contract changed after the draft was generated")
    summary = str(manifest.get("summary") or contract_summary(spec))
    lock = {
        "schema": LOCK_SCHEMA,
        "contract_path": str(path),
        "contract_hash": digest,
        "confirmation_code": expected,
        "objective": str(manifest.get("objective") or ""),
        "summary": summary,
        "statement": statement.strip(),
        "confirmed_by": confirmed_by,
        "confirmed_at": _now(),
    }
    _write_json(contract_lock_path(path), lock)
    return lock


def verify_contract_lock(
    contract_path: str | Path,
    spec: InfraTaskSpec,
    *,
    require: bool = False,
) -> dict[str, Any] | None:
    """Validate the sidecar lock against the contract's semantic hash."""
    path = Path(contract_path).resolve()
    disk_spec = load_contract(path)
    disk_digest = contract_hash(disk_spec)
    if contract_hash(spec) != disk_digest:
        raise ContractLockError(
            "the supplied contract does not match the contract file on disk; "
            "reload it before measuring"
        )
    lock_path = contract_lock_path(path)
    if not lock_path.is_file():
        if require:
            raise ContractLockError(
                f"contract is not confirmed: {path}; run `irsi contract confirm` first"
            )
        return None
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema") != LOCK_SCHEMA:
        raise ContractLockError(f"unsupported contract lock schema: {lock_path}")
    if lock.get("contract_hash") != disk_digest:
        raise ContractLockError(
            "contract changed after confirmation; regenerate, re-review and re-confirm it"
        )
    if not str(lock.get("statement") or "").strip():
        raise ContractLockError("contract lock has no confirmation statement")
    return lock


def contract_hash(spec: InfraTaskSpec) -> str:
    """Canonical semantic hash, independent of YAML formatting and comments."""
    payload = json.dumps(
        spec.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def contract_lock_path(contract_path: str | Path) -> Path:
    path = Path(contract_path)
    return path.with_suffix(path.suffix + ".lock.json")


def contract_draft_path(contract_path: str | Path) -> Path:
    path = Path(contract_path)
    return path.with_suffix(path.suffix + ".draft.json")


def load_contract_draft(contract_path: str | Path) -> dict[str, Any] | None:
    """Load the draft manifest, if this contract was generated by the Agent."""
    path = contract_draft_path(contract_path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract_lock(contract_path: str | Path) -> dict[str, Any] | None:
    path = contract_lock_path(contract_path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_writable_prefixes(objective: str) -> tuple[str, ...]:
    text = objective.lower()
    if any(word in text for word in ("checkpoint", "recompute", "重计算", "激活检查点")):
        return ("activation_checkpoint.",)
    return ("source.",)


def _visible_read_only(
    writable_prefixes: Sequence[str],
    defaults: Sequence[str],
) -> tuple[str, ...]:
    return tuple(
        key for key in defaults
        if not any(key.startswith(prefix) for prefix in writable_prefixes)
    ) or ("training.seed",)


def _load_mapping(path: Path) -> Mapping[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"base config must be a YAML mapping: {path}")
    return payload


def _deep_get(payload: Mapping[str, Any], dotted: str) -> Any:
    current: Any = payload
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _config_bool(payload: Mapping[str, Any], dotted: str, *, default: bool) -> bool:
    value = _deep_get(payload, dotted)
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
    return bool(value)


def _git_root(path: str | Path) -> Path:
    start = Path(path).resolve()
    if start.is_file():
        start = start.parent
    try:
        done = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        done = None
    if done is not None and done.returncode == 0 and done.stdout.strip():
        return Path(done.stdout.strip()).resolve()
    return start


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(dict(payload), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

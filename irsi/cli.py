"""Command-line entry point: ``run`` / ``status`` / ``report`` / ``skills``."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .execution import backends as _backends  # noqa: F401  (plugin registration)
from .contract import surfaces as _surfaces  # noqa: F401
from . import gates as _gates  # noqa: F401
from .execution.backends.hyperparallel import HyperParallelBackend
from .contract import (
    ContractLockError,
    confirm_contract,
    contract_hash,
    contract_summary,
    create_contract_draft,
    load_contract,
    load_contract_draft,
    verify_contract_lock,
)
from .engine import Engine
from .knowledge import DEFAULT_CATALOG, get_skill
from .knowledge.runtime.ledger_store import TaskLedger
from .measurement import MeasurementError, measure_current

__all__ = ["main"]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "task"


def _task_dir(runs_dir: Path, name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return runs_dir / f"{stamp}-{_slug(name)}"


def _cmd_run(args: argparse.Namespace) -> int:
    spec = load_contract(args.contract)
    task_dir = _task_dir(Path(args.runs_dir), spec.name)
    ledger = TaskLedger(
        task_dir,
        {"contract_path": str(Path(args.contract).resolve()), **spec.to_dict()},
    )
    backend = HyperParallelBackend(timeout_min=args.timeout_min or spec.budget.timeout_min)
    engine = Engine(spec, backend, ledger)
    report = engine.run(max_trials=args.max_trials)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        best = report["best"]
        gain = best["gain_vs_baseline"]
        gain_text = "n/a" if gain is None else f"{gain * 100:+.2f}%"
        print(f"task: {task_dir}")
        print(
            f"baseline {report['baseline']['metric']:.6g} -> best {best['metric']:.6g} "
            f"({best['trial']}), gain {gain_text}"
        )
        print(
            f"trials={report['counts']['trials']} kept={report['counts']['kept']} "
            f"discarded={report['counts']['discarded']} crashed={report['counts']['crashed']}"
        )
        print(f"report: {task_dir / 'report.md'}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    state = Path(args.task_dir) / "state.json"
    if not state.is_file():
        print(f"no state.json in {args.task_dir}", file=sys.stderr)
        return 1
    print(state.read_text(encoding="utf-8"))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    root = Path(args.task_dir)
    report_json = root / "report.json"
    report_md = root / "report.md"
    if not report_json.is_file():
        print(f"no report.json in {args.task_dir}", file=sys.stderr)
        return 1
    if args.json:
        print(report_json.read_text(encoding="utf-8"))
    else:
        print(report_md.read_text(encoding="utf-8") if report_md.is_file() else report_json.read_text(encoding="utf-8"))
    return 0


def _cmd_measure(args: argparse.Namespace) -> int:
    spec = load_contract(args.contract)
    backend = HyperParallelBackend(timeout_min=args.timeout_min or spec.budget.timeout_min)
    try:
        measurement = measure_current(
            spec,
            backend,
            artifacts_dir=args.artifacts_dir,
            reference=args.reference,
            freeze_baseline=args.freeze_baseline,
            contract_path=args.contract,
            require_confirmed=(
                args.require_confirmed_contract
                or bool(args.freeze_baseline or args.reference)
            ),
            label=args.label,
        )
    except (ContractLockError, MeasurementError, RuntimeError) as exc:
        print(f"IRSI_MEASURE_ERROR={exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(measurement.payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(f"IRSI_MEASURE_METRIC={measurement.metric:.10g}")
    print("IRSI_MEASURE_GATE=pass")
    print("IRSI_MEASURE_ENGAGED=1")
    print(f"IRSI_MEASURE_RUN_DIR={measurement.run_dir}")
    if args.freeze_baseline:
        print(f"IRSI_MEASURE_BASELINE={Path(args.freeze_baseline).resolve()}")
    return 0


def _cmd_contract_draft(args: argparse.Namespace) -> int:
    try:
        draft = create_contract_draft(
            objective=args.objective,
            out=args.out,
            base_config=args.base_config,
            repo_root=args.repo_root,
            name=args.name,
            domain=args.domain,
            writable_prefixes=args.writable_prefix,
            read_only_keys=args.read_only_key,
            python=args.python,
            env_setup=args.env_setup,
            extra_pythonpath=args.extra_pythonpath,
            nproc=args.nproc,
            seed=args.seed,
            steps=args.steps,
            warmup_steps=args.warmup_steps,
            measured_steps=args.measured_steps,
            memory_budget_gib=args.memory_budget_gib,
            max_trials=args.max_trials,
            timeout_min=args.timeout_min,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"IRSI_CONTRACT_ERROR={exc}", file=sys.stderr)
        return 1

    summary_path = draft.path.with_suffix(draft.path.suffix + ".summary.md")
    if args.json:
        print(
            json.dumps(
                {
                    "status": "draft",
                    "contract_path": str(draft.path),
                    "contract_hash": draft.contract_hash,
                    "confirmation_code": draft.confirmation_code,
                    "summary": draft.summary,
                    "summary_path": str(summary_path),
                    "draft_manifest_path": str(draft.manifest_path),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(draft.summary)
    print()
    print(f"contract: {draft.path}")
    print(f"status: draft (not confirmed)")
    print(f"summary: {summary_path}")
    print("next: show this summary to the user; only after their explicit natural-language")
    print("      confirmation, run `irsi contract confirm` with the confirmation code.")
    return 0


def _draft_objective(contract_path: Path, digest: str) -> str:
    manifest = load_contract_draft(contract_path)
    if not manifest:
        return ""
    if manifest.get("contract_hash") != digest:
        raise ContractLockError(
            "contract changed after the draft was generated; regenerate and re-review it"
        )
    return str(manifest.get("objective") or "")


def _cmd_contract_show(args: argparse.Namespace) -> int:
    path = Path(args.contract).resolve()
    try:
        spec = load_contract(path)
        digest = contract_hash(spec)
        objective = _draft_objective(path, digest)
        lock = verify_contract_lock(path, spec)
    except (ContractLockError, OSError, ValueError, KeyError) as exc:
        print(f"IRSI_CONTRACT_ERROR={exc}", file=sys.stderr)
        return 1
    summary = contract_summary(
        spec, objective=objective, confirmation_code=digest[:12]
    )
    if args.json:
        print(
            json.dumps(
                {
                    "status": "confirmed" if lock else "unconfirmed",
                    "contract_path": str(path),
                    "contract_hash": digest,
                    "confirmation_code": digest[:12],
                    "objective": objective,
                    "summary": summary,
                    "lock": lock,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(summary)
    print()
    print(f"status: {'confirmed' if lock else 'unconfirmed'}")
    if lock:
        print(f"confirmed_by: {lock.get('confirmed_by', '')}")
        print(f"confirmed_at: {lock.get('confirmed_at', '')}")
    return 0


def _cmd_contract_confirm(args: argparse.Namespace) -> int:
    try:
        lock = confirm_contract(
            args.contract,
            confirmation_code=args.code,
            statement=args.statement,
            confirmed_by=args.confirmed_by,
        )
    except (ContractLockError, OSError, ValueError, KeyError) as exc:
        print(f"IRSI_CONTRACT_ERROR={exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(f"IRSI_CONTRACT_CONFIRMED={lock['contract_path']}")
    print(f"IRSI_CONTRACT_HASH={lock['contract_hash']}")
    return 0


def _cmd_skills(args: argparse.Namespace) -> int:
    if args.name:
        skill = get_skill(args.name, args.version)
        if args.json:
            print(json.dumps(skill.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"{skill.name} v{skill.version}")
            print(f"path: {skill.path}")
            print(skill.description)
        if args.body:
            print()
            print(skill.body)
        return 0

    skills = DEFAULT_CATALOG.list_skills(args.query)
    if args.json:
        print(json.dumps([skill.to_dict() for skill in skills], ensure_ascii=False, indent=2))
        return 0
    for skill in skills:
        summary = skill.description.splitlines()[0] if skill.description else ""
        print(f"{skill.name}\tv{skill.version}\t{skill.path}\t{summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch one subcommand."""
    parser = argparse.ArgumentParser(prog="irsi", description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    run = subs.add_parser("run", help="run a task contract")
    run.add_argument("--contract", required=True, help="path to the contract YAML")
    run.add_argument("--runs-dir", default="runs", help="directory that holds task runs")
    run.add_argument("--max-trials", type=int, default=None, help="override budget.max_trials")
    run.add_argument("--timeout-min", type=float, default=None, help="per-trial timeout")
    run.add_argument("--json", action="store_true", help="print the full report as JSON")
    run.set_defaults(func=_cmd_run)

    status = subs.add_parser("status", help="print the task state")
    status.add_argument("task_dir")
    status.set_defaults(func=_cmd_status)

    report = subs.add_parser("report", help="print the task report")
    report.add_argument("task_dir")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=_cmd_report)

    measure = subs.add_parser(
        "measure",
        help="run one trial of the current committed source",
    )
    measure.add_argument("--contract", required=True, help="path to the contract YAML")
    measure.add_argument(
        "--artifacts-dir",
        default="runs/measurements",
        help="parent directory for per-trial logs and measurement.json",
    )
    measure.add_argument(
        "--reference",
        default=None,
        help="frozen measurement.json to compare against for numerical equality",
    )
    measure.add_argument(
        "--freeze-baseline",
        default=None,
        help="write the current measurement to this reference path",
    )
    measure.add_argument("--label", default="measure")
    measure.add_argument(
        "--require-confirmed-contract",
        action="store_true",
        help="reject an unconfirmed or stale contract lock",
    )
    measure.add_argument("--timeout-min", type=float, default=None)
    measure.add_argument("--json", action="store_true")
    measure.set_defaults(func=_cmd_measure)

    contract = subs.add_parser("contract", help="generate, review and confirm a contract")
    contract_subs = contract.add_subparsers(dest="contract_command", required=True)

    contract_draft = contract_subs.add_parser(
        "draft", help="infer a reviewable contract from the workload config"
    )
    contract_draft.add_argument("--objective", required=True, help="user's optimization objective")
    contract_draft.add_argument("--base-config", required=True, help="training YAML to infer from")
    contract_draft.add_argument("--out", required=True, help="new contract YAML path")
    contract_draft.add_argument("--repo-root", default=None, help="repo containing editable source")
    contract_draft.add_argument("--name", default=None, help="contract task name")
    contract_draft.add_argument("--domain", default="source-edit", help="candidate domain identifier")
    contract_draft.add_argument("--writable-prefix", action="append", default=[])
    contract_draft.add_argument("--read-only-key", action="append", default=[])
    contract_draft.add_argument("--python", default=None, help="Python executable for trials")
    contract_draft.add_argument("--env-setup", default=None, help="shell setup for each trial")
    contract_draft.add_argument("--extra-pythonpath", action="append", default=[])
    contract_draft.add_argument("--nproc", type=int, default=None)
    contract_draft.add_argument("--seed", type=int, default=None)
    contract_draft.add_argument("--steps", type=int, default=None)
    contract_draft.add_argument("--warmup-steps", type=int, default=None)
    contract_draft.add_argument("--measured-steps", type=int, default=None)
    contract_draft.add_argument("--memory-budget-gib", type=float, default=24.0)
    contract_draft.add_argument("--max-trials", type=int, default=6)
    contract_draft.add_argument("--timeout-min", type=float, default=25.0)
    contract_draft.add_argument("--json", action="store_true")
    contract_draft.set_defaults(func=_cmd_contract_draft)

    contract_show = contract_subs.add_parser("show", help="show the review summary and lock state")
    contract_show.add_argument("--contract", required=True)
    contract_show.add_argument("--json", action="store_true")
    contract_show.set_defaults(func=_cmd_contract_show)

    contract_confirm = contract_subs.add_parser(
        "confirm", help="freeze the reviewed contract hash"
    )
    contract_confirm.add_argument("--contract", required=True)
    contract_confirm.add_argument("--code", required=True, help="12-character confirmation code")
    contract_confirm.add_argument(
        "--statement", required=True, help="the user's natural-language confirmation"
    )
    contract_confirm.add_argument("--confirmed-by", default="user")
    contract_confirm.add_argument("--json", action="store_true")
    contract_confirm.set_defaults(func=_cmd_contract_confirm)

    skills = subs.add_parser("skills", help="list or show auto-loaded skills")
    skills.add_argument("name", nargs="?", default=None, help="skill name to show")
    skills.add_argument("--version", type=int, default=None, help="skill version")
    skills.add_argument("--query", default=None, help="filter name or description text")
    skills.add_argument("--json", action="store_true", help="print metadata as JSON")
    skills.add_argument("--body", action="store_true", help="print the SKILL.md body")
    skills.set_defaults(func=_cmd_skills)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

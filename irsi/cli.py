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
from .contract import load_contract
from .engine import Engine
from .knowledge import DEFAULT_CATALOG, get_skill
from .knowledge.runtime.ledger_store import TaskLedger

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

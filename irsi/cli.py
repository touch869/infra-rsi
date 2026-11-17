"""Command-line entry point: ``irsi run`` / ``irsi status`` / ``irsi report``."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .execution import backends as _backends  # noqa: F401  (plugin registration)
from .contract import surfaces as _surfaces  # noqa: F401
from . import gates as _gates  # noqa: F401
from .execution.backends.hyperparallel import HyperParallelBackend
from .contract import BudgetSpec, load_contract
from .knowledge.catalog import SkillCatalog
from .knowledge.reader import SkillResolver
from .knowledge.runtime.ledger_store import TaskLedger
from .knowledge.runtime.reader import RuntimeKnowledgeReader
from .knowledge.runtime.record_store import ExperimentRecordStore
from .orchestration import RoundController
from .reporting import ReportBuilder

__all__ = ["main"]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "task"


def _task_dir(runs_dir: Path, name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return runs_dir / f"{stamp}-{_slug(name)}"


def _cmd_run(args: argparse.Namespace) -> int:
    spec = load_contract(args.contract)
    if args.max_trials is not None:
        spec = replace(
            spec,
            budget=BudgetSpec(
                max_trials=args.max_trials,
                timeout_min=spec.budget.timeout_min,
            ),
        )

    task_dir = _task_dir(Path(args.runs_dir), spec.name)
    ledger = TaskLedger(
        task_dir,
        {"contract_path": str(Path(args.contract).resolve()), **spec.to_dict()},
    )
    store = ExperimentRecordStore(task_dir)
    reader = RuntimeKnowledgeReader(store)
    catalog = SkillCatalog.from_root(
        Path(__file__).resolve().parents[1] / "knowledge" / "skills"
    )
    resolver = SkillResolver(catalog)

    backend = HyperParallelBackend(
        timeout_min=args.timeout_min or spec.budget.timeout_min
    )
    controller = RoundController(
        spec,
        backend,
        task_dir,
        store=store,
        reader=reader,
        resolver=resolver,
    )
    state = controller.run_round("round-1")

    report = ReportBuilder(store).build("round-1")
    report_dict = report.to_dict()
    ledger.write_json("report.json", report_dict)
    (task_dir / "report.md").write_text(
        ReportBuilder.render_markdown(report), encoding="utf-8"
    )
    ledger.set_state(
        "COMPLETED",
        round_id=state.round_id,
        stage=state.stage.value,
        trials=state.trials_run,
        best_metric=state.best_metric,
        stop_reason=state.stop_reason,
    )

    if args.json:
        print(json.dumps(report_dict, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        best = report.best_record
        gain = None
        if best is not None and best.metric is not None and report.baseline_metric:
            gain = (best.metric - report.baseline_metric) / report.baseline_metric
        gain_text = "n/a" if gain is None else f"{gain * 100:+.2f}%"
        best_metric = best.metric if best is not None else None
        print(f"task: {task_dir}")
        print(
            f"baseline {report.baseline_metric} -> best {best_metric} "
            f"({best.hypothesis_id if best is not None else 'n/a'}), gain {gain_text}"
        )
        print(f"counts: {dict(report.counts)}")
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
        print(
            report_md.read_text(encoding="utf-8")
            if report_md.is_file()
            else report_json.read_text(encoding="utf-8")
        )
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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

# Copyright 2026 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Command-line interface for the autoresearch loop.

Commands::

    python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py init \\
        --run-dir <dir> --target <file> --benchmark-cmd "<cmd>"
    python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py baseline --run-dir <dir>
    python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py iterate \\
        --run-dir <dir> --why "<expected improvement>" --description "<what changed>"
    python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py status --run-dir <dir>

``iterate`` expects the experimental edit to sit uncommitted in the run's
target files. The tool tests a committed source snapshot, writes the
Why/Change/Result documents, and leaves one reachable step commit.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from config import CONFIG_NAME, load_run_config
from loop import (
    iterate,
    pending_retries,
    record_baseline,
    run_status,
)

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_SKILLS = Path(__file__).resolve().parents[3]
_SHARED_TEMPLATES = _SKILLS / "runtime" / "experiment-record" / "templates"


def _repo_root(start: Path) -> Path:
    """Locate the enclosing git repository root."""
    done = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(done.stdout.strip())


def _freeze_baseline_arg(argv: list[str]) -> str | None:
    """Return the path following ``--freeze-baseline`` in an argv list."""
    for index, item in enumerate(argv):
        if item == "--freeze-baseline" and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith("--freeze-baseline="):
            return item.split("=", 1)[1]
    return None


def _baseline_artifact_path(run_dir: Path, repo_root: Path, value: str) -> str:
    """Normalize a CLI baseline path to a run-relative artifact path."""
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        run_prefix = run_dir.resolve().relative_to(repo_root.resolve()).parts
        if candidate.parts[:len(run_prefix)] == run_prefix:
            resolved = (repo_root / candidate).resolve()
        else:
            resolved = (run_dir / candidate).resolve()
    try:
        relative = resolved.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise ValueError("baseline artifact must stay inside the run directory") from exc
    if relative == Path("."):
        raise ValueError("baseline artifact must name a file")
    return relative.as_posix()


def command_init(args: argparse.Namespace) -> int:
    """Scaffold a run directory: run.json plus the shared record templates."""
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    repo_root = _repo_root(run_dir)  # fail fast when the run dir is outside a git repository
    config_file = run_dir / CONFIG_NAME
    if config_file.exists() and not args.force:
        print(f"refusing to overwrite existing {config_file} (use --force)")
        return 1
    baseline_cmd = shlex.split(args.baseline_cmd) if args.baseline_cmd else []
    baseline_artifact = args.baseline_artifact
    try:
        inferred = _freeze_baseline_arg(baseline_cmd)
        if inferred:
            inferred_path = _baseline_artifact_path(run_dir, repo_root, inferred)
            if baseline_artifact:
                explicit_path = _baseline_artifact_path(run_dir, repo_root, baseline_artifact)
                if explicit_path != inferred_path:
                    raise ValueError(
                        "--baseline-artifact conflicts with --freeze-baseline in --baseline-cmd"
                    )
            baseline_artifact = inferred_path
        elif baseline_artifact:
            baseline_artifact = _baseline_artifact_path(run_dir, repo_root, baseline_artifact)
    except ValueError as exc:
        print(f"invalid baseline artifact: {exc}", file=sys.stderr)
        return 1
    payload = {
        "target_files": list(args.target),
        "benchmark_cmd": shlex.split(args.benchmark_cmd),
        "baseline_artifact": baseline_artifact,
        "gate_cmd": shlex.split(args.gate_cmd) if args.gate_cmd else [],
        "metric_pattern": args.metric_pattern,
        "metric_lower_is_better": True,
        "noise_fraction": args.noise_fraction,
        "bench_must_match": list(args.bench_must_match),
        "gate_must_match": list(args.gate_must_match),
    }
    if baseline_cmd:
        payload["baseline_cmd"] = baseline_cmd
    if not baseline_artifact:
        del payload["baseline_artifact"]
    config_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    template_sources = {
        "manual.md": _TEMPLATES / "manual.md",
        "ideas.md": _SHARED_TEMPLATES / "ideas.md",
        "results.tsv": _SHARED_TEMPLATES / "results.tsv",
        "learnings.md": _SHARED_TEMPLATES / "learnings.md",
        "experiment_log.md": _SHARED_TEMPLATES / "experiment_log.md",
    }
    for name, source in template_sources.items():
        destination = run_dir / name
        if not destination.exists():
            shutil.copyfile(source, destination)
    print(f"initialized autoresearch run at {run_dir}")
    print("next: edit manual.md [SETUP], seed ideas.md, then run `baseline`")
    return 0


def _load(args: argparse.Namespace):
    """Load the run configuration for a subcommand."""
    run_dir = Path(args.run_dir).resolve()
    return load_run_config(run_dir, _repo_root(run_dir))


def command_baseline(args: argparse.Namespace) -> int:
    """Benchmark the current commit and record the first keep row."""
    outcome = record_baseline(_load(args), args.description, args.why)
    print(f"{outcome.status}: metric={outcome.metric} ({outcome.detail})")
    print(f"step_commit={outcome.experiment_commit} measured_commit={outcome.measured_commit}")
    return 0 if outcome.kept else 1


def command_iterate(args: argparse.Namespace) -> int:
    """Run one experiment iteration on the pending target-file edit."""
    config = _load(args)
    outcome = iterate(config, args.description, why=args.why, changes=tuple(args.changes),
                      revisit_on=tuple(args.revisit_on), retry_of=args.retry_of)
    print(f"{outcome.status}: metric={outcome.metric} best_before={outcome.best_before}")
    print(f"step_commit={outcome.experiment_commit} measured_commit={outcome.measured_commit} "
          f"({outcome.detail})")
    for row in pending_retries(config):
        print(f"retry_ready={row['commit']} ({row['change']['summary']})")
    return 0 if outcome.status != "crash" else 1


def command_status(args: argparse.Namespace) -> int:
    """Print a short summary of the run."""
    print(run_status(_load(args), tail=args.tail))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py",
        description="Bounded autonomous-experiment loop (benchmark + gate + bookkeeping).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="scaffold a run directory")
    init.add_argument("--run-dir", required=True)
    init.add_argument("--target", action="append", required=True,
                      help="repo-relative file the agent may modify (repeatable)")
    init.add_argument("--benchmark-cmd", required=True)
    init.add_argument(
        "--baseline-cmd",
        default="",
        help="optional command used only for the initial baseline measurement",
    )
    init.add_argument(
        "--baseline-artifact",
        default="",
        help="frozen baseline JSON path, run-relative (inferred from --freeze-baseline)",
    )
    init.add_argument("--gate-cmd", default="")
    init.add_argument("--metric-pattern", default=r"total_ms=(?P<metric>[0-9.]+)")
    init.add_argument("--noise-fraction", type=float, default=0.02)
    init.add_argument("--bench-must-match", action="append", default=[])
    init.add_argument("--gate-must-match", action="append", default=[])
    init.add_argument("--force", action="store_true")
    init.set_defaults(handler=command_init)

    baseline = commands.add_parser("baseline", help="record the starting metric")
    baseline.add_argument("--run-dir", required=True)
    baseline.add_argument("--description", default="baseline")
    baseline.add_argument("--why", default="Establish the measured starting point")
    baseline.set_defaults(handler=command_baseline)

    iteration = commands.add_parser("iterate", help="measure the pending edit")
    iteration.add_argument("--run-dir", required=True)
    iteration.add_argument("--description", required=True)
    iteration.add_argument("--why", required=True, help="hypothesis and expected improvement")
    iteration.add_argument("--changes", action="append", default=[], help="configuration scope changed (repeatable)")
    iteration.add_argument("--revisit-on", action="append", default=[],
                           help="retry after a keep changes this scope (repeatable)")
    iteration.add_argument("--retry-of", help="full commit ID reported as retry_ready")
    iteration.set_defaults(handler=command_iterate)

    status = commands.add_parser("status", help="summarize the run")
    status.add_argument("--run-dir", required=True)
    status.add_argument("--tail", type=int, default=5)
    status.set_defaults(handler=command_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())

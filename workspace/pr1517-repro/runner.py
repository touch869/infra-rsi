#!/usr/bin/env python3
"""Training wrapper for the PR #1517 autoresearch reproduction on 8x910B4.

Bridges HyperParallel ``scripts/train_lm.py`` to the PR's structured training
contract: runs one gate (correctness window) or benchmark (performance window)
training job, then emits ``steady_*`` metric lines and exactly one terminal
``RSI_TRAINING_RECEIPT`` JSON line (see
.agent/skills/perf-playbook/references/training-rsi.md in the PR checkout).

The candidate edit under test lives in ``exec_config.json`` (the autoresearch
target file): ``mode`` selects the activation-checkpoint execution setting and
``inject`` optionally simulates a fault (``silent_fallback`` renders the
requested mode but keeps the previous one active, ``numerical_corruption``
perturbs grad clipping so the numeric fingerprint must diverge).

Engagement evidence is twofold: the resolved-config dump in the training log
must show the requested mode, and the per-device peak memory must fall in that
mode's band (full ~4.0 GB, off ~9.1 GB, selective ~4.9 GB on this workload).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[1]
WORKSPACE = Path("/root/irsi-workspace")
BASE_YAML = WORKSPACE / "configs" / "train_medium.yaml"
PYTHON = "/root/miniconda3/envs/irsi/bin/python"
SET_ENV = "/usr/local/Ascend/ascend-toolkit/latest/set_env.sh"
RECEIPT_PREFIX = "RSI_TRAINING_RECEIPT"

GATE_STEPS = 8
BENCH_STEPS = 32
WARMUP_STEPS = 8
MEASURED_STEPS = 16
GATE_TIMEOUT_S = 900
BENCH_TIMEOUT_S = 1200

# Peak-memory band (GB) per execution mode, measured on this 8x910B4 host.
MEM_BANDS = {"full": (0.0, 4.5), "off": (7.0, 99.0), "selective": (4.5, 7.0)}

STEP_LINE = re.compile(r"\| step=(\d+) ")
KV_TOKEN = re.compile(
    r"([A-Za-z0-9_/.-]+)=(-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
MODE_DUMP = re.compile(
    r'"activation_checkpoint":\s*\{\s*"mode":\s*"([a-z]+)"')


def workload_id() -> str:
    """Stable digest of the frozen workload identity (data, shape, hardware).

    Per the PR contract the series ID derives from the frozen data, shape,
    hardware and topology - deliberately not from the git HEAD, so scaffolding
    commits cannot invalidate an in-flight run.
    """
    digest = hashlib.sha256()
    for path in (BASE_YAML, WORKSPACE / "configs" / "medium-qwen3" / "config.json"):
        digest.update(path.read_bytes())
    digest.update(b"nproc=8\ndtype=bfloat16\nseq_len=4096\ngbs=8\n")
    return f"sha256:{digest.hexdigest()[:16]}"


def read_exec_config() -> dict:
    data = json.loads((RUN_DIR / "exec_config.json").read_text(encoding="utf-8"))
    mode = data.get("mode", "full")
    if mode not in MEM_BANDS:
        raise SystemExit(f"unknown mode {mode!r} in exec_config.json")
    return {"mode": mode, "inject": data.get("inject")}


def render_yaml(steps: int, exec_cfg: dict, trial_dir: Path) -> Path:
    """Render one trial YAML from the base config with line-level overrides."""
    text = BASE_YAML.read_text(encoding="utf-8")
    text, n_iters = re.subn(r"train_iters: \d+", f"train_iters: {steps}", text)
    # silent_fallback: the requested mode never reaches the training config -
    # the previous active setting (full) keeps running.
    active_mode = "full" if exec_cfg["inject"] == "silent_fallback" else exec_cfg["mode"]
    text, n_mode = re.subn(r"mode: full", f"mode: {active_mode}", text)
    if n_iters != 1 or n_mode != 1:
        raise SystemExit(f"render failed (train_iters x{n_iters}, mode x{n_mode})")
    if exec_cfg["inject"] == "numerical_corruption":
        text, n_clip = re.subn(r"max_grad_norm: 1\.0", "max_grad_norm: 0.001", text)
        if n_clip != 1:
            raise SystemExit(f"grad-clip injection failed x{n_clip}")
    yaml_path = trial_dir / "train.yaml"
    yaml_path.write_text(text, encoding="utf-8")
    return yaml_path


def launch_training(yaml_path: Path, timeout_s: int, log_path: Path) -> tuple[int, float]:
    """Run the 8-device training job; kill the whole process group on timeout."""
    command = (
        f"source {SET_ENV} && cd {REPO_ROOT} && "
        f"export PYTHONPATH={REPO_ROOT}:{WORKSPACE}:$PYTHONPATH && "
        f"{PYTHON} -m torch.distributed.run --nproc_per_node=8 "
        f"scripts/train_lm.py {yaml_path}"
    )
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            ["bash", "-lc", command], cwd=str(REPO_ROOT),
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            returncode = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            returncode = -9
    return returncode, time.monotonic() - started


def parse_log(log_path: Path) -> dict:
    """Extract per-step metrics, resolved mode and peak memory from the log."""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    # The resolved-config dump is pretty-printed JSON spanning two lines
    # ("activation_checkpoint": {\n  "mode": "full"), so match on the whole
    # text rather than line by line.
    dump_hit = MODE_DUMP.search(text)
    dump_mode = dump_hit.group(1) if dump_hit else None
    steps: dict[int, dict[str, float]] = {}
    for line in text.splitlines():
        hit = STEP_LINE.search(line)
        if not hit:
            continue
        values = {key: float(value) for key, value in KV_TOKEN.findall(line)}
        if values:
            steps[int(hit.group(1))] = values
    loss_of = lambda v: v.get("training/foundation_loss", v.get("training/total_loss"))
    grad_of = lambda v: v.get("training/grad_norm", v.get("grad_norm"))
    mem_peak = max((v.get("memory/device_max_allocated_gb", 0.0) for v in steps.values()),
                   default=0.0)
    return {
        "steps": steps,
        "dump_mode": dump_mode,
        "mem_peak": mem_peak,
        "loss_of": loss_of,
        "grad_of": grad_of,
    }


def numeric_fingerprint(parsed: dict) -> tuple[str, int]:
    """SHA256 over 'step|loss|grad_norm' rows (infra-rsi convention); first divergence."""
    digest = hashlib.sha256()
    frozen = json.loads((RUN_DIR / "fingerprint.json").read_text(encoding="utf-8")) \
        if (RUN_DIR / "fingerprint.json").exists() else None
    diverged_at = 0
    for step in sorted(parsed["steps"]):
        row = parsed["steps"][step]
        loss, grad = parsed["loss_of"](row), parsed["grad_of"](row)
        if loss is None or grad is None:
            continue
        digest.update(f"{step}|{loss!r}|{grad!r}\n".encode())
        if frozen and diverged_at == 0:
            key = str(step)
            if key not in frozen["steps"] or (
                    frozen["steps"][key] != [repr(loss), repr(grad)]):
                diverged_at = step
    return digest.hexdigest(), diverged_at


def freeze_fingerprint(digest: str, parsed: dict) -> None:
    rows = {}
    for step in sorted(parsed["steps"]):
        row = parsed["steps"][step]
        loss, grad = parsed["loss_of"](row), parsed["grad_of"](row)
        if loss is not None and grad is not None:
            rows[str(step)] = [repr(loss), repr(grad)]
    (RUN_DIR / "fingerprint.json").write_text(
        json.dumps({"sha256": digest, "steps": rows}, indent=1), encoding="utf-8")


def engagement(parsed: dict, expected_mode: str) -> bool:
    """Positive evidence that the requested execution path actually ran."""
    if parsed["dump_mode"] != expected_mode:
        return False
    low, high = MEM_BANDS[expected_mode]
    return low <= parsed["mem_peak"] <= high


def steady_tokens_per_second(parsed: dict) -> float | None:
    ordered = [parsed["steps"][s].get("performance/tokens_per_second")
               for s in sorted(parsed["steps"])]
    ordered = [v for v in ordered if v is not None]
    window = ordered[WARMUP_STEPS:WARMUP_STEPS + MEASURED_STEPS]
    if len(window) < MEASURED_STEPS:
        return None
    return statistics.median(window)


def emit_receipt(phase: str, status: str, completed: int, engaged: bool,
                 first_error_step: int | None = None) -> None:
    print(f"{RECEIPT_PREFIX} " + json.dumps({
        "workload_id": workload_id(),
        "phase": phase,
        "status": status,
        "completed_steps": completed,
        "engaged": engaged,
        "allocation_retries": None,
        "first_error_step": first_error_step,
    }, sort_keys=True))


def run_phase(phase: str) -> int:
    exec_cfg = read_exec_config()
    steps = GATE_STEPS if phase == "gate" else BENCH_STEPS
    timeout_s = GATE_TIMEOUT_S if phase == "gate" else BENCH_TIMEOUT_S
    stamp = time.strftime("%H%M%S")
    tag = exec_cfg["mode"] + (f"-{exec_cfg['inject']}" if exec_cfg["inject"] else "")
    trial_dir = RUN_DIR / "trials" / f"{phase}-{tag}-{stamp}"
    trial_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = render_yaml(steps, exec_cfg, trial_dir)
    returncode, seconds = launch_training(
        yaml_path, timeout_s, trial_dir / "run.log")
    parsed = parse_log(trial_dir / "run.log")
    completed = max(parsed["steps"], default=0)
    engaged = engagement(parsed, exec_cfg["mode"])
    print(f"phase={phase} requested_mode={exec_cfg['mode']} "
          f"dump_mode={parsed['dump_mode']} mem_peak_gb={parsed['mem_peak']:.3f} "
          f"completed_steps={completed} wall_s={seconds:.0f}")

    if returncode != 0 and not parsed["steps"]:
        emit_receipt(phase, "error", completed, engaged)
        return 1
    if returncode == -9:
        emit_receipt(phase, "error", completed, engaged)
        return 1
    if completed != steps:
        emit_receipt(phase, "incomplete", completed, engaged)
        return 1

    digest, diverged_at = numeric_fingerprint(parsed)
    if phase == "gate":
        if not (RUN_DIR / "fingerprint.json").exists():
            freeze_fingerprint(digest, parsed)  # baseline: freeze and pass
            emit_receipt(phase, "passed", completed, engaged)
            return 0
        if diverged_at:
            emit_receipt(phase, "numerical_mismatch", completed, engaged,
                         first_error_step=diverged_at)
            return 1
        emit_receipt(phase, "passed", completed, engaged)
        return 0

    tps = steady_tokens_per_second(parsed)
    if tps is None:
        emit_receipt(phase, "incomplete", completed, engaged)
        return 1
    print(f"steady_tokens_per_second={tps:.2f}")
    print(f"steady_peak_mem_gb={parsed['mem_peak']:.3f}")
    print(f"steady_engaged_mode={exec_cfg['mode'] if engaged else 'NOT_ENGAGED'}")
    emit_receipt(phase, "passed", completed, engaged)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("gate", "benchmark"))
    parser.add_argument("--print-workload-id", action="store_true")
    args = parser.parse_args()
    if args.print_workload_id:
        print(workload_id())
        return 0
    if not args.phase:
        parser.error("--phase is required unless --print-workload-id is given")
    return run_phase(args.phase)


if __name__ == "__main__":
    sys.exit(main())

"""Parse one training log into per-step metrics and a numeric fingerprint."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

__all__ = ["StepMetric", "TrialMetrics", "parse_log"]

_TOKEN = re.compile(r"([A-Za-z0-9_/.-]+)=(-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_LOSS_KEYS = ("training/foundation_loss", "training/total_loss", "foundation_loss")
_GRAD_KEYS = ("training/grad_norm", "grad_norm")


def _first(fields: Dict[str, float], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        if key in fields:
            return fields[key]
    return None


@dataclass(frozen=True)
class StepMetric:
    """One optimizer step as reported by the trainer."""

    step: int
    loss: Optional[float]
    grad_norm: Optional[float]
    step_time: Optional[float]
    tokens_per_second: Optional[float]
    peak_mem_gib: Optional[float]


@dataclass(frozen=True)
class TrialMetrics:
    """All parsed steps of one trial plus its exit status."""

    steps: Tuple[StepMetric, ...]
    exit_code: int = 0
    timed_out: bool = False
    traceback: bool = False

    @property
    def completed_steps(self) -> int:
        return len(self.steps)

    @property
    def last_step(self) -> int:
        return self.steps[-1].step if self.steps else 0

    @property
    def peak_mem_gib(self) -> Optional[float]:
        values = [s.peak_mem_gib for s in self.steps if s.peak_mem_gib is not None]
        return max(values) if values else None

    def steady(self, field_name: str, warmup_steps: int, measured_steps: int) -> Optional[float]:
        """Median of ``measured_steps`` values after ``warmup_steps`` (or all left)."""
        values = [
            float(getattr(s, field_name))
            for s in self.steps
            if getattr(s, field_name) is not None
        ][warmup_steps:]
        if not values:
            return None
        values = values[-measured_steps:] if measured_steps > 0 else values
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    @property
    def numeric_hash(self) -> str:
        """Exact fingerprint of loss/grad_norm across steps (bitwise gate)."""
        digest = hashlib.sha256()
        for step in self.steps:
            if step.loss is None or step.grad_norm is None:
                continue
            digest.update(f"{step.step}|{step.loss!r}|{step.grad_norm!r}\n".encode())
        return digest.hexdigest()

    def value(self, key: str, *, warmup_steps: int = 0, measured_steps: int = 0) -> Optional[float]:
        """Resolve a contract metric key to a measured value."""
        if key in ("performance/tokens_per_second", "tokens_per_second", "tps"):
            return self.steady("tokens_per_second", warmup_steps, measured_steps)
        if key in ("performance/step_time", "step_time"):
            return self.steady("step_time", warmup_steps, measured_steps)
        if key in ("memory/device_max_allocated_gb", "peak_mem_gib"):
            return self.peak_mem_gib
        if key in ("training/foundation_loss", "training/total_loss", "loss"):
            return self.steps[-1].loss if self.steps else None
        raise KeyError(f"unsupported metric key: {key}")


def parse_log(
    text: str,
    *,
    exit_code: int = 0,
    timed_out: bool = False,
    traceback: bool = False,
) -> TrialMetrics:
    """Parse per-step metric lines from combined stdout/stderr."""
    by_step: Dict[int, StepMetric] = {}
    for line in text.splitlines():
        if "step=" not in line:
            continue
        fields: Dict[str, float] = {}
        for match in _TOKEN.finditer(line):
            key, raw = match.group(1), match.group(2)
            try:
                fields[key] = float(raw)
            except ValueError:
                continue
        if "step" not in fields:
            continue
        step = int(fields["step"])
        by_step[step] = StepMetric(
            step=step,
            loss=_first(fields, _LOSS_KEYS),
            grad_norm=_first(fields, _GRAD_KEYS),
            step_time=_first(fields, ("performance/step_time", "step_time")),
            tokens_per_second=_first(
                fields, ("performance/tokens_per_second", "tokens_per_second", "tokens/s")
            ),
            peak_mem_gib=_first(
                fields, ("memory/device_max_allocated_gb", "memory/peak_mem_gib")
            ),
        )
    steps = tuple(by_step[key] for key in sorted(by_step))
    return TrialMetrics(
        steps=steps,
        exit_code=exit_code,
        timed_out=timed_out,
        traceback=traceback or "Traceback (most recent call last)" in text,
    )

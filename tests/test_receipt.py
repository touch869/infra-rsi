"""Log parsing: per-step metrics, steady-state medians and the numeric hash."""

from __future__ import annotations

from irsi.execution.metric_extractor import parse_log

LINE = (
    "Training:  50%|#####     | 10/20 [00:03<00:03,  1.73s/step] | step={step} epoch=0 "
    "data/consumed_samples=8 data/step_tokens=16368 memory/device_max_allocated_gb={mem} "
    "memory/device_max_reserved_gb=1.69 performance/step_time={step_time} "
    "performance/tokens_per_second={tps} training/foundation_loss={loss} "
    "training/grad_norm={grad} training/lr=0.0001"
)


def _log(steps=6, tps=100.0, loss=1.0, grad=2.0, mem=1.5, step_time=0.5):
    return "\n".join(
        LINE.format(
            step=i + 1,
            tps=tps + i,
            loss=loss + i * 0.001,
            grad=grad,
            mem=mem,
            step_time=step_time,
        )
        for i in range(steps)
    )


def test_parse_steps_and_fields():
    metrics = parse_log(_log())
    assert metrics.completed_steps == 6
    assert metrics.last_step == 6
    assert metrics.peak_mem_gib == 1.5
    assert metrics.steps[0].loss == 1.0
    assert metrics.steps[0].grad_norm == 2.0
    assert metrics.steps[0].tokens_per_second == 100.0


def test_steady_state_median_skips_warmup():
    metrics = parse_log(_log(steps=6, tps=100.0))
    # tps values: 100,101,102,103,104,105 -> drop 2 warmup, take last 3
    assert metrics.steady("tokens_per_second", 2, 3) == 104.0


def test_hash_is_stable_and_sensitive():
    first = parse_log(_log()).numeric_hash
    assert first == parse_log(_log()).numeric_hash
    assert first != parse_log(_log(loss=1.5)).numeric_hash


def test_traceback_and_exit_are_captured():
    metrics = parse_log("Traceback (most recent call last):\nboom", exit_code=1)
    assert metrics.traceback is True
    assert metrics.exit_code == 1
    assert metrics.completed_steps == 0


def test_metric_value_resolves_contract_keys():
    metrics = parse_log(_log())
    assert metrics.value("performance/tokens_per_second", warmup_steps=0, measured_steps=6) == 102.5
    assert metrics.value("memory/device_max_allocated_gb") == 1.5

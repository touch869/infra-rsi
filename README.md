# infra-rsi

Closed-loop experiment harness for training-infra optimization (phase 1).

One command runs a task contract end to end: **baseline → hypotheses → gates →
decision → ledger**, and produces a report with the measured gain. The first
edit surface is activation recompute on HyperParallel; the harness itself is
plugin-based so backends, gates and edit surfaces are added without touching the
engine.

## Architecture

```
entry       cli.py
engine      baseline -> candidates -> gates -> keep/discard/crash -> ledger
plugins     contract/surfaces/ (which candidates a surface offers)
            execution/backends/ (how a trial runs)
            gates/ (receipt, bitwise, memory)
contract    contract/task_spec.py (what may change, how it is judged)
knowledge   knowledge/skill_catalog.py (auto-loads SKILL.md)
            knowledge/runtime/ledger_store.py (append-only runtime evidence)
reporting   reporting/ (step/round reports + exporters/)
```

Dependency rule: `engine` never imports torch or HyperParallel; it talks to a
`Backend`. Gates never mutate a trial. Surfaces only emit contract-approved
overrides, and the contract rejects any key outside `writable_prefixes`.

## Skills

Skills are auto-discovered from `SKILL.md` frontmatter anywhere under
`irsi/knowledge/`. `irsi skills` lists them; `irsi skills experiment-record
--body` prints the loaded instructions. The `experiment-record` skill defines
the per-step why/change/test record and its commit and rollback accounting.
The `profiling` skill targets Ascend NPU + HyperParallel and lives at
`irsi/knowledge/analysis/profiling/ascend/hyperparallel/`; other environments
can add sibling variants under `analysis/profiling/`.
The peer `moe-profiler` skill extracts MoE expert-load, All-to-All, routing,
and gradient facts from logs, profile captures, and checkpoints under
`irsi/knowledge/analysis/moe-profiler/ascend/hyperparallel/`.
The `parallel-strategy-planner` skill plans DP/FSDP/TP/PP/EP/CP strategies
for Ascend and NVIDIA hardware, with HyperParallel DeviceMesh output, under
`irsi/knowledge/strategy/parallel-strategy-planner/generic/hyperparallel/`.
The `sapp-parallel-strategy` skill prices concrete layouts on Ascend dies with
HyperParallel's device-free ND model under
`irsi/knowledge/strategy/sapp-parallel-strategy/ascend/hyperparallel/`.
The `perf-playbook` skill maps a measured bottleneck to a tuning technique and
records the change in a tuning summary under
`irsi/knowledge/strategy/perf-playbook/ascend/hyperparallel/`.
The `strategy-optimizer` skill runs a bounded parallel-layout search with
real-device benchmarks under
`irsi/knowledge/strategy/strategy-optimizer/generic/hyperparallel/`.
The `moe-optimizer` skill closes the loop from MoE profiling and diagnosis to
candidate generation and refinement under
`irsi/knowledge/strategy/moe-optimizer/generic/hyperparallel/`.
The `memory-analysis` skill captures and breaks down Ascend NPU allocation
snapshots under `irsi/knowledge/analysis/memory-analysis/ascend/generic/`.
The `precision` skill captures msprobe dumps, compares candidate and reference
runs, and localizes numerical divergence under
`irsi/knowledge/analysis/precision/ascend/generic/`.
Validation skills live under `irsi/knowledge/validation/`:
`bringup-benchmark` scores bring-up assets and A/B evidence;
`formal-verification` drives FM-Agent contracts and counterexamples;
`hf-model-precision-validation` checks numerical acceptance on Ascend;
`routing-validator` checks MoE token, ordering and gradient-flow invariants;
and `strategy-validator` measures parallel-strategy candidates.

## Quickstart (Ascend host)

```bash
pip install -e .
# model configs, base YAMLs and the dataset generator live in workspace/
cp -r workspace/. /root/irsi-workspace/
(cd /root/irsi-workspace && python make_data.py --out data/tiny-packed)
irsi run --contract contracts/medium-qwen3.yaml --runs-dir runs
irsi report runs/<task-dir>
```

`contracts/tiny-qwen3.yaml` is the 12-layer smoke contract; `medium-qwen3.yaml`
is the 24-layer measurement contract. The latest evidence is exported under
`results/medium-qwen3-20261112/` (**+20.63%** throughput vs baseline, **+15.78%**
vs the no-op control, bitwise-identical numerics), and the write-up is
`docs/phase1-result.md`.

The contract pins the repo, base YAML, writable key surface, metric, gates and
budget. Every trial writes `train.yaml`, `run.log`, `metrics.json`; the task
writes `results.tsv`, `candidates.jsonl`, `decisions/*.json`, `report.md`.

## Layerwise recompute (optional patch)

`patches/0001-qwen3-recompute-policy.patch` declares `ModelAdapterSpec.recompute`
for Qwen3 dense, which unlocks per-layer recompute
(`activation_checkpoint.selection.layer_count`). Apply it to the HyperParallel
checkout, then run a layerwise contract:

```bash
git -C ../hyper-parallel am patches/0001-qwen3-recompute-policy.patch
irsi run --contract contracts/medium-qwen3-layerwise.yaml --runs-dir runs
```

The ladder comes from `domain_params.layer_counts`; three example budgets are
shipped (24 GiB, 8 GiB, 6 GiB). Results: `docs/layerwise-recompute-result.md`
and `results/layerwise-20261113/` (`layers-0` +34.29% vs the same-run baseline;
`layers-6` +28.04% at 8 GiB; `layers-14` +9.39% at 6 GiB; all numerics bitwise
identical). Note that installing the patch makes `mode=full` take the
adapter-region wrapper path, which is ~7–13% slower than HF native checkpointing.

## Gates (phase 1)

| gate | checks |
|---|---|
| `receipt` | exit 0, no traceback, expected step count |
| `bitwise` | loss / grad_norm fingerprint identical to baseline |
| `memory` | peak device memory within budget |

## Edit surfaces

`contract/surfaces/recompute.py` emits the recompute candidates (`off`,
`control`, `selective`, `swap` variants) and the layerwise ladder
(`recompute-layerwise`, driven by `domain_params.layer_counts`). A new surface
(fusion, parallel, pipeline) is a new surface plugin plus a contract that
declares its `writable_prefixes`.

## Tests

```bash
python -m pytest -q
```

Design docs live in `docs/`: `architecture-phase1-task-aligned.md`,
`directory-plan.md`, `architecture-comparison-inferrsi.md`,
`architecture-comparison-hp-pr1517.md`; results in `phase1-result.md` and
`layerwise-recompute-result.md`. Older design notes are in `docs/archive/`.

# infra-rsi

Experiment harness for Agent-driven training-infra optimization (phase 1).

The main controller is the `autoresearch` skill. The user states an optimization
objective in natural language; the host Agent reads the skill, analyses the
baseline, proposes candidates, edits the declared target files, and lets
`autoresearch` run the deterministic **gate → benchmark → keep/discard/crash →
record → commit** loop.

The repository supplies the deterministic pieces the controller needs: contract
validation, one-trial measurement (`irsi measure`), receipt/memory/numerical
gates, source-safe configuration rendering, and the experiment ledger. It does
not need a second orchestration engine or a fixed candidate list.

## Architecture

```
entry       cli.py
controller  knowledge/skills/execution/autoresearch/
measurement irsi measure -> backend -> gates -> metric + evidence
loop        baseline -> one candidate -> gate -> benchmark -> decision -> commit
plugins     contract/surfaces/ (optional fixed candidates for legacy irsi run)
            execution/backends/ (how a trial runs)
            gates/ (receipt, bitwise, memory)
contract    contract/task_spec.py (what may change, how it is judged)
knowledge   knowledge/skill_catalog.py (auto-loads knowledge/skills/**/SKILL.md)
            knowledge/runtime/ledger_store.py (append-only runtime evidence)
reporting   reporting/ (step/round reports + exporters/)
```

Dependency rule: `engine` never imports torch or HyperParallel; it talks to a
`Backend`. Gates never mutate a trial. Surfaces only emit contract-approved
overrides, and the contract rejects any key outside `writable_prefixes`.

## Skills

Skills are auto-discovered from `SKILL.md` frontmatter anywhere under
`irsi/knowledge/skills/`. `irsi skills` lists them; `irsi skills autoresearch
--body` prints the controller instructions. The `experiment-record` skill defines
the per-step why/change/test record and its commit and rollback accounting, and
lives at `irsi/knowledge/skills/runtime/experiment-record/`.
The `profiling` skill targets Ascend NPU + HyperParallel and lives at
`irsi/knowledge/skills/analysis/profiling/ascend/hyperparallel/`; other environments
can add sibling variants under `irsi/knowledge/skills/analysis/profiling/`.
The peer `moe-profiler` skill extracts MoE expert-load, All-to-All, routing,
and gradient facts from logs, profile captures, and checkpoints under
`irsi/knowledge/skills/analysis/moe-profiler/ascend/hyperparallel/`.
The `parallel-strategy-planner` skill plans DP/FSDP/TP/PP/EP/CP strategies
for Ascend and NVIDIA hardware, with HyperParallel DeviceMesh output, under
`irsi/knowledge/skills/strategy/parallel-strategy-planner/generic/hyperparallel/`.
The `sapp-parallel-strategy` skill prices concrete layouts on Ascend dies with
HyperParallel's device-free ND model under
`irsi/knowledge/skills/strategy/sapp-parallel-strategy/ascend/hyperparallel/`.
The `perf-playbook` skill maps a measured bottleneck to a tuning technique and
records the change in a tuning summary under
`irsi/knowledge/skills/strategy/perf-playbook/ascend/hyperparallel/`.
The `strategy-optimizer` skill runs a bounded parallel-layout search with
real-device benchmarks under
`irsi/knowledge/skills/strategy/strategy-optimizer/generic/hyperparallel/`.
The `moe-optimizer` skill closes the loop from MoE profiling and diagnosis to
candidate generation and refinement under
`irsi/knowledge/skills/strategy/moe-optimizer/generic/hyperparallel/`.
The `memory-analysis` skill captures and breaks down Ascend NPU allocation
snapshots under `irsi/knowledge/skills/analysis/memory-analysis/ascend/generic/`.
The `precision` skill captures msprobe dumps, compares candidate and reference
runs, and localizes numerical divergence under
`irsi/knowledge/skills/analysis/precision/ascend/generic/`.
Validation skills live under `irsi/knowledge/skills/validation/`:
`bringup-benchmark` scores bring-up assets and A/B evidence;
`formal-verification` drives FM-Agent contracts and counterexamples;
`hf-model-precision-validation` checks numerical acceptance on Ascend;
`routing-validator` checks MoE token, ordering and gradient-flow invariants;
and `strategy-validator` measures parallel-strategy candidates.
Execution skills live under `irsi/knowledge/skills/execution/`: `autoresearch` is
the generic experiment controller described above, and `mfu-riser` drives the
Ascend + HyperParallel MFU optimization controller.

`autoresearch` assigns work to bounded subagents: analysis produces a diagnosis
with evidence, strategy proposes a ranked shortlist, an implementer applies one
candidate in `target_files`, and the deterministic `iterate` command performs the
gate, benchmark, record and commit. Observe and propose may run in parallel;
target-file edits are serial. The full ownership and handoff rules are in
`autoresearch/SKILL.md` and are copied into each run's `manual.md`.

## Quickstart (Ascend host)

The preferred entry is natural language to the host Agent:

```text
在 contracts/tiny-qwen3.yaml 下把吞吐提高 15%，保持 loss/grad_norm 完全一致；
用 autoresearch 跑 baseline、分析瓶颈、提出候选、逐个验证，失败实验保留报告并回退代码。
```

The Agent does not ask the user to write contract YAML. It inspects the target
repository/base config, generates a draft, shows the natural-language summary,
and waits for an explicit user confirmation:

```bash
python -m irsi.cli contract draft \
  --objective "把吞吐提高 15%，保持 loss/grad_norm 完全一致" \
  --base-config /root/irsi-workspace/configs/train_tiny.yaml \
  --repo-root /root/hyper-parallel --out contracts/tiny-qwen3.generated.yaml
python -m irsi.cli contract show --contract contracts/tiny-qwen3.generated.yaml

# Show the summary, semantic hash and confirmation code to the user and WAIT.
# Only the user's explicit natural-language confirmation authorizes this:
python -m irsi.cli contract confirm \
  --contract contracts/tiny-qwen3.generated.yaml --code <shown-code> \
  --statement "<用户的确认原话>" --confirmed-by user
```

`draft` also writes `<contract>.summary.md` and `<contract>.draft.json`; `confirm`
writes `<contract>.lock.json`. The lock is a semantic hash, so comments or YAML
formatting may change, but workload/metric/gates/editable surface may not. Any
semantic change requires a new draft, a new user confirmation, and a new baseline.

After confirmation, the Agent uses `autoresearch` as the controller and
`irsi measure` as its measurement primitive. Create `runs/ar-qwen3` inside the git
repository that contains the editable target files; the contract may live in
infra-rsi. A direct shell run has the same shape:

```bash
python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py init \
  --run-dir runs/ar-qwen3 --target <editable-source-file> \
  --baseline-cmd "python -m irsi.cli measure --contract contracts/tiny-qwen3.generated.yaml \
    --artifacts-dir runs/ar-qwen3/measurements \
    --freeze-baseline runs/ar-qwen3/baseline.json --label baseline" \
  --benchmark-cmd "python -m irsi.cli measure --contract contracts/tiny-qwen3.generated.yaml \
    --artifacts-dir runs/ar-qwen3/measurements \
    --reference runs/ar-qwen3/baseline.json --label candidate" \
  --baseline-artifact baseline.json \
  --metric-pattern 'IRSI_MEASURE_METRIC=(?P<metric>[0-9.eE+-]+)' \
  --bench-must-match 'IRSI_MEASURE_GATE=pass' --noise-fraction 0.03
python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py \
  baseline --run-dir runs/ar-qwen3 --why "freeze the measured starting point"
```

The baseline step commits `run.json`, `manual.md`, the frozen `baseline.json`, the
append-only ledgers and the living docs in one traceable commit. The baseline
receipt also records SHA-256 fingerprints for those files plus the contract hash,
confirmation code, numeric hash and measured commit. After baseline, `iterate`
refuses to proceed if `run.json`, `manual.md` or the baseline evidence changed.
The contract YAML and its `.draft.json`/`.summary.md`/`.lock.json` sidecars must be
committed in the repository where they live.

Then the Agent edits one target file, writes the why/change description, and runs
`autoresearch.py iterate --run-dir ... --why ... --description ...`. The command
owns the gate, metric, failed-code restoration and one-step commit.

The original fixed-surface path remains available for deterministic regression:

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
`architecture-comparison-hp-pr1517.md`, `autoresearch-controller.md`; results in `phase1-result.md` and
`layerwise-recompute-result.md`. Older design notes are in `docs/archive/`.

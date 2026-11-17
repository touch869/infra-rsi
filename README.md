# infra-rsi

Closed-loop experiment harness for training-infra optimization (phase 1).

One command runs a task contract end to end: **environment → clean baseline → observation → observed baseline → hypotheses → execution → gates → judgment → ledger/report**, and produces a report with the measured gain. The first edit surface is activation recompute on HyperParallel; the harness itself is plugin-based so backends, gates and edit surfaces are added without touching the engine.

## Architecture

```
entry       cli.py (entry/ commands planned)
orchestration  Orchestrator / RoundController / ContextBuilder
plugins     contract/surfaces/ (which candidates a surface offers)
            execution/backends/ (how a trial runs)
            gates/ (receipt, bitwise, memory)
contract    contract/task_spec.py (what may change, how it is judged)
knowledge   knowledge/runtime/ (records.jsonl, ExperimentRecordStore, RuntimeKnowledgeReader)
            knowledge/skills/hp/ (skill packages)
prompting   prompting/ (StageContext, expert prompt specs, deterministic builder)
experts     experts/ (five role artifacts, prompt specs, registry)
execution   execution/stage.py (deterministic ExecutionStage) + execution/trial_executor.py
runtime     runtime/facade.py + runtime/neutrality.py + runtime/baseline_reference.py + runtime/observation_patch.py + runtime/native_prompt_runtime.py
git         git/commit_recorder.py (candidate commit + report, revert)
reporting   reporting/ (step/round reports + exporters/)
```

Dependency rule: `orchestration` and expert roles never import torch or HyperParallel; they talk to a `Backend` and `RuntimeFacade`. Gates never mutate a trial. Surfaces only emit contract-approved overrides, and the contract rejects any key outside `writable_prefixes`. Observation patches are applied by the runtime, not by an expert. Execution is deterministic: `TrialExecutor` runs, `ExecutionStage` only wraps `CandidateSpec`; it does not decide or control flow. The reference baseline is the **observed** baseline; the clean baseline is only a control for observation overhead.

## Quickstart (Ascend host)

```bash
pip install -e .
# model configs, base YAMLs and the dataset generator live in workspace/
cp -r workspace/. /root/irsi-workspace/
(cd /root/irsi-workspace && python make_data.py --out data/tiny-packed)
irsi run --contract contracts/medium-qwen3.yaml --runs-dir runs
irsi report runs/<task-dir>
```

`contracts/tiny-qwen3.yaml` is the 12-layer smoke contract; `medium-qwen3.yaml` is the 24-layer measurement contract. The latest evidence is exported under `results/medium-qwen3-20261112/` (**+20.63%** throughput vs baseline, **+15.78%** vs the no-op control, bitwise-identical numerics), and the write-up is `docs/phase1-result.md`.

The contract pins the repo, base YAML, writable key surface, metric, gates and budget. Every trial writes `train.yaml`, `run.log`, `metrics.json`; the task writes `results.tsv`, `candidates.jsonl`, `decisions/*.json`, `report.md`.

## Layerwise recompute (optional patch)

`patches/0001-qwen3-recompute-policy.patch` declares `ModelAdapterSpec.recompute` for Qwen3 dense, which unlocks per-layer recompute (`activation_checkpoint.selection.layer_count`). Apply it to the HyperParallel checkout, then run a layerwise contract:

```bash
git -C ../hyper-parallel am patches/0001-qwen3-recompute-policy.patch
irsi run --contract contracts/medium-qwen3-layerwise.yaml --runs-dir runs
```

The ladder comes from `domain_params.layer_counts`; three example budgets are shipped (24 GiB, 8 GiB, 6 GiB). Results: `docs/layerwise-recompute-result.md` and `results/layerwise-20261113/` (`layers-0` +34.29% vs the same-run baseline; `layers-6` +28.04% at 8 GiB; `layers-14` +9.39% at 6 GiB; all numerics bitwise identical). Note that installing the patch makes `mode=full` take the adapter-region wrapper path, which is ~7–13% slower than HF native checkpointing.

## Gates (phase 1)

| gate | checks |
|---|---|
| `receipt` | exit 0, no traceback, expected step count |
| `bitwise` | loss / grad_norm fingerprint identical to the observed baseline |
| `memory` | peak device memory within budget |

## Phase-1 knowledge skills

The core skill set is:

```text
hp/recompute-modes
hp/recompute-layerwise
hp/measurement
hp/memory-budget
hp/numeric-fingerprint
hp/engaged-evidence
```

`hp/mfu-perf` is optional. The packages live under `knowledge/skills/hp/`; `SkillCatalog` and `HPKnowledgeProvider` load them and `SkillResolver` selects them per stage. Process control, report schemas, contract validation and audit are code-enforced, not skills.

## Edit surfaces

`contract/surfaces/recompute.py` emits the recompute candidates (`off`, `control`, `selective`, `swap` variants) and the layerwise ladder (`recompute-layerwise`, driven by `domain_params.layer_counts`). A new surface (fusion, parallel, pipeline) is a new surface plugin plus a contract that declares its `writable_prefixes`. Observation is task-level: one `ObservationPlan` / `ObservationPatch` per task/round, shared by all candidates; surface-specific diagnostics go into a superset profile rather than a per-hypothesis patch.

## Tests

```bash
python -m pytest -q
```

Design docs live in `docs/`: `architecture-phase1-task-aligned.md`, `directory-plan.md`, `runtime-knowledge-design.md`, `architecture-comparison-inferrsi.md`, `architecture-comparison-hp-pr1517.md`; results in `phase1-result.md` and `layerwise-recompute-result.md`. Older design notes are in `docs/archive/`.

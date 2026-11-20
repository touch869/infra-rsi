---
name: autoresearch
description: >
  Bounded autonomous-experiment loop for kernel / graph optimization:
  benchmark + correctness gate + keep/discard/crash decision + append-only
  bookkeeping + one committed Why/Change/Result record per step, with the
  commit/restore protocol enforced in
  code rather than left to agent discipline. Use for automated experiments,
  performance optimization loops, iterative operator tuning, or any "measure a pending edit against the best
  recorded result and keep it only if it wins and the gate passes" workflow.
  The agent owns the creative half (pick an idea, make the edit); this skill
  owns the deterministic half.
category: "execution"
stages: ["S4"]
inputs:
  - "candidate source edit"
  - "benchmark command"
  - "correctness gate command"
  - "metric definition and budget"
outputs:
  - "append-only run ledger"
  - "results.tsv and candidates.jsonl"
  - "one step commit per baseline or candidate"
  - "report-only commits for discarded or crashed candidates"
next: ["mfu-riser"]
---

# Autoresearch

A bounded autonomous-experiment loop. One iteration = one optimization
experiment: edit the declared target file(s), pass the correctness gate,
benchmark the candidate, record the outcome, and keep / discard / crash.
The Agent drives iterations within the declared budget. Design follows torchtitan's `graph_trainer/autoresearch`,
promoting its deterministic protocol from prose into code.

**This file is the index + hard rules.** The per-run operating manual is
scaffolded into each run directory as `manual.md` (fill its `[SETUP]`).

The step-record fields and append-only rules follow the shared
[experiment-record](../../runtime/experiment-record/SKILL.md) contract. During `init`,
`ideas.md`, `results.tsv`, `experiment_log.md`, and `learnings.md` are generated
from that skill's templates.

## Controller model

This skill is the controller for a natural-language optimization objective. The
repository is deliberately not another controller: it only supplies a
deterministic one-trial measurement through `irsi measure`. The controller owns
baseline freezing, analysis, candidate selection, source edits, iteration,
record review, and the stop decision.

Start from the user's objective, not from a prebuilt candidate list:

1. Inspect the target repo/config, run `irsi contract draft`, show the summary,
   hash and confirmation code to the user, then **wait for explicit confirmation**
   before running `irsi contract confirm`. Never ask the user to author YAML.
2. Scaffold the run and fill `manual.md` `[SETUP]`: objective, confirmed contract,
   metric direction and noise, editable target files, protected files, correctness
   gates, workload identity, budget, and stop conditions.
3. Seed `ideas.md` with the user's intent and any already measured evidence.
4. Run `baseline` with `baseline_cmd`; it freezes the exact comparison reference.
5. Run the staged loop below. One iteration changes one candidate only.
6. Stop at the target, budget, or repeated no-improvement condition, then report
   baseline, best, measured gain, failed directions, evidence, and residual risk.

## Stage ownership and subagents

The main controller keeps the budget and makes the final keep/discard/stop
decision. Subagents are scoped workers, not additional controllers.

| Stage | Owner | Input | Required output | Boundary |
|---|---|---|---|---|
| Observe | analysis subagent | baseline logs, profiles, prior records, analysis skills | diagnosis with bottleneck, evidence paths, and contract-safe opportunities | No source edit, no candidate selection |
| Propose | strategy subagent | diagnosis, prior records, strategy skills | ranked candidate shortlist with `why`, expected effect, scope, and evidence | No source edit, no benchmark |
| Implement | implementer subagent | one accepted candidate and `manual.md` restrictions | one minimal edit in declared target files and a change summary | One candidate, target files only |
| Execute | deterministic controller | committed edit, `run.json`, gate/benchmark commands | gate, metric, `results.tsv`, `candidates.jsonl`, experiment-log entry, step commit | No agent-written result override |
| Judge | controller + engine record | gate and metric output | `keep`, `discard`, or `crash`; failure evidence retained | Failed source is restored by `iterate` |
| Reflect | controller | record, `ideas.md`, `learnings.md` | next candidate queue, retry entries, or stop reason | Only measured, reusable claims become learnings |

This replaces the earlier standalone expert orchestrator: ObservationExpert is
the Observe stage, DecisionExpert is Propose, DevelopmentExpert is Implement,
ExecutionExpert and JudgmentExpert collapse into deterministic Execute/Judge,
and ArchiveReportExpert is the engine-written record plus Reflect.

Handoffs are artifacts, not prose-only messages:

- diagnosis: bottleneck, evidence path, allowed change scope, and expected effect;
- candidate: id, `why`, target files/config keys, expected gate, and source skill;
- implementation: exact files changed, diff summary, and the single hypothesis it implements;
- measurement: the engine-written record and commit, never a subagent's claimed metric.

After the baseline, Observe and Propose may run in parallel. Implement is serial:
never let two subagents edit target files at once. Execute only after the
implementer has stopped. A subagent must receive `manual.md` restrictions and the
same gate/benchmark commands verbatim; the controller does not relax them for a
delegate.

## Harness measurement

For an infra-rsi contract, use `irsi measure` as the deterministic measurement
boundary. It runs the current committed source with the contract's base workload,
applies receipt and memory gates, emits a stable metric line, and writes
`measurement.json` plus the raw log. `baseline_cmd` freezes a numerical reference;
`benchmark_cmd` compares every later trial against it.

### Contract authoring and confirmation

The user supplies an objective, not a contract YAML. The Agent inspects the target
repository and base training config, then generates a draft:

```bash
python -m irsi.cli contract draft \
  --objective "<user objective>" \
  --base-config <training-config.yaml> \
  --repo-root <editable-repo> --out contracts/<task>.generated.yaml
python -m irsi.cli contract show --contract contracts/<task>.generated.yaml
```

`draft` writes the contract plus `<contract>.summary.md` and
`<contract>.draft.json`. Show the natural-language summary, semantic hash and
confirmation code to the user, then **stop and wait**. Only an explicit user
confirmation authorizes:

```bash
python -m irsi.cli contract confirm \
  --contract contracts/<task>.generated.yaml --code <shown-code> \
  --statement "<the user's confirmation in their own words>" --confirmed-by user
```

This writes `<contract>.lock.json`. The confirmation code is tied to the semantic
hash of the loaded contract, not YAML formatting or comments. Do not infer approval
from silence, paraphrase it as a default, or confirm before the user replies.

`irsi measure --freeze-baseline` and `--reference` require a confirmed, current
lock. Any change to workload, metric, gates, writable surface or read-only keys
invalidates the lock: regenerate, show the new summary, obtain confirmation, and
freeze a **new baseline**. Reusing the old baseline is forbidden.

If the contract lives in a different repository from the editable targets, commit
the contract YAML and its `.draft.json`/`.summary.md`/`.lock.json` sidecars in the
contract repository. The baseline evidence stores the contract hash and
confirmation code, so both repositories can be linked without copying the contract
into the run directory.

Create the autoresearch run directory **inside the git repository that contains
the editable target files**. The contract and knowledge skills may live in
infra-rsi, but `autoresearch` commits and restores paths relative to the target
repository, and `irsi measure` must measure that repository's current commit.

Minimal `run.json` shape:

```json
{
  "target_files": ["<editable source files>"],
  "baseline_cmd": ["python", "-m", "irsi.cli", "measure", "--contract", "contracts/tiny-qwen3.generated.yaml", "--artifacts-dir", "runs/ar/measurements", "--freeze-baseline", "runs/ar/baseline.json", "--label", "baseline"],
  "baseline_artifact": "baseline.json",
  "benchmark_cmd": ["python", "-m", "irsi.cli", "measure", "--contract", "contracts/tiny-qwen3.generated.yaml", "--artifacts-dir", "runs/ar/measurements", "--reference", "runs/ar/baseline.json", "--label", "candidate"],
  "metric_pattern": "IRSI_MEASURE_METRIC=(?P<metric>[0-9.eE+-]+)",
  "metric_lower_is_better": false,
  "noise_fraction": 0.03,
  "bench_must_match": ["IRSI_MEASURE_GATE=pass"]
}
```

The confirmed contract remains the frozen evaluation boundary for the base
workload, metric, gates, and allowed configuration keys. `target_files` is the
write boundary for source edits. Neither boundary may be widened to make a
candidate pass. Add a separate `gate_cmd` only when correctness needs evidence
that the single-trial measurement does not already enforce.

For the `irsi measure` flow, `baseline_artifact` must point to the same frozen
JSON as `--freeze-baseline`. `init` infers a run-relative path from that flag;
otherwise pass `--baseline-artifact <run-relative-path>`. The file must stay
inside the run directory. When configured, baseline verifies its schema,
`source_commit`, metric, `numeric_hash` and confirmed `contract_hash` before
recording it.

## Rules enforced in code

These come from real incidents, not agent memory:

1. **Benchmarks only measure committed code.** Remote benchmarks sync by
   commit; an uncommitted edit silently measures the previous state, so
   `iterate` commits the experiment first.
2. **Positive-evidence markers are required** (e.g. `engaged=1`). Their
   absence is a `crash`, never a quiet pass — a fallback run and an
   optimized run are indistinguishable by "no warning".
3. **A failed gate voids the metric**, however good it looks.
4. **Every step produces one reachable commit.** A kept step contains the
   measured code plus its Why/Change/Result documents. A `discard` or `crash`
   restores the target files and commits only the report documents.
5. **The baseline is the provenance boundary.** Its commit contains `run.json`,
   `manual.md`, the frozen baseline JSON and the ledger. `candidates.jsonl`
   records SHA-256 fingerprints for the config, manual and baseline evidence.
   After baseline, `iterate` rejects any modification to these protected files.

Two manual-level prohibitions protect blind runs (scaffolded into
`manual.md`). Use the current run's artifacts for prior experiments, and
consume the gate script through its assertion output.

## Subcommands

```bash
python irsi/knowledge/skills/execution/autoresearch/scripts/autoresearch.py <subcommand> [options]
```

| Intent | Command | Purpose |
|---|---|---|
| Initialize a run directory | `init --run-dir <d> --target <f> --benchmark-cmd "<c>" [--baseline-cmd "<c>" --baseline-artifact <f>]` | scaffold run.json + living docs and pin baseline evidence |
| Record a baseline | `baseline --run-dir <d>` | benchmark the current commit as the first keep |
| Evaluate a pending change | `iterate --run-dir <d> --why "<why>" --description "<what>"` | commit→gate→benchmark→decide→write docs→step commit |
| Inspect progress | `status --run-dir <d>` | summarize the run so far |

`iterate` expects the experimental edit to sit **uncommitted** in the run's
target files, with nothing else dirty outside the run directory.

## run.json contract

- `benchmark_cmd` / `gate_cmd`: **argv lists** (shell constructs live inside
  the invoked script, never in config).
- `baseline_cmd`: optional argv list used only by `baseline`; when absent,
  `baseline` reuses `benchmark_cmd`. Use it when the initial measurement must
  freeze a reference that later candidates compare against.
- `baseline_artifact`: optional run-relative frozen baseline JSON. It must match
  the `--freeze-baseline` path in `baseline_cmd`, stay inside the run directory,
  and is validated plus committed by `baseline`.
- `metric_pattern`: regex with a `(?P<metric>...)` group; the last match wins.
- `metric_lower_is_better`, `noise_fraction`: direction and the discard band.
- `noise_confirm_reruns` (default 0): when the first sample lands inside the
  noise band, rerun N times and decide on the median.
- `aux_patterns`: `{name: regex-with-(?P<value>...)}`; captured values ride
  along in the result row's description.
- `bench_must_match` / `gate_must_match`: literal markers; absence = crash.
- `training_protocol`: optional workload ID and full-window step counts.
  Use it with a separate `gate_cmd` and the
  [structured training receipt](../../strategy/perf-playbook/ascend/hyperparallel/references/training-rsi.md#structured-training-receipts).

## The experiment loop (agent side)

1. Read `status`, `ideas.md`, `learnings.md`, and `experiment_log.md`.
   Review the latest diagnosis and any `retry_ready` candidates before selecting
   an unrelated idea.
2. Edit the target file(s) — keep the tree dirty only there.
3. `iterate --run-dir <d> --why "..." --description "..."` - the tool owns the
   test, record, and step commit.
4. The tool appends the committed `experiment_log.md` entry. Update
   `ideas.md` / `learnings.md` as follow-up state for the next step.
Continue within the declared budget. Record which targets passed, which
remain open, and why the loop stopped.

## Candidate receipts and retries

Each `iterate` appends a step record to `candidates.jsonl` alongside the compact
metric history in `results.tsv`. The record stores:

- `why`: the hypothesis and expected improvement;
- `change`: the change summary, changed target files, and diff stat;
- `result`: decision stage, gate status, metric, detail, and auxiliary values;
- `commit`: the exact source commit that was measured.

`experiment_log.md` receives the same Why/Change/Result summary as a committed
Markdown entry. The engine, not a follow-up Agent edit, writes this record.
Training runs using the structured contract also record the baseline and every
gate or benchmark invocation, including failed noise-confirmation attempts.

- Tag changes with repeatable `--changes <scope>` flags. Use stable scope
  names within a run, such as `optimizer-residency` or `operator-path`.
- A candidate with `--revisit-on <scope>` becomes `retry_ready` when a later
  **kept** candidate changes that scope. Both `iterate` and `status` show
  eligible commits. Record the condition and the intended reapplication
  in the experiment log.
- Reapply the idea to the current kept configuration from the run's own
  notes or patch. Run it as a new candidate with `--retry-of <commit>` and
  the appropriate gate. This consumes that retry entry. A subsequent retry
  can declare its own trigger. Use the run's normal resource admission
  and budget for every retry.

For training runs, follow the [training RSI protocol](../../strategy/perf-playbook/ascend/hyperparallel/references/training-rsi.md).
Use [MFU Riser](../mfu-riser/ascend/hyperparallel/SKILL.md) when the task needs architecture FLOPs
audits, linked capacity series, or screening followed by performance acceptance.

## Hard rules (must not violate)

- Never edit `config.py` / `loop.py` (the engine) to make a run pass.
- Benchmarks and gates are argv lists — no `shell=True`, no inline pipes.
- A within-noise result is `discard`, not a forced keep.
- Never leave a failed candidate's source code in its step commit.
- Never merge two experiment steps into one commit.
- Keep the engine dependency-free (stdlib only) and pylint-clean.

## Field record

Two field runs drove the DeepSeek-V4.1 fused Lightning-Indexer adapter: the
first took a four-probe metric 697→123ms over three experiments; the second
(master baseline, six probes including long sequences) took 4617→261ms and
caught a wrong bf16-scoring optimization at the gate (crash, logged). Both
runs informed the fused-indexer integration. The original run artifacts were
stored in external `autoresearch/` and `autoresearch2/` directories; these
numbers are historical context, not benchmark results reproduced by this
checkout. The unit tests below exercise the experiment protocol locally.

## Unit tests

`tests/ut/tools/test_autoresearch_loop.py` drives baseline / keep / discard /
crash / dirty-tree / noise-confirm / aux-capture against a temporary git
repository (CPU, no accelerator). It puts the engine directory on `sys.path`
the same way the entry script does.

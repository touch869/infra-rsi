# Autoresearch operating manual

This manual guides the Agent. In each iteration, implement one candidate within the
declared target files, run the gate and benchmark, and record `keep`, `discard`, or
`crash`. Continue within the run's budget.

## [SETUP] Run configuration

- **Optimization objective:** <FILL: what to optimize>
- **Contract and baseline command:** <FILL: contract path, `baseline_cmd`, run-relative `baseline_artifact`, and frozen reference path>
- **Primary metric:** <FILL: benchmark_cmd output field and optimization direction>
- **Starting point:** <FILL: current implementation and known performance>
- **Scaffolding level:** <FILL: readable references and access to the network or history>
- **Budget and stopping conditions:** <FILL: time or trial count, improvement over baseline, and independent performance target if applicable>
- **Measurement windows:** <FILL: correctness and performance windows, topology, probes, routing, and metric convention>
- **Change classes and gates:** <FILL: evidence for equivalent implementations, numerical tolerances, or training-policy changes>
- **Retry tags:** <FILL: stable configuration scopes used in this run, such as optimizer-residency>

## Editable files

Use `target_files` in this directory's `run.json`. The tool refuses to benchmark
uncommitted changes outside that list.

**Do not modify:** <FILL: reference implementation, gate scripts, trainer, or other
protected files whose changes would alter the evaluation>.
Analysis tools may be added under this run directory's `scripts/`.

## Read scope

**May read:** <FILL: target files, read-only reference implementation, current run files, and self-generated profiles>
**Do not read:** <FILL: unrelated subsystems; record a reason in experiment_log before expanding scope>

## History and gate-source restrictions

These requirements cannot be relaxed by `[SETUP]`.

- **Do not inspect Git history.** `git log`, `git log -p`, `git show <commit>`,
  `git diff <commit>`, and `git blame` are prohibited. Prior commit titles and diffstats
  can reveal optimizations that this run is intended to rediscover independently.
  Working-tree `git status` and `git diff` without commit references are allowed.
  Read this run's commits and failure evidence from `results.tsv`, `candidates.jsonl`,
  and its own experiment logs.
- **Do not read gate-script source.** Execute the gate and use assertion messages
  in its output to diagnose failures. Symbols in gate source can reveal previous
  optimization choices.
- Treat material with uncertain read authorization as out of scope.

## Benchmark and correctness gate

`run.json` defines `benchmark_cmd` and `gate_cmd`. Missing positive markers from
`bench_must_match` or `gate_must_match`, such as `engaged=1`, result in `crash`.
Absence of warnings does not establish that an optimization executed. For a first
measurement inside the noise band, configured automatic repeats use the median before
deciding (`noise_confirm_reruns`). Do not override this with a single reading.

Before the first baseline, `irsi contract show --contract <path>` must report
`status: confirmed`. The Agent must generate the draft and explain it to the user,
but only the user's explicit confirmation may authorize `irsi contract confirm`.
Never edit a confirmed contract or confirm a changed hash; regenerate, re-review,
re-confirm, and freeze a new baseline instead.

The baseline step validates the frozen JSON, records SHA-256 fingerprints for
`run.json`, this manual and the baseline evidence, and commits them with the
append-only ledger. After baseline, these protected files must not change.

## Records

The tool appends `results.tsv`, `candidates.jsonl`, and `experiment_log.md` and
creates one step commit. A kept step contains code plus documents. A failed step
contains only its report; the target files are restored. Update `ideas.md` and
`learnings.md` as follow-up state for the next step. The baseline commit includes
`run.json`, `manual.md`, the frozen baseline JSON and all ledger files; a later
candidate may change only the declared targets and living documents.

## Experiment loop

Within the declared budget:

1. Run `status`, check `retry_ready` candidates first, then choose the next experiment
   using `ideas.md`, `learnings.md`, and `experiment_log.md`.
2. Implement the change in `target_files`, leaving only those files modified. When
   context is limited, implementation and execution may be delegated to a subagent.
   Pass this manual's restrictions and commands verbatim; the main loop receives the
   result rather than rewriting the rules for the delegate.
3. Run `autoresearch.py iterate --run-dir <this-directory> --why "<expected improvement>"
   --description "<what changed>"` to create the measurement commit, test it, write the
   record, and create the final step commit. Use `--changes` for changed scopes and
   `--revisit-on` for dependency scopes. For a retry, reapply the change to the current
   best configuration and pass `--retry-of <commit>`.
4. Update ideas and learnings for the next step. Do not append a second experiment-log
   entry by hand; the engine already committed one Why/Change/Result entry.

## Stage handoffs

The main controller owns the budget and final decision. Delegate only bounded
stages, and require an artifact at each handoff:

- **Observe:** return a diagnosis with bottleneck, evidence paths, and allowed
  change scope. Do not edit source or choose a winner.
- **Propose:** return a ranked candidate shortlist with `why`, target files,
  expected gate, and evidence. Do not benchmark.
- **Implement:** apply exactly one accepted candidate in `target_files`, then stop
  and return the change summary. No two delegates may edit targets concurrently.
- **Execute/Judge:** only `iterate` and its engine record decide keep/discard/crash.
  Do not let a delegate report a metric outside those records.
- **Reflect:** the main controller updates `ideas.md` and `learnings.md`, then
  chooses the next stage or records the stop reason.

Pass this manual's restrictions and commands verbatim to every delegate.

**Crash:** Identify the first failing stage and distinguish training, validation, and
resource failures. Record the fix, retry conditions, and evidence paths.

**Stop:** Record whether the target was met, the remaining gap, and the stopping reason.

## Environment requirements

- <FILL: occupancy checks and resource-sharing rules; do not interfere with other jobs; release resources after completion>
- <FILL: known environment constraints, such as timeouts, caches, and concurrent compilation>

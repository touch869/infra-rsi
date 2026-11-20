# infra-rsi Agent routing

When the user asks to improve performance, throughput, memory, numerical
precision, MoE behavior, parallel strategy, or training efficiency, use
`irsi/knowledge/skills/execution/autoresearch/SKILL.md` as the controller.

Do not hand the user a manual `prepare` / edit / `execute` procedure. The user
states the objective in natural language; you create and drive the experiment:

1. Read `docs/autoresearch-controller.md` and the full `autoresearch` skill.
2. Inspect the target repository and training config, then generate a contract with
   `irsi contract draft`. Show its natural-language summary, hash and confirmation
   code to the user. **Stop and wait for an explicit user confirmation**; do not
   confirm on the user's behalf and do not ask the user to edit YAML.
3. Only after the user confirms, run `irsi contract confirm` with their natural-
   language statement and the displayed code. Then scaffold a run with
   `autoresearch.py init` with the same `--freeze-baseline` path pinned through
   `--baseline-artifact`, fill `manual.md` `[SETUP]`, seed `ideas.md`, and run
   `baseline` with `irsi measure --freeze-baseline`.
4. Delegate bounded Observe / Propose / Implement work as described by the skill.
5. Use `autoresearch.py iterate` as the only gate, benchmark, decision and commit
   authority. One candidate produces one step commit.
6. Read `status`, `results.tsv`, `candidates.jsonl`, and `learnings.md` before the
   next step. Stop on the target, budget, or repeated no-improvement condition.

Hard constraints:

- Keep the contract's workload, metric, gates and read-only keys frozen. A confirmed
  contract is protected by a hash lock; any semantic change requires regenerating
  the draft, re-confirming with the user, and freezing a new baseline.
- Treat the baseline commit as the provenance boundary: it must contain `run.json`,
  `manual.md`, the frozen baseline JSON and the append-only ledger. After baseline,
  never edit these files; the next run must start a new run directory and baseline.
- Commit the contract YAML and its `.draft.json`/`.summary.md`/`.lock.json` sidecars
  in the repository where they live. Baseline evidence links that commit through
  the contract hash and confirmation code.
- Edit only the run's declared `target_files`; one candidate at a time.
- Preserve discarded and crashed experiments as report-only commits; restore their
   source before committing.
- Never claim a gain that is absent from the autoresearch records.
- Do not commit outside the protocol or modify the controller to make a result pass.

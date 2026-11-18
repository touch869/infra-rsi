---
name: experiment-record
version: 1
description: >
  Define and maintain the append-only contract for recording why each experiment
  step was attempted, what changed, what the test reported, and how the step was
  committed or rolled back. Use when a workflow initializes a result ledger, writes
  one step record, validates completeness, or produces a reproducible report.
category: "shared"
---

# Experiment Record

This skill defines the evidence contract for one experiment step. It records
what was attempted, what changed, what the test proved, and whether the code was
retained or restored. It does not run benchmarks, choose candidates, or execute
Git commands.

## Contract sources

Use one file as the source of truth for each concern:

- record shape: [schemas/experiment-record.schema.json](schemas/experiment-record.schema.json)
- field meanings: [references/field-dictionary.md](references/field-dictionary.md)
- states and commit disposition: [references/status-values.md](references/status-values.md)
- invariants and commit contract: [references/record-contract.md](references/record-contract.md)
- human log layout: [templates/experiment_log.md](templates/experiment_log.md)
- idea backlog: [templates/ideas.md](templates/ideas.md)
- reusable findings: [templates/learnings.md](templates/learnings.md)

Every machine-readable record uses the `experiment-record/v1` envelope. Every
step must answer three questions:

1. **Why:** the problem, hypothesis, or expected effect.
2. **What changed:** files, symbols, configuration keys, and semantic diff.
3. **Test result:** gate status, first failure, metric and delta, or the exact
   reason the test did not complete.

The record also carries commit and rollback accounting. Failed, crashed, and
discarded steps stay in history.

## Step commit policy

1. One record represents one step and produces exactly one Git commit.
2. The commit message contains `Experiment-Record: <record_id>` so the step can
   be found with `git log --grep`.
3. A kept or accepted step commits retained source plus the record, experiment
   log, result row, and evidence.
4. A failed, crashed, or discarded step restores tracked source before committing.
   The commit contains only the report, record, ledger updates, evidence, and rollback
   proof; failed source must not remain in the branch or working tree.
5. Set `code_restored=true` only when the source restoration is complete. A kept
   step sets it to `false`.
6. Git execution belongs to the calling workflow. `TaskLedger` records the declared
   commit reference and disposition; it does not create or revert commits itself.

## Append-only rules

1. Never rewrite a completed record; corrections are new records that reference
   the record they supersede.
2. A failed or skipped gate voids performance metrics.
3. Every record identifies source revision, workload identity, and its parent record.
4. Every claim points to a readable evidence path with a content hash.
5. A missing field is not evidence. Explain permitted unknowns in `notes`.

## Runtime integration

`irsi run` invokes `Engine`, which writes through `TaskLedger` under the task
directory:

| Artifact | Role |
|---|---|
| `results.tsv` | Compact append-only step summary, including the commit reference |
| `candidates.jsonl` | Canonical compact decision receipts |
| `decisions/<trial>.json` | One decision receipt per candidate |
| `experiment_log.md` | Human-readable why/change/test/commit narrative |
| `ideas.md` | Agent-maintained backlog of proposed, not yet measured ideas |
| `learnings.md` | Agent-maintained conclusions reused across steps |
| `events.jsonl` | Append-only controller event history |
| `baseline.json` | Frozen baseline measurement and gate results |
| `trials/<trial>/` | Raw log, rendered config, and metrics |
| `report.json`, `report.md` | Derived run report; never the sole evidence |

The JSONL/TSV files are runtime receipts. The `experiment-record/v1` schema is the
canonical envelope for a complete step record; an agent or controller converting
receipts into a formal record must validate against it.

`ideas.md` and `learnings.md` are not written by `TaskLedger`. The calling Agent
or controller maintains them: record new proposals in `ideas.md`, and promote
only evidence-backed, reusable conclusions to `learnings.md`.

## Loading

The skill is auto-discovered from its `SKILL.md` frontmatter by
`irsi.knowledge.skill_catalog` and is available through `irsi skills`.

## Hard rules

- Do not omit failed steps or failed evidence.
- Do not record a metric that the gate did not validate.
- Do not split one step across multiple commits.
- Do not claim a rollback or commit reference that was not produced.
- Do not use this skill to execute experiments or choose the winning candidate.

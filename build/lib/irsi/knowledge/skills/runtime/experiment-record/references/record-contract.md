# Experiment Record Contract

## Invariants

- One record covers one baseline, candidate, confirmation, or recovery step.
- A candidate or confirmation has an explicit parent record.
- Completed records are append-only. Corrections reference the record they supersede.
- Failed, crashed, discarded, and invalid attempts remain in history.
- Every record identifies its source revision, workload identity, and measurement
  convention.
- Every claim points to re-readable evidence with a content hash.
- A missing field is not evidence. Permitted unknowns are explained in `notes`.

## Required step content

Every record answers:

- why the step was attempted;
- what changed, including files, symbols, configuration keys, and semantic diff;
- what the test or gate reported, including the first failure or noncompletion
  reason.

The canonical field definitions are in [field-dictionary.md](field-dictionary.md).
The machine-readable schema is
[../schemas/experiment-record.schema.json](../schemas/experiment-record.schema.json).

## Commit contract

Each step produces one Git commit containing its canonical record, experiment log
entry, result ledger row, and evidence references. Put
`Experiment-Record: <record_id>` in the commit message so it can be resolved with
`git log --grep`.

- **Kept or accepted:** commit retained source and documentation together.
- **Failed, crashed, or discarded:** restore tracked source to the retained parent
  first, then commit only the report, record, ledger updates, evidence, and rollback
  proof.
- **Clean state:** failed source must not remain in the branch or working tree.

`code_restored` records whether restoration completed. `rollback_ref` identifies
the restored revision or record. Commit and restore commands belong to the calling
workflow, not to this skill.

## Extensions

Workflow-specific data belongs under the top-level `extensions` namespace. An
extension cannot redefine common fields, status values, metrics, or the step
fields above.

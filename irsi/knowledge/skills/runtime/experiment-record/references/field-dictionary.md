# Field Dictionary

| Field | Required | Meaning |
|---|---|---|
| `schema` | yes | Fixed value `experiment-record/v1` |
| `record_id` | yes | Unique identifier within the experiment |
| `record_type` | yes | `baseline`, `candidate`, `confirmation`, or `recovery` |
| `workflow` | yes | Producing workflow name |
| `experiment_id` | yes | Stable identifier for the overall search or run |
| `parent_id` | baseline only may be null | Record from which this attempt started |
| `created_at` | yes | ISO 8601 timestamp with timezone |
| `source.revision` | yes | Commit, source archive, or complete source digest |
| `source.digest` | yes | Hash of the measured source snapshot |
| `source.dirty` | yes | Whether uncommitted source was present |
| `workload.id` | yes | Stable workload name |
| `workload.hash` | yes | Hash of resolved inputs and measurement configuration |
| `gate.status` | yes | `PASS`, `FAIL`, or `SKIP` |
| `gate.first_failure` | no | First failed check when the gate did not pass |
| `gate.evidence` | yes | Raw gate output paths |
| `metrics` | measured records | Primary and secondary numeric results; `null` on failed or skipped gates |
| `decision.value` | yes | State from [status-values.md](status-values.md) |
| `decision.reason` | yes | Short reason tied to evidence |
| `evidence` | yes | Artifact paths with SHA-256 hashes |
| `step.why` | yes | Why the step was attempted and the expected effect |
| `step.changes` | yes | Files, symbols, configuration keys, or semantic changes |
| `step.test_result` | yes | Gate/benchmark result or the exact reason it did not complete |
| `step.commit.commit_ref` | yes | Commit hash or stable `Experiment-Record: <record_id>` trailer |
| `step.commit.docs_included` | yes | Must be `true`; the step commit contains its documentation |
| `step.commit.code_restored` | yes | Whether failed source was restored; `false` for kept steps |
| `step.commit.rollback_ref` | restored steps | Revision or record restored before the failure commit |
| `notes` | no | Explanation of limitations or permitted missing evidence |
| `extensions` | no | Workflow-specific fields under a workflow namespace |

## Validation rules

- A failed or skipped gate requires `metrics` to be absent or `null`.
- `keep` or `accepted` requires a passing gate and a primary metric.
- Every evidence path resolves relative to the run directory and its SHA-256
  describes the referenced bytes.
- `keep` and `accepted` use `code_restored=false`; restored steps supply
  `rollback_ref`. See [status-values.md](status-values.md) for the full mapping.
- `notes` may explain a limitation but cannot replace a required field.

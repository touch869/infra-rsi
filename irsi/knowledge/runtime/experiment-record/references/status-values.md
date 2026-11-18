# Status Values

## Record types

| Type | Meaning |
|---|---|
| `baseline` | First retained measurement for a workload series |
| `candidate` | Attempt derived from a retained parent |
| `confirmation` | Independent replay of a retained or accepted candidate |
| `recovery` | Interrupted trial and its cleanup state |

## Gate states

| State | Meaning |
|---|---|
| `PASS` | Required correctness, identity, and engagement checks passed |
| `FAIL` | At least one required check failed |
| `SKIP` | The check was not run; this is not a pass |

A failed or skipped gate voids performance metrics.

## Decisions

| Decision | Meaning |
|---|---|
| `keep` | Gate passed and the result beat the comparison rule |
| `discard` | Candidate was not retained; code is restored |
| `crash` | Execution failed before a valid comparison; code is restored |
| `pending` | Work is incomplete and must be resumed or recovered |
| `accepted` | Acceptance criteria passed; code is retained |
| `rejected` | Acceptance criteria did not pass; code is restored |
| `invalid` | Record is incomplete or inconsistent; code is restored |

`infra-rsi` currently emits `keep`, `discard`, and `crash` from `Engine`. The other
states are available to external controllers.

## Commit disposition

| Decision | `code_restored` | Commit contents |
|---|---|---|
| `keep` | `false` | Retained code plus record, log, ledger, and evidence |
| `accepted` | `false` | Accepted code plus record, log, ledger, and evidence |
| `discard` | `true` | Report, rollback proof, and evidence only |
| `crash` | `true` | Failure report, rollback proof, and evidence only |
| `rejected` | `true` | Rejection report, rollback proof, and evidence only |
| `invalid` | `true` | Invalidation report, rollback proof, and evidence only |

`pending` may be written before the commit exists, but is not complete until the
step commit contains its narrative and evidence.

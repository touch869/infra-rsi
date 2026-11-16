# Autoresearch experiment log

Append one entry per experiment. Never rewrite previous entries. Read the log at the
start of each iteration to avoid repeating failed approaches.

## Entry format

```markdown
## <Short title> — <status> (<commit>)

- **Hypothesis:** What was tried and why it was expected to help.
- **Change:** What was modified; summarize rather than pasting the full diff.
- **Engagement and gate:** Executed path, evidence location, and gate result. On failure, record the first failing stage and assertion.
- **Result:** Primary metric, measurement convention, and breakdown, or reason for noncompletion.
- **Analysis:** Why it helped, had no effect, or failed.
- **Lesson:** What to retain or avoid in future iterations.
- **Retry conditions:** Configuration changes that justify retrying, and how to reapply the candidate to the current best version.
```

---

(Empty. Seeded by the experiment owner or populated by the Agent.)

## Reproduction run 2026-11-16 (8x910B4, medium-qwen3, PR #1517 engine)

| exp | exec_config | decision | metric (tps) | evidence |
|---|---|---|---|---|
| baseline | full | keep | 23130 | gate froze fingerprint; peak_mem 4.007GB |
| C1 | off | keep | 26955 (+16.6%) | fingerprint bitwise-identical; engaged_mode=off; peak_mem 9.058GB |
| C2 | selective | discard | 14262 (-47% vs best) | fingerprint identical; slow as known negative |
| C3 | off + inject silent_fallback | crash (gate: path_not_engaged) | none | resolved dump stayed full; engagement evidence correctly vetoed |
| C4 | off + inject numerical_corruption | crash (gate: numerical_mismatch, first_error_step=2) | none | engaged=true but fingerprint diverged at step 2; metric voided |
| C5 | off (no-op) | discard | 23703 (-12.1%, outside band) | no noise-confirm rerun: clear regression skips reruns by design |

Two earlier scaffolding crashes (invalid_training_receipt, path_not_engaged) are kept
in history per rule 4; they motivated making workload_id HEAD-independent and fixing
the pretty-printed config-dump regex.

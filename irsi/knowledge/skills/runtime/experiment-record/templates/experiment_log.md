# Experiment log

Append one entry per experiment step. Never rewrite previous entries.

## Entry format

```markdown
## <trial> - <decision> (<record_id>)

- **Experiment identity:** trial `<trial>`, record `<record_id>`.
- **Why:** The problem addressed and the expected effect.
- **What changed:**
  - `path/to/file.py`: semantic summary of the change.
- **Test result:** Gate status, first failure, metric and delta, or the reason the test did not complete.
- **Commit:** `<commit hash or Experiment-Record trailer>`; docs included; code restored: `<true|false>`; rollback: `<revision or not applicable>`.
- **Evidence:**
  - log: `path/to/run.log`
```

---

(Empty. Appended by the experiment controller.)

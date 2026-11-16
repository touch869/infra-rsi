# Autoresearch accumulated findings

The Agent maintains findings across experiments. Read this file at each iteration and
update it after unexpected positive or negative results. Put individual experiment
details in `experiment_log.md`; retain actionable conclusions here. Seed findings
originate from measured manual experiments on 2026-09-23/24.

## Methodology

Record the triggering symptom, runtime and tensor shapes, change mechanism,
correctness and engagement evidence, end-to-end result, applicability limits,
and conditions that would justify a retry. Link the experiment and raw evidence.

- Run-to-run tps variance on this host reaches ~12% (C1 26955 vs C5 23703, identical
  config), so a 5% noise band is tight; PR noise_confirm_reruns only fires inside the
  band - clear regressions skip confirmation entirely.
- The resolved-config dump is the strongest engagement evidence; the memory-band check
  is a good second factor (full 4.0GB / off 9.1GB / selective 4.9GB).
- First-error-step localizes a numerical fault to the first optimizer update after the
  corrupted clip takes effect (step 2, not step 1).

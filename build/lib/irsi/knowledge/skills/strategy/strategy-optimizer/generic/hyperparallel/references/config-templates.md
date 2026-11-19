# Training configuration contract

Use the shared [strategy-validator configuration reference](../../../../../validation/strategy-validator/generic/hyperparallel/references/config-templates.md).
The optimizer's `--config-template` must be a complete runnable Trainer YAML.
The official PSA writer resolves searched batch/recompute settings before the optimizer patches degree fields.
Neighborhood candidates preserve other template settings; an incompatible batch configuration is a failed
benchmark and cannot be exported as the measured winner.

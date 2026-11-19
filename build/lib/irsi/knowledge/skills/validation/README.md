# Validation skills

This directory holds skills that turn hypotheses and candidate configurations
into explicit pass/fail decisions. Each variant contains its own `SKILL.md`; use
`environment` and `framework` frontmatter to select the matching rules.

Current layout:

```text
validation/
  bringup-benchmark/
    generic/hyperparallel/       # bring-up asset checks, trials and A/B verdicts
  formal-verification/
    generic/hyperparallel/       # FM-Agent contracts and counterexamples
  hf-model-precision-validation/
    ascend/hyperparallel/        # numerical acceptance and precision diagnosis
  routing-validator/
    generic/generic/             # MoE routing correctness checks
  strategy-validator/
    generic/hyperparallel/       # measured parallel-strategy validation
```

`analysis/` produces evidence, `strategy/` proposes candidates or tuning
changes, and `validation/` decides whether a change passes correctness,
performance, or formal-verification gates. Validation skills report evidence;
they do not silently convert a failed or inconclusive measurement into a pass.

`irsi.knowledge.skill_catalog` discovers every `SKILL.md` below this directory
automatically. Add a sibling hardware or framework variant when a new
environment needs different commands or acceptance rules.

# Execution skills

This directory holds skills that run experiments, orchestrate trials, and
maintain the evidence needed to keep, discard, or revert a candidate. They
consume outputs from `analysis/`, `strategy/`, and `validation/`; they do not
replace those decision layers.

Current layout:

```text
execution/
  autoresearch/              # hardware/framework-agnostic experiment loop
  mfu-riser/
    ascend/
      hyperparallel/         # Ascend + HyperParallel MFU optimization controller
```

`autoresearch` owns the generic benchmark → gate → decision → record → commit
loop. `mfu-riser` adds MFU-specific contracts, profiling evidence, linked
capacity series, and Ascend/HyperParallel acceptance rules.

Each skill contains its own `SKILL.md`. `irsi.knowledge.skill_catalog`
discovers every `SKILL.md` automatically; add an environment variant only when
the hardware or framework needs different execution rules.

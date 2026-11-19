# Strategy skills

This directory holds skills that turn analysis evidence into candidate
strategies, tuning choices, and launchable plans. Keep environment-specific
rules in a variant directory so hardware and framework assumptions stay visible.

Current layout:

```text
strategy/
  moe-optimizer/
    generic/
      hyperparallel/  # MoE diagnosis, candidate generation and refinement loop
  strategy-optimizer/
    generic/
      hyperparallel/  # Bounded parallel-layout search and measured selection
  perf-playbook/
    ascend/
      hyperparallel/  # Bottleneck-to-technique playbook and tuning report
  parallel-strategy-planner/
    generic/
      hyperparallel/  # DP/TP/PP/EP/CP planners with DeviceMesh output
  sapp-parallel-strategy/
    ascend/
      hyperparallel/  # Ascend A3 layout pricing with HyperParallel's ND model
```

`analysis/` produces the evidence (profiles, memory breakdowns, MoE facts and
precision divergence). `strategy/` turns that evidence into proposals and
closed-loop searches: which technique to try, which parallel layout to launch,
or which candidates to compare. Validation lives under `../validation/` and
decides whether a proposed change passes correctness and performance gates.

Each variant contains its own `SKILL.md`. `irsi.knowledge.skill_catalog`
discovers every `SKILL.md` automatically; use `category`, `environment`, and
`framework` frontmatter to route the right variant.

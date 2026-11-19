# Analysis skills

This directory holds diagnostic and profiling skills. Keep environment-specific
implementations in subdirectories so incompatible hardware or framework rules do
not overwrite each other.

Current layout:

```text
analysis/
  profiling/
    ascend/
      hyperparallel/  # Ascend NPU + torch_npu/CANN + HyperParallel
  moe-profiler/
    ascend/
      hyperparallel/  # MoE expert/load/routing facts on HyperParallel
  memory-analysis/
    ascend/
      generic/  # Ascend NPU allocation and snapshot analysis, any framework
  precision/
    ascend/
      generic/  # msprobe capture, candidate/reference diff, first-divergence triage
```

Each variant contains its own `SKILL.md` and the resources it needs.
`irsi.knowledge.skill_catalog` discovers every `SKILL.md` automatically; use
frontmatter such as `category`, `environment`, and `framework` to route variants.
Each skill owns its capability directory; `ascend/<framework>/` is the variant
axis. Add another framework or hardware directory when a new environment needs
different rules, rather than nesting one skill under another.

Strategy planning and tuning skills live under `../strategy/`. This directory
stays focused on producing evidence: profiles, memory breakdowns, MoE facts, and
precision divergence.

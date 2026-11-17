# infra-rsi 目录规划（第一阶段）

日期：2026-11-16  
原则：按“组件包”组织，不按抽象层名组织；专家目录放角色与 prompt 规范，`prompting/` 放通用拼装，`runtime/` 放确定性工具与专家运行时。

## 1. 目录树

```text
infra-rsi/
├── irsi/
│   ├── __init__.py
│   ├── cli.py                     # 顶层 CLI 入口
│   ├── registry.py                # typed registry
│   ├── core/
│   │   ├── __init__.py
│   │   └── protocols.py           # Gate / TrialExecutor / KnowledgeProvider / Exporter
│   │
│   ├── entry/
│   │   ├── __init__.py
│   │   ├── commands.py            # run/status/report 命令分发
│   │   └── openjiuwen_entry.py    # prompt 触发 / 产物 RSI 入口
│   │
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── orchestrator.py        # 选阶段、选专家、handoff
│   │   ├── round_controller.py    # 下一轮、baseline、停止条件
│   │   └── context_builder.py     # 组装 StageContext
│   │
│   ├── prompting/
│   │   ├── __init__.py
│   │   ├── context.py             # StageContext
│   │   ├── spec.py                # ExpertPromptSpec / SkillView / RenderedPrompt
│   │   ├── builder.py             # 通用 prompt 拼装
│   │   └── registry.py            # role/stage → prompt spec
│   │
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── skills.py              # Skill / SkillManifest
│   │   ├── catalog.py             # SkillCatalog
│   │   ├── reader.py              # SkillResolver / read-only search
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # KnowledgeProvider
│   │   │   └── hyperparallel.py   # HP skill provider
│   │   └── runtime/
│   │       ├── __init__.py
│   │       ├── experiment_record.py   # ExperimentRecord
│   │       ├── record_store.py        # ExperimentRecordStore
│   │       └── ledger_store.py        # append-only runtime evidence
│   │
│   ├── contract/
│   │   ├── __init__.py
│   │   ├── task_spec.py           # TaskSpec
│   │   ├── candidate_generator.py
│   │   ├── validation.py          # NumericPrecisionGate / ValidationPolicy
│   │   └── surfaces/
│   │       ├── __init__.py
│   │       ├── base.py            # SurfacePlugin
│   │       └── recompute.py       # HP recompute surface
│   │
│   ├── gates/
│   │   ├── __init__.py
│   │   ├── base.py                # Gate protocol
│   │   └── builtin.py             # receipt / bitwise / memory
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── metric_extractor.py    # log -> metrics
│   │   ├── perf_observer.py
│   │   ├── snapshot.py
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── base.py            # TrialExecutor protocol
│   │       └── hyperparallel.py   # HP adapter
│   │
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── facade.py              # 确定性运行时工具
│   │   ├── calibration.py         # clean / observed baseline 校准
│   │   ├── expert_runtime.py      # ExpertRuntime protocol
│   │   ├── native_prompt_runtime.py
│   │   └── openjiuwen_runtime.py  # OpenJiuwen adapter
│   │
│   ├── experts/
│   │   ├── __init__.py
│   │   ├── base.py                # ExpertRole / ExpertResult
│   │   ├── artifacts.py           # HypothesisSet / CandidateSpec / Judgment / ...
│   │   ├── registry.py
│   │   ├── decision/
│   │   │   ├── __init__.py
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── development/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── observation/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── execution/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── judgment/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   └── archive_report/
│   │       ├── expert.py
│   │       └── prompt_spec.py
│   │
│   ├── audit/
│   │   ├── __init__.py
│   │   ├── hitt.py                # HITT 成果审计
│   │   ├── knowledge_audit.py
│   │   └── audit_record.py
│   │
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── step_report.py
│   │   ├── round_report.py
│   │   ├── report_builder.py
│   │   └── exporters/
│   │       ├── __init__.py
│   │       ├── json_exporter.py
│   │       ├── markdown_exporter.py
│   │       └── csv_exporter.py
│
├── knowledge/
│   ├── skills/
│   │   └── hp/
│   │       ├── recompute-layerwise/
│   │       │   ├── SKILL.md
│   │       │   └── skill.yaml
│   │       ├── mfu-perf/
│   │       └── memory-budget/
│   └── runtime/
│       └── cases.jsonl           # 审计后晋升的正例/反例
│
├── contracts/
├── workspace/
├── patches/
├── results/
│   └── <round-id>/
│       ├── baseline.json
│       ├── report.json
│       ├── report.md
│       ├── results.tsv
│       ├── candidates.jsonl
│       └── records.jsonl
├── runs/
│   └── <round-id>/
│       ├── baseline/
│       ├── candidates/
│       └── logs/
├── tests/
│   ├── unit/
│   │   ├── test_task_spec.py
│   │   ├── test_recompute_surface.py
│   │   ├── test_numeric_precision.py
│   │   ├── test_experiment_record.py
│   │   ├── test_expert_roles.py
│   │   └── test_hitt.py
│   └── integration/
│       ├── test_phase1_loop.py
│       └── test_cli_round.py
│
├── docs/
└── pyproject.toml
```

## 2. 每个目录的职责

| 目录 | 职责 |
|---|---|
| `entry/` | CLI 命令、OpenJiuwen prompt 入口 |
| `orchestration/` | 流程编排、round 控制、StageContext |
| `prompting/` | 阶段 prompt 规范与通用拼装 |
| `knowledge/` | skill catalog、HP provider、runtime records、ledger |
| `contract/` | TaskSpec、修改面插件、数值精度验证 |
| `gates/` | 通用 gate 与其 registry |
| `execution/` | 执行器、观察器、指标抽取、快照 |
| `runtime/` | 确定性 runtime facade、专家运行时 adapter |
| `experts/` | 六个专家角色、各自 prompt spec、统一 artifact 类型 |
| `audit/` | HITT 成果审计、知识审计 |
| `reporting/` | 每步报告、round 报告、`exporters/` 导出插件 |

## 3. prompt 拼装位置

- **专家目录**：`experts/*/prompt_spec.py`，定义角色、目标、输入、允许工具、输出 schema。
- **上下文类型**：`prompting/context.py`，定义 `StageContext`，只带当前 stage 需要的切片。
- **通用拼装**：`prompting/builder.py`，把 `ExpertPromptSpec + StageContext + selected skills` 按固定段在前、变化段在后渲染成 prompt。
- **上下文组装**：`orchestration/context_builder.py`，从 task、skills、records、constraints 组装 `StageContext`。
- **确定性工具**：`runtime/facade.py`，提供 `validate_surface`、`execute_trial`、`run_gates`、`commit` 等。

## 4. 调用链

```text
Orchestrator
  → ExpertRegistry.get(stage)
  → ContextBuilder.build(stage, task, skills, records)
  → PromptBuilder.render(prompt_spec, context)
  → ExpertRuntime.run(expert, prompt, runtime_facade)
  → Artifact
  → Ledger / Report / KnowledgeStore
```

## 5. 清理前路径 → 当前路径

> 下表是清理前的路径，当前代码已按右列路径落位；不是当前目录结构。

| 清理前 | 当前 |
|---|---|
| `irsi/engine.py` | `orchestration/orchestrator.py` + `experts/judgment.py` |
| `irsi/contract.py` | `contract/task_spec.py` |
| `irsi/domain/recompute.py` | `contract/surfaces/recompute.py` |
| `irsi/backends/hyperparallel.py` | `execution/backends/hyperparallel.py` |
| `irsi/backends/base.py` | `execution/backends/base.py` |
| `irsi/receipt.py` | `execution/metric_extractor.py` |
| `irsi/gates/builtin.py` | `gates/builtin.py` |
| `irsi/ledger.py` | `knowledge/runtime/ledger_store.py` |
| `irsi/cli.py` | `cli.py` + `entry/commands.py` |

## 6. 第一阶段只建这些

必建：

- `entry/`
- `orchestration/`
- `prompting/`
- `knowledge/`
- `knowledge/runtime/`
- `contract/surfaces/recompute.py`
- `contract/validation.py`
- `gates/`
- `execution/`
- `runtime/`
- `experts/` 六个角色
- `audit/hitt.py`
- `reporting/`（含 `exporters/`）

暂不建：

- `git/`（CommitRecorder 有需要时再加）
- `baseline/`（BaselineWorld 有需要时再加）
- `contract/surfaces/fusion.py`
- `contract/surfaces/parallel.py`
- `contract/surfaces/pipeline.py`
- `experts/knowledge_deposition.py`
- `experts/parallel_*`
- `experts/operator_*`
- `knowledge/providers/mindspore.py`
- `world/deployment`

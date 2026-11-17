# infra-rsi 目录规划（第一阶段）

日期：2026-11-16  
更新：2026-11-17  
原则：按“组件包”组织，不按抽象层名组织；专家目录放角色与 prompt 规范，`prompting/` 放通用拼装，`runtime/` 放确定性工具，`execution/` 放确定性执行。流程由代码强制，不由 agent 自由控制。

---

## 1. 当前已落地目录

```text
infra-rsi/
├── irsi/
│   ├── __init__.py
│   ├── cli.py                     # 当前 CLI 入口
│   ├── engine.py                  # 现有 trial 状态机（待被 orchestration 替代）
│   ├── registry.py                # typed registry
│   │
│   ├── contract/
│   │   ├── __init__.py
│   │   ├── task_spec.py           # InfraTaskSpec
│   │   └── surfaces/
│   │       ├── __init__.py
│   │       ├── base.py            # Hypothesis
│   │       └── recompute.py       # recompute / recompute-layerwise surface
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── metric_extractor.py    # log -> StepMetric / TrialMetrics
│   │   ├── trial_executor.py      # unified deterministic execution primitive
│   │   ├── stage.py               # 确定性 ExecutionStage（非 agent）
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── base.py            # Backend / TrialResult
│   │       └── hyperparallel.py   # HyperParallel adapter
│   │
│   ├── gates/
│   │   ├── __init__.py
│   │   ├── base.py                # GateContext / GateResult
│   │   └── builtin.py             # receipt / bitwise / memory
│   │
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── skills.py              # Skill / SkillManifest
│   │   ├── catalog.py             # SkillCatalog
│   │   ├── reader.py              # SkillResolver
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # KnowledgeProvider
│   │   │   └── hyperparallel.py   # HPKnowledgeProvider
│   │   └── runtime/
│   │       ├── __init__.py
│   │       ├── experiment_record.py
│   │       ├── record_store.py
│   │       ├── reader.py
│   │       └── ledger_store.py    # append-only ledger / report
│   │
│   ├── prompting/
│   │   ├── __init__.py
│   │   ├── context.py             # StageContext
│   │   ├── spec.py                # ExpertPromptSpec / SkillView / RenderedPrompt
│   │   ├── builder.py             # 固定段在前、变化段在后的通用拼装
│   │   └── registry.py            # role -> prompt spec
│   │
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── facade.py              # list_candidates / validate / execute / gates / metric
│   │   ├── calibration.py         # analyze clean/observed TrialResult
│   │   ├── neutrality.py          # NeutralityChecker / NeutralityResult
│   │   ├── baseline_reference.py  # BaselineReference = observed
│   │   ├── observation_patch.py   # apply / revert ObservationPatch
│   │   ├── native_prompt_runtime.py  # render prompt + record provenance
│   │   └── expert_runtime.py      # ExpertRuntime Protocol
│   │
│   ├── experts/
│   │   ├── __init__.py
│   │   ├── base.py                # ExpertRole / ExpertResult
│   │   ├── artifacts.py           # HypothesisSet / CandidateSpec / ObservationPlan / ...
│   │   ├── registry.py            # EXPERTS（五个角色）
│   │   ├── decision/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── development/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── observation/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   ├── judgment/
│   │   │   ├── expert.py
│   │   │   └── prompt_spec.py
│   │   └── archive_report/
│   │       ├── expert.py
│   │       └── prompt_spec.py
│   │
│   ├── git/
│   │   ├── __init__.py
│   │   └── commit_recorder.py     # commit candidate + report; revert
│   │
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── report_builder.py      # StepReport / RoundReport / ReportBuilder
│   │   └── exporters/
│   │       └── __init__.py        # 出口合并点；具体 exporter 待建
│   │
│   ├── audit/                     # 空脚手架；HITT 暂缓
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── state.py               # Stage / RoundState
│   │   ├── policy.py              # artifact / budget rules
│   │   ├── context_builder.py     # StageContext + skills
│   │   ├── orchestrator.py        # candidate-stage loop
│   │   └── round_controller.py    # observation + baseline + round
│   └── entry/                     # 空脚手架；commands / openjiuwen 待建
│
├── tests/
│   ├── test_contract.py
│   ├── test_domain.py
│   ├── test_engine.py
│   ├── test_receipt.py
│   ├── test_prompting.py
│   ├── test_experts.py
│   ├── test_knowledge.py
│   └── test_runtime_knowledge.py
├── knowledge/
│   └── skills/
│       └── hp/
│           ├── recompute-modes/
│           │   ├── SKILL.md
│           │   └── skill.yaml
│           ├── recompute-layerwise/
│           │   ├── SKILL.md
│           │   └── skill.yaml
│           ├── measurement/
│           │   ├── SKILL.md
│           │   └── skill.yaml
│           ├── memory-budget/
│           │   ├── SKILL.md
│           │   └── skill.yaml
│           ├── numeric-fingerprint/
│           │   ├── SKILL.md
│           │   └── skill.yaml
│           ├── engaged-evidence/
│           │   ├── SKILL.md
│           │   └── skill.yaml
│           └── mfu-perf/
│               ├── SKILL.md
│               └── skill.yaml
├── contracts/
├── workspace/
├── patches/
├── results/
├── docs/
└── pyproject.toml
```

---

## 2. 规划但尚未落地

- `entry/commands.py`
- `entry/openjiuwen_entry.py`
- `contract/candidate_generator.py`
- `contract/validation.py`
- `execution/perf_observer.py`
- `execution/snapshot.py`
- `runtime/openjiuwen_runtime.py`
- `reporting/exporters/json_exporter.py` / `markdown_exporter.py` / `csv_exporter.py`
- `audit/hitt.py`、`audit/knowledge_audit.py`、`audit/audit_record.py`（暂缓）
- `baseline/BaselineWorld`（待建）
- `contract/surfaces/fusion.py`、`parallel.py`、`pipeline.py`（暂不建）

---

## 3. 每个目录的职责

| 目录 | 职责 |
|---|---|
| `entry/` | CLI 命令、OpenJiuwen prompt 入口（待建） |
| `orchestration/` | 流程编排、round 控制、StageContext 组装（已建） |
| `prompting/` | 阶段 prompt 规范与通用拼装（已建） |
| `knowledge/` | skill catalog、HP provider、SkillResolver、runtime records、ledger（已建） |
| `contract/` | TaskSpec、修改面插件、数值精度验证（已建） |
| `gates/` | 通用 gate 与其 registry（已建） |
| `execution/` | 执行器、指标抽取、确定性 ExecutionStage（已建） |
| `runtime/` | 确定性 runtime facade、baseline 分析、观测 patch apply/revert、专家运行时 adapter（facade/neutrality/baseline_reference/observation_patch/expert_runtime 已建） |
| `git/` | 候选 commit + report、revert（CommitRecorder 已建，未接入编排） |
| `experts/` | 五个专家角色、各自 prompt spec、统一 artifact 类型（已建） |
| `audit/` | HITT 成果审计、知识审计（暂缓） |
| `reporting/` | 每步报告、round 报告、`exporters/` 导出插件（report_builder 已建；exporters 待建） |

---

## 4. 专家职责

| 专家/阶段 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `DecisionExpert` | 从修改面筛选、排序假设 | TaskSpec、baseline、records、skills | `HypothesisSet` |
| `DevelopmentExpert` | 把假设转成 contract 允许的候选；只改 `writable_prefixes` | Hypothesis / HypothesisSet | `CandidateSpec` |
| `ObservationExpert` | 生成 task-level 观测计划与可开关 patch | TaskSpec | `ObservationPlan` + `ObservationPatch` |
| `ExecutionStage` | 确定性执行候选；不是 agent | CandidateSpec | `ExecutionResult` |
| `JudgmentExpert` | 用 gates、metric、observed baseline 判断 | ExecutionResult、GateResult | `Judgment` |
| `ArchiveReportExpert` | 整理报告和归档信息；不自动 commit | Judgment | `ArchiveBundle` |
| `ExpertRegistry` | 注册/选择专家角色 | role name | `ExpertRole` |

边界：专家只产出 artifact，不控制阶段顺序、预算、retry、restore。  
`ObservationPatch` 由 runtime apply/revert；baseline 校准由 `TrialExecutor + NeutralityChecker` 执行。

---

## 5. 第一阶段知识库决议

核心 6 个 HP skill：

```text
hp/recompute-modes
hp/recompute-layerwise
hp/measurement
hp/memory-budget
hp/numeric-fingerprint
hp/engaged-evidence
```

可选：

```text
hp/mfu-perf
```

不纳入 skill：

```text
process/autoresearch-loop   → Orchestrator / RoundController
report/step-report          → ReportBuilder / ledger
audit/hitt                  → 暂缓的审计组件
contract/edit-surface       → TaskSpec + check_overrides_allowed
hp/hp-config                → runtime / contract 配置约束
```

---

## 6. prompt 拼装位置

- **专家目录**：`experts/*/prompt_spec.py`，定义角色、目标、输入、允许工具、输出 schema。
- **上下文类型**：`prompting/context.py`，定义 `StageContext`，只带当前 stage 需要的切片。
- **通用拼装**：`prompting/builder.py`，把 `ExpertPromptSpec + StageContext + selected skills` 按固定段在前、变化段在后渲染成 prompt。
- **上下文组装**：`orchestration/context_builder.py`（待建），从 task、skills、records、constraints 组装 `StageContext`。
- **确定性工具**：`runtime/facade.py`，提供 `list_candidates`、`validate_overrides`、`execute_trial`、`run_gates`、`metric_value`、`delta`。
- **baseline 校准**：`runtime/calibration.py`，跑 clean / observed baseline；待拆成 `NeutralityChecker` 与 `BaselineReference`，reference 固定 observed。

---

## 7. 调用链

```text
Orchestrator
  → EnvironmentExpert / EnvironmentOperator
  → ObservationExpert（task-level）
  → TrialExecutor（clean / observed baseline）
  → NeutralityChecker
  → BaselineReference（observed）
  → SkillResolver
  → ContextBuilder
  → PromptBuilder
  → ExpertRuntime.run(expert, prompt, runtime_facade)
  → Expert artifact
  → Ledger / Report / ExperimentRecordStore
```

当前已实现：

```text
PromptBuilder
RuntimeFacade
SkillCatalog / HPKnowledgeProvider / SkillResolver
五个 ExpertRole
ExecutionStage
Orchestrator / RoundController / ContextBuilder
NeutralityChecker / BaselineReference
BaselineCalibrator（只分析 TrialResult）
ObservationPatchManager
NativePromptRuntime
ReportBuilder
CommitRecorder（已建，未接入编排）
```

仍待实现：

```text
EnvironmentExpert
```

---

## 8. 清理前路径 → 当前路径

> 下表是清理前的历史路径，不是当前目录结构。

| 清理前 | 当前 |
|---|---|
| `irsi/engine.py` | 保留；待改为 orchestration + judgment |
| `irsi/contract.py` | `contract/task_spec.py` |
| `irsi/domain/recompute.py` | `contract/surfaces/recompute.py` |
| `irsi/backends/hyperparallel.py` | `execution/backends/hyperparallel.py` |
| `irsi/backends/base.py` | `execution/backends/base.py` |
| `irsi/receipt.py` | `execution/metric_extractor.py` |
| `irsi/gates/builtin.py` | `gates/builtin.py` |
| `irsi/ledger.py` | `knowledge/runtime/ledger_store.py` |
| `irsi/cli.py` | `cli.py`；`entry/commands.py` 待建 |

---

## 9. 第一阶段建与不建

**已建：**

- `prompting/`（context、spec、builder、registry）
- `runtime/facade.py`、`runtime/calibration.py`、`runtime/neutrality.py`、`runtime/baseline_reference.py`、`runtime/observation_patch.py`、`runtime/native_prompt_runtime.py`、`runtime/expert_runtime.py`
- `git/commit_recorder.py`
- `experts/` 五个角色与 artifact
- `execution/stage.py` 确定性 ExecutionStage
- `orchestration/`（state、policy、context_builder、orchestrator、round_controller）
- `contract/surfaces/recompute.py`
- `gates/`
- `execution/`（metric_extractor、trial_executor、stage、backends）
- `knowledge/runtime/ledger_store.py`
- `knowledge/runtime/experiment_record.py`、`record_store.py`、`reader.py`
- `knowledge/skills.py`、`catalog.py`、`reader.py`、`providers/hyperparallel.py`
- `knowledge/skills/hp/*` 七个 skill 包（6 核心 + 1 可选）
- `reporting/report_builder.py`、`reporting/exporters/base.py` 与出口占位

**待建：**

- `entry/`（commands / openjiuwen）
- `runtime/openjiuwen_runtime.py`
- `baseline/BaselineWorld`

**暂缓：**

- `audit/hitt.py`：流程未对齐，先不加
- `contract/surfaces/fusion.py`、`parallel.py`、`pipeline.py`
- `experts/knowledge_deposition.py`
- `experts/parallel_*`
- `experts/operator_*`
- `knowledge/providers/mindspore.py`
- `world/deployment`

# infra-rsi 第一阶段组件设计（按任务表粒度重写）

日期：2026-11-16  
更新：2026-11-17  
对齐对象：`rsi-task.xlsx` 中标记为“高”的任务。  
重写原则：

1. 不再用“七层抽象类图”，而是按任务表拆成 **组件 → 模块 → 职责 → 产物**。
2. 每个组件只暴露接口；跨组件靠产物连接。
3. 只覆盖第一阶段高优先级任务；并行、流水、通信、算子融合、内存、优化器、MoE 等暂列为扩展。
4. 专家是“角色/协议”，不是引擎；执行器只负责跑，裁决器只负责判断。
5. 流程由代码强制，不由 agent 自由控制。

---

## 1. 闭环图

```text
CLI
 ↓
Orchestrator / RoundController（代码强制编排）
 ↓
BaselineCalibrator（clean baseline + observed baseline）
 ↓
KnowledgeBundle
   ├─ ExperimentRecordStore（实验记录）
   └─ SkillCatalog / HPKnowledgeProvider（6 个 HP skill）
 ↓
DecisionExpert → HypothesisSet
 ↓
RecomputeSurface → CandidateSpec
 ↓
DevelopmentExpert → CandidateSpec
 ↓
ObservationExpert → ObservationPlan + ObservationPatch
 ↓
ExecutionExpert → ExecutionResult
 ↓
MetricExtractor → Gates + JudgmentExpert → Judgment
 ↓
ArchiveReportExpert → ArchiveBundle
 ↓
Ledger / Report / ExperimentRecordStore
 ↺ Orchestrator（下一轮）
```

`ObservationPatch` 不是专家自己改仓库；它是观测代码 patch artifact，由 runtime 在 baseline 前应用。  
`BaselineCalibrator` 也不是专家；它由 RoundController 调用。

---

## 2. 组件与模块

### 2.1 入口层 + 流程编排

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `CLI` | `run` / `status` / `report`；解析 task、触发一轮实验 | 用户命令、契约文件 | `RoundRequest` |
| `Orchestrator` | 启动 round、装载知识、选择专家、handoff、控制预算与重试 | `RoundRequest`、`KnowledgeBundle` | `RoundPlan` |
| `RoundController` | 维护当前 baseline、调用 `BaselineCalibrator`、下一轮触发、停止条件 | `RoundPlan`、`RoundResult` | 下一轮 `RoundRequest` |

**边界**：`CLI` 不执行训练；`Orchestrator` 不实现候选；`RoundController` 不裁决。

**对应任务**：入口层 `cli`、流程编排。

---

### 2.2 知识库

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `ExperimentRecordStore` | 追加语义化实验记录；不原地修改历史 | `ExecutionResult`、`Judgment` | `ExperimentRecord` |
| `SkillCatalog` | skill 索引/检索：按 framework、surface、model、tag 查询 | `skill.yaml` / `SKILL.md` | `SkillBundle` |
| `HPKnowledgeProvider` | 加载 HP skill 包，不绑定核心 | `knowledge/skills/hp/*` | `list[Skill]` |
| `SkillResolver` | 按 stage/tag 选择 skill | query、StageContext | `list[SkillView]` |
| `RuntimeKnowledgeReader` | 只读检索：按 round、status、surface 查询 | query | `KnowledgeBundle` |
| `RuntimeKnowledge` | 正例/反例/假设/issue 的运行时集合（暂缓） | 记录、审计 | `KnowledgeBundle` |

HP 知识不是 `HPDomainKnowledge` 大类，而是 `knowledge/skills/hp/*` 下的 skill 包；`SKILL.md` 是人类可读流程，`skill.yaml` 是机器可读 manifest。

`ExperimentRecord` 字段分层：

```text
核心: record_id, round_id, step_id, stage, hypothesis_id,
      overrides, metric, status(baseline/keep/discard/crash), detail, timestamp
推荐: surface, baseline_metric, gates, artifacts
可选: commit, rollback, prompt_hash, skill_ids, evidence
```

**边界**：知识库只读写和沉淀，不产生候选，不裁决。  
运行时知识库接口见 `docs/runtime-knowledge-design.md`：`ExperimentRecordStore` 负责写入，`RuntimeKnowledgeReader` 负责只读查询；专家不直接写 store。

**对应任务**：运行时知识库——实验记录；hp 领域知识库。

---

### 2.3 修改面：重计算

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `TaskSpec` | 冻结 workload、只读键、预算、显存上限、允许修改面 | 契约文件 | 只读约束 |
| `RecomputeSurface` | 生成重计算候选：`off/full/selective`、`layer_count`、`selection.source` | `TaskSpec` | `Hypothesis` |
| `CandidateGenerator` | 枚举单点候选，不越出修改面 | `RecomputeSurface` | `list[Hypothesis]` |

**硬约束**：`memory_budget_gib` 与 `read_only_keys` 必须在 `TaskSpec` 中；候选只能落在 `writable_prefixes` 声明的键上。

**对应任务**：native infra 修改面——重计算（限定显存上限）。

---

### 2.4 验证面：数值精度

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `NumericPrecisionGate` | 二值硬门槛：bitwise / feature parity / model equivalence；PASS 或 FAIL | `ExecutionResult`、`TrialMetrics` | `GateResult` |
| `GateSuite` | 组合 receipt、bitwise、memory、数值精度 | `ExecutionResult` | 多个 `GateResult` |
| `ValidationPolicy` | 按 surface 选择 gate 与容差；数值精度不进入噪声带 | `CandidateSpec` | `GatePlan` |

**关键区分**：`NumericPrecisionGate` 是 **PASS/FAIL**；`INCONCLUSIVE` 只用于性能 metric 的噪声带，不用于数值精度。

**对应任务**：native infra 验证面——数值精度（二值结论，硬门槛）。

---

### 2.5 执行与观测

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `TrialExecutor` | 渲染配置、启动 `torchrun`、超时清理、返回原始日志与退出码 | `CandidateSpec` | `ExecutionResult` |
| `HyperParallelBackend` | HyperParallel 具体执行实现 | `CandidateSpec` | 原始日志与 `TrialResult` |
| `ObservationExpert` | 定义指标、日志、warmup/measured、显存观察；产出观测代码 patch | `CandidateSpec`、`TaskSpec` | `ObservationPlan` + `ObservationPatch` |
| `MetricExtractor` | 把日志解析成 `StepMetric` / `TrialMetrics` | 原始日志 | `TrialMetrics` |
| `SnapshotProvider` | 记录 repo commit / artifact hash | workspace | `Snapshot` |

**边界**：`ExecutionExpert` 只负责执行环境和训练；`ObservationExpert` 只定义观测；`ObservationPatch` 由 runtime 应用；`MetricExtractor` 只解析；判定由 gates / `JudgmentExpert` 做。

**对应任务**：执行专家、观察专家。

---

### 2.6 专家组

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `DecisionExpert` | 从修改面筛选、排序候选假设 | `TaskSpec`、baseline、记录、skills | `HypothesisSet` |
| `DevelopmentExpert` | 把假设转成 contract 允许的候选 | `Hypothesis` / `HypothesisSet`、`TaskSpec` | `CandidateSpec` |
| `ObservationExpert` | 定义观测方式与观测代码 patch | `CandidateSpec`、`TaskSpec` | `ObservationPlan` + `ObservationPatch` |
| `ExecutionExpert` | 只执行环境和训练 | `CandidateSpec` | `ExecutionResult` |
| `JudgmentExpert` | 用 gates、metric、校准后的 baseline 判断 | `ExecutionResult`、`GateResult` | `Judgment` |
| `ArchiveReportExpert` | 整理报告和归档信息 | `Judgment` | `ArchiveBundle` |
| `ExpertRegistry` | 注册/选择专家角色 | role name | `ExpertRole` |

**边界**：专家是角色协议，不是引擎；每个专家只产出自己的 artifact。  
`ObservationPatch` 由 runtime 应用；baseline 校准由 `RoundController` / `BaselineCalibrator` 执行；专家不控制流程。

**对应任务**：agents 六个重计算角色。

---

### 2.7 HITT 成果审计（暂不纳入第一阶段）

HITT 流程尚未对齐，暂不建 `HITTAudit` / `KnowledgeAudit` / `AuditRecord`。等审计流程明确后再加。

**对应任务**：HITT 成果审计，暂缓。

---

### 2.8 报告

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `StepReport` | 每步：为什么改、改了什么、测试结果、提升/失败、commit | `ExperimentRecord` | `step report` |
| `RoundReport` | 一轮汇总：做了哪些事、每步提升、采纳/未采纳 | `StepReport[]` | `round report` |
| `ReportBuilder` | 生成 `report.json` / `report.md` | `LedgerStore` | `report.json`, `report.md` |

**边界**：报告 schema 由 `ReportBuilder` 代码强制；`ArchiveReportExpert` 只整理 artifact，不自动 commit。

**对应任务**：报告——做了哪些事，每步提升。

---

### 2.9 支撑组件：账本、commit、baseline

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `LedgerStore` | 追加 decisions、trials、results、candidate 记录 | `Judgment`、`ExecutionResult` | `results.tsv`, `candidates.jsonl` |
| `CommitRecorder` | 每步一个 commit；失败也 commit 报告并回退代码 | `Patch`、`StepReport` | `commit` |
| `BaselineCalibrator` | 跑 clean baseline 与 observed baseline，比较观测开销，选择 reference | `ObservationPlan`、两个 facade | `BaselineCalibration` |

**边界**：这些是支撑，不是你的高优先级任务；但没有它们，实验记录和下一轮 baseline 不完整。

---

## 3. 闭环时序

1. `CLI` 收到任务，交给 `Orchestrator`。
2. `Orchestrator` 读取 `ExperimentRecordStore` 与 `SkillCatalog / HPKnowledgeProvider`。
3. `RoundController` 调用 `BaselineCalibrator`：跑 clean baseline 与 observed baseline；若观测开销超过 noise，则用 observed baseline 作为 reference。
4. `DecisionExpert` 根据 perf、记录、知识提出 `HypothesisSet`。
5. `RecomputeSurface` 在 `TaskSpec` 允许范围内生成重计算候选。
6. `DevelopmentExpert` 产出 contract 允许的 `CandidateSpec`。
7. `ObservationExpert` 产出 `ObservationPlan` + `ObservationPatch`；runtime 在 baseline 前应用非空 patch。
8. `ExecutionExpert` 只执行环境和训练，产出 `ExecutionResult`。
9. `MetricExtractor` 解析指标；gates 与 `JudgmentExpert` 用校准后的 baseline 判断 keep / discard / crash。
10. `ArchiveReportExpert` 写 `ArchiveBundle`；`ReportBuilder` / `LedgerStore` 生成报告。
11. `ExperimentRecordStore` 写入实验记录；回到第 1 步。

`HITTAudit`、`CommitRecorder` 在第一阶段暂缓，按需要再加。

---

## 4. 和任务表逐行对齐

| 任务表行 | 设计组件 | 产物 | 覆盖判断 |
|---|---|---|---|
| 流程编排 | `Orchestrator` + `RoundController` | `RoundPlan` | 覆盖，且流程由代码强制 |
| 运行时知识库：实验记录 | `ExperimentRecordStore` | `ExperimentRecord` | 覆盖，补上 commit/失败回退字段 |
| hp 领域知识库 | `SkillCatalog` + `HPKnowledgeProvider` | `SkillBundle` | 覆盖；第一阶段 6 个核心 skill |
| native infra 修改面：重计算 | `RecomputeSurface` + `CandidateGenerator` | `CandidateSpec` | 覆盖 |
| native infra 验证面：数值精度 | `NumericPrecisionGate` | `GateResult` | 覆盖，且明确为二值硬门槛 |
| agents 六角色 | 六个 `ExpertRole` 实现 | `HypothesisSet/CandidateSpec/ExecutionResult/Judgment/ArchiveBundle` | 已实现，按你的角色逐项对应 |
| HITT 成果审计 | `HITTAudit` | `AuditVerdict` | 暂缓，流程未对齐 |
| 报告 | `StepReport` + `RoundReport` + `ReportBuilder` | `report.json` / `report.md` | 覆盖；报告 schema 由代码强制 |
| 入口层 cli | `CLI` | `RoundRequest` | 覆盖 |

**未进入第一阶段、暂列扩展的：**

- 并行策略、流水调度、通信调度、算子融合、内存优化、优化器优化、MoE 优化、模型结构等价替换、组合搜索
- cann 领域知识库、固化知识库
- 知识沉淀专家、并行策略分析/实施/验证专家、算子优化分析/实施/验证专家
- openJiuwen prompt 触发、openJiuwen 产物 RSI 入口、idea 结构化 skill
- 生产部署 / 上线门

---

## 5. 第一阶段知识库决议

第一阶段只保留 **6 个核心 HP skill**：

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

不纳入 skill 的内容：

```text
process/autoresearch-loop   → Orchestrator / RoundController
report/step-report          → ReportBuilder / ledger
audit/hitt                  → 暂缓的审计组件
contract/edit-surface       → TaskSpec + check_overrides_allowed
hp/hp-config                → runtime / contract 配置约束
```

Skill 只承载领域知识；流程、报告、审计、contract 约束由代码强制。

---

## 6. 第一阶段实现顺序

1. **CLI + Orchestrator / RoundController**：代码强制阶段顺序、预算、停止条件。
2. **BaselineCalibrator**：先校准 clean / observed baseline。
3. **ExperimentRecordStore**：记录每步实验。
4. **SkillCatalog / HPKnowledgeProvider / SkillResolver**：加载 6 个 HP skill。
5. **RecomputeSurface + NumericPrecisionGate**：冻结修改面与硬门槛。
6. **TrialExecutor + MetricExtractor**：能跑、能解析。
7. **六个 ExpertRole**：决策、开发、观察、执行、判断、归档。
8. **ReportBuilder / LedgerStore**：生成报告。
9. **CommitRecorder / BaselineWorld**：按需要再补。
10. **HITTAudit**：审计流程对齐后再加。

---

## 7. 与现有代码的关系

| 设计组件 | 现有代码 | 状态 |
|---|---|---|
| `CLI` | `irsi/cli.py` | 已有入口 |
| `Orchestrator` / `RoundController` | `irsi/engine.py` 的 `run` 流程 | 编排与裁决仍混在一起，需拆 |
| `ExperimentRecordStore` | `irsi/knowledge/runtime/record_store.py` | 已实现 |
| `SkillCatalog / HPKnowledgeProvider / SkillResolver` | `irsi/knowledge/{skills,catalog,reader,providers}` | 已实现；skill 包在 `knowledge/skills/hp/*` |
| `RuntimeKnowledgeReader` | `irsi/knowledge/runtime/reader.py` | 已实现 |
| `RecomputeSurface` | `irsi/contract/surfaces/recompute.py` | 已有重计算候选 |
| `NumericPrecisionGate` | `irsi/gates/builtin.py` 的 `BitwiseGate` | 已有二值 gate |
| `TrialExecutor` | `irsi/execution/backends/hyperparallel.py` | 已有执行；解析耦合在 backend |
| `ObservationPlan / ObservationPatch` | `irsi/experts/observation/expert.py`、`irsi/experts/artifacts.py` | 已有 artifact；patch 未接入执行链 |
| `BaselineCalibrator` | `irsi/runtime/calibration.py` | 已有，但未接入 Engine |
| `MetricExtractor` | `irsi/execution/metric_extractor.py` | 已有解析 |
| 六个 `ExpertRole` | `irsi/experts/*/expert.py` | 已实现 |
| `PromptBuilder` | `irsi/prompting/builder.py` | 已实现 |
| `RuntimeFacade` | `irsi/runtime/facade.py` | 已实现 |
| `HITTAudit` | 无 | 暂缓 |
| `StepReport` / `RoundReport` | `knowledge/runtime/ledger_store.py` 有 report | 需补每步叙事与 report builder |
| `CommitRecorder` | 无 | 缺 |
| `LedgerStore` | `irsi/knowledge/runtime/ledger_store.py` | 已有账本 |
| `BaselineWorld` | `workspace/` + 契约 | 有输入/产物，缺 baseline 门 |

**结论**：现有代码覆盖 `CLI / RecomputeSurface / NumericPrecisionGate / TrialExecutor / MetricExtractor / LedgerStore / PromptBuilder / RuntimeFacade / 六个 ExpertRole / BaselineCalibrator / SkillCatalog / HPKnowledgeProvider / SkillResolver / ExperimentRecordStore / RuntimeKnowledgeReader`；第一阶段真正缺的是 **Orchestrator、RoundController、ReportBuilder / StepReport、CommitRecorder、HITTAudit**。

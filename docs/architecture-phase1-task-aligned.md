# infra-rsi 第一阶段组件设计（按任务表粒度重写）

日期：2026-11-16  
对齐对象：`rsi-task.xlsx` 中标记为“高”的任务。  
重写原则：

1. 不再用“七层抽象类图”，而是按你的任务表拆成 **组件 → 模块 → 职责 → 产物**。
2. 每个组件只暴露接口；跨组件靠产物连接，不把所有实现类画成一张蜘蛛网。
3. 只覆盖第一阶段高优先级任务；并行、流水、通信、算子融合、内存、优化器、MoE 等暂列为扩展。
4. 专家是“角色/协议”，不是引擎；执行器只负责跑，裁决器只负责判断，审计器只负责人审。

---

## 1. 按任务表的总图

```text
CLI
 ↓
Orchestrator（流程编排）
 ↓
KnowledgeBundle
   ├─ ExperimentRecordStore（实验记录）
   └─ SkillCatalog / HPKnowledgeProvider（hp skills）
 ↓
DecisionExpert（决策专家）
 ↓
RecomputeSurface（重计算修改面） → CandidateSpec
 ↓
DevelopmentExpert（开发专家）
 ↓
ExecutionExpert（执行专家） → ObservationExpert（观察专家） → MetricExtractor
 ↓
NumericPrecisionGate（数值精度硬门槛） + JudgmentExpert（判断专家）
 ↓
HITTAudit（成果审计） → StepReport / RoundReport → CommitRecorder
 ↓
ExperimentRecordStore（知识沉淀/记录）
 ↺ Orchestrator（下一轮）
```

这不是类图，而是**任务闭环图**：每个箭头对应一个任务产物。

---

## 2. 组件与模块

### 2.1 入口层 + 流程编排

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `CLI` | `run` / `status` / `report`；解析 task、触发一轮实验 | 用户命令、契约文件 | `RoundRequest` |
| `Orchestrator` | 启动 round、装载知识、选择专家、handoff、控制预算与重试 | `RoundRequest`、`KnowledgeBundle` | `RoundPlan` |
| `RoundController` | 维护当前 baseline、下一轮触发、停止条件 | `RoundPlan`、`RoundResult` | 下一轮 `RoundRequest` |

**边界**：`CLI` 不执行训练；`Orchestrator` 不实现候选；`RoundController` 不裁决。

**对应任务**：入口层 `cli`、流程编排。

---

### 2.2 知识库

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `ExperimentRecordStore` | 每步记录：为什么改、改了什么、测试结果、commit、失败/回退 | `ExecutionResult`、`Judgment`、`Patch` | `ExperimentRecord` |
| `SkillCatalog` | skill 索引/检索：按 framework、surface、model、tag 查询 | `skill.yaml` / `SKILL.md` | `SkillBundle` |
| `HPKnowledgeProvider` | 加载 HP skill 包，不绑定核心 | `knowledge/skills/hp/*` | `list[Skill]` |
| `KnowledgeReader` | 只读检索：按 round、case、surface 查询 | query | `KnowledgeBundle` |
| `RuntimeKnowledge` | 正例/反例/假设/issue 的运行时集合 | 记录、审计 | `KnowledgeBundle` |

HP 知识不是 `HPDomainKnowledge` 大类，而是 `knowledge/skills/hp/*` 下的 skill；`SkillCatalog` 聚合多个 provider。`SKILL.md` 是人类可读流程，`skill.yaml` 是机器可读 manifest。

落地说明（2026-11-19）：实现统一使用 `irsi/knowledge/skills/<category>/<skill>/<environment>/<framework>/`，
由 `SkillCatalog` 递归发现 `SKILL.md`；`SKILL.md` 的 YAML frontmatter 承担机器可读 manifest 职责。

`ExperimentRecord` 建议字段：

```text
round_id, step_id, hypothesis, change, test_result,
commit, status(kept/discarded/failed), rollback,
report_path, timestamp
```

**边界**：知识库只读写和沉淀，不产生候选，不裁决。

**对应任务**：运行时知识库——实验记录；hp 领域知识库。

---

### 2.3 修改面：重计算

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `TaskSpec` | 冻结 workload、只读键、预算、显存上限、允许修改面 | 契约文件 | 只读约束 |
| `RecomputeSurface` | 生成重计算候选：`off/full/selective`、`layer_count`、`selection.source`、`allow_cache_entry_mutation` | `TaskSpec`、`KnowledgeBundle` | `CandidateSpec` |
| `CandidateGenerator` | 枚举单点候选，不越出修改面 | `RecomputeSurface` | `list[CandidateSpec]` |

**硬约束**：`memory_budget_gib` 与 `read_only_keys` 必须在 `TaskSpec` 中；候选只能落在 `RecomputeSurface` 声明的键上。

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

### 2.5 执行

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `TrialExecutor` | 渲染配置、启动 `torchrun`、超时清理、返回原始日志与退出码 | `CandidateSpec` | `ExecutionResult` |
| `HyperParallelExecutor` | HyperParallel 具体执行实现 | `CandidateSpec` | 原始日志 |
| `PerfObserver` | 开启 perf 采集、增删日志、采集 step 指标 | trial 配置 | perf 日志 |
| `MetricExtractor` | 把日志解析成 `StepMetric` / `TrialMetrics` | 原始日志 | `TrialMetrics` |
| `SnapshotProvider` | 记录 repo commit / artifact hash | workspace | `Snapshot` |

**边界**：`TrialExecutor` 只负责“跑 + 原始结果”；`MetricExtractor` 负责解析；`PerfObserver` 负责观测手段。

**对应任务**：执行专家、观察专家。

---

### 2.6 专家组

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `DecisionExpert` | 根据 perf、实验记录、知识提出假设 | `KnowledgeBundle`、`RoundPlan` | `Hypothesis` |
| `DevelopmentExpert` | 按 skill 与框架约束实施单点代码变更 | `Hypothesis`、`TaskSpec` | `Patch` |
| `ObservationExpert` | 开启 perf 采集、增删日志 | `Patch`、`CandidateSpec` | `ObservationPlan` |
| `ExecutionExpert` | 配环境、启动、给出日志与 perf 结果 | `CandidateSpec` | `ExecutionResult` |
| `JudgmentExpert` | 根据日志/指标判断是否有收益 | `ExecutionResult`、`GateResult` | `Judgment` |
| `ArchiveReportExpert` | 整理报告、commit、失败回退记录 | `Judgment`、`Patch` | `ArchiveBundle` |
| `ExpertRegistry` | 注册/选择专家角色 | role name | `ExpertRole` |

**边界**：专家是角色协议，不是引擎；每个专家只产出自己的 artifact。

**对应任务**：agents 六个重计算角色。

---

### 2.7 HITT 成果审计

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `HITTAudit` | 人审成果：结果、报告、知识沉淀是否可信 | `ArchiveBundle`、`RoundReport` | `AuditVerdict` |
| `KnowledgeAudit` | 检查沉淀知识是否可复用、是否过期 | `ExperimentRecord` | `AuditVerdict` |
| `AuditRecord` | 记录审计人、时间、依据、artifact hash | `AuditVerdict` | `AuditRecord` |

**边界**：审计不修改 trial，不自动晋升知识；它是人审门。

**对应任务**：HITT 成果审计。

---

### 2.8 报告

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `StepReport` | 每步：为什么改、改了什么、测试结果、提升/失败、commit | `ExperimentRecord` | `step report` |
| `RoundReport` | 一轮汇总：做了哪些事、每步提升、采纳/未采纳 | `StepReport[]` | `round report` |
| `ReportBuilder` | 生成 `report.json` / `report.md` | `LedgerStore` | `report.json`, `report.md` |

**对应任务**：报告——做了哪些事，每步提升。

---

### 2.9 支撑组件：账本、commit、baseline

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `LedgerStore` | 追加 decisions、trials、results、candidate 记录 | `Judgment`、`ExecutionResult` | `results.tsv`, `candidates.jsonl` |
| `CommitRecorder` | 每步一个 commit；失败也 commit 报告并回退代码 | `Patch`、`StepReport` | `commit` |
| `BaselineWorld` | 当前 best config，作为下一轮 baseline | `Judgment` | `Baseline` |

**边界**：这些是支撑，不是你的高优先级任务；但没有它们，实验记录和下一轮 baseline 不完整。

---

## 3. 闭环时序（按你的任务顺序）

1. `CLI` 收到任务，交给 `Orchestrator`。
2. `Orchestrator` 读取 `ExperimentRecordStore` 与 `SkillCatalog / HPKnowledgeProvider`。
3. `DecisionExpert` 根据 perf、记录、知识提出假设。
4. `RecomputeSurface` 在 `TaskSpec` 允许范围内生成重计算候选。
5. `DevelopmentExpert` 实施单点代码变更。
6. `ExecutionExpert` 配环境、启动；`ObservationExpert` 开启 perf 采集与日志修改。
7. `MetricExtractor` 解析指标；`NumericPrecisionGate` 做二值硬门槛；`JudgmentExpert` 判断收益。
8. `ArchiveReportExpert` 写 `StepReport` / `RoundReport`，`CommitRecorder` 记录 commit。
9. `HITTAudit` 人审成果与知识。
10. `ExperimentRecordStore` 写入实验记录；`BaselineWorld` 更新 baseline；回到第 1 步。

---

## 4. 和任务表逐行对齐

| 任务表行 | 设计组件 | 产物 | 覆盖判断 |
|---|---|---|---|
| 流程编排 | `Orchestrator` + `RoundController` | `RoundPlan` | 覆盖，且补上了表里未写的编排职责 |
| 运行时知识库：实验记录 | `ExperimentRecordStore` | `ExperimentRecord` | 覆盖，补上了 commit/失败回退字段 |
| hp 领域知识库 | `SkillCatalog` + `HPKnowledgeProvider` | `SkillBundle` | 覆盖，补上了 mfu-perf/框架约束 |
| native infra 修改面：重计算 | `RecomputeSurface` + `CandidateGenerator` | `CandidateSpec` | 覆盖 |
| native infra 验证面：数值精度 | `NumericPrecisionGate` | `GateResult` | 覆盖，且明确为二值硬门槛 |
| agents 六角色 | 六个 `ExpertRole` 实现 | `Hypothesis/Patch/ExecutionResult/Judgment/ArchiveBundle` | 覆盖，按你的角色逐项对应 |
| HITT 成果审计 | `HITTAudit` | `AuditVerdict` | 覆盖，从知识层移到审计层 |
| 报告 | `StepReport` + `RoundReport` + `ReportBuilder` | `report.json` / `report.md` | 覆盖，补上每步提升叙事 |
| 入口层 cli | `CLI` | `RoundRequest` | 覆盖 |

**未进入第一阶段、暂列扩展的：**

- 并行策略、流水调度、通信调度、算子融合、内存优化、优化器优化、MoE 优化、模型结构等价替换、组合搜索
- cann 领域知识库、固化知识库
- 知识沉淀专家、并行策略分析/实施/验证专家、算子优化分析/实施/验证专家
- openJiuwen prompt 触发、openJiuwen 产物 RSI 入口、idea 结构化 skill
- 生产部署 / 上线门

这些在你的表里大多为空或未标“高”，不应塞进第一阶段主线。

---

## 5. 第一阶段实现顺序

1. **CLI + Orchestrator**：先把“谁触发、谁 handoff、谁控制下一轮”做出来。
2. **ExperimentRecordStore + SkillCatalog / HPKnowledgeProvider**：先有输入知识，再谈专家。
3. **RecomputeSurface + NumericPrecisionGate**：先冻结修改面与硬门槛。
4. **TrialExecutor + PerfObserver + MetricExtractor**：先能跑、能观测、能解析。
5. **六个 ExpertRole**：决策、开发、观察、执行、判断、归档报告。
6. **HITTAudit + StepReport**：先有人审与每步报告。
7. **CommitRecorder / BaselineWorld**：最后补 commit 纪律与下一轮 baseline。

---

## 6. 与现有代码的关系

| 设计组件 | 现有代码 | 状态 |
|---|---|---|
| `CLI` | `irsi/cli.py` | 已有入口 |
| `Orchestrator` | `irsi/engine.py` 的 `run` 流程 | 编排与裁决混在一起，需拆 |
| `ExperimentRecordStore` | 无 | 缺 |
| `SkillCatalog / HPKnowledgeProvider` | 文档/占位 | 缺结构化实现 |
| `RecomputeSurface` | `irsi/contract/surfaces/recompute.py` | 已有重计算候选 |
| `NumericPrecisionGate` | `irsi/gates/builtin.py` 的 `BitwiseGate` | 已有二值 gate |
| `TrialExecutor` | `irsi/execution/backends/hyperparallel.py` | 执行与解析混在一起，需拆 |
| `PerfObserver` | 无独立模块 | 缺 |
| `MetricExtractor` | `irsi/execution/metric_extractor.py` | 已有解析 |
| 六个 `ExpertRole` | 无 | 缺 |
| `HITTAudit` | 无 | 缺 |
| `StepReport` / `RoundReport` | `knowledge/runtime/ledger_store.py` 有 report | 需补每步叙事 |
| `CommitRecorder` | 无 | 缺 |
| `LedgerStore` | `irsi/knowledge/runtime/ledger_store.py` | 已有账本 |
| `BaselineWorld` | `workspace/` + 契约 | 有输入/产物，缺 baseline 门 |

**结论**：现有代码覆盖 `CLI / RecomputeSurface / NumericPrecisionGate / TrialExecutor / MetricExtractor / LedgerStore`；第一阶段真正缺的是 **Orchestrator、ExperimentRecordStore、SkillCatalog / HPKnowledgeProvider、六个专家角色、HITTAudit、StepReport、CommitRecorder**。

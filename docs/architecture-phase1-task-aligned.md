# infra-rsi 第一阶段组件设计（按任务表粒度重写）

日期：2026-11-16  
更新：2026-11-17  
对齐对象：`rsi-task.xlsx` 中标记为“高”的任务。  
重写原则：

1. 按 **组件 → 模块 → 职责 → 产物** 描述，不再用“七层抽象类图”。
2. 每个组件只暴露接口；跨组件靠 artifact 连接。
3. 第一阶段只覆盖高优先级任务；并行、流水、通信、算子融合、内存、优化器、MoE 等暂列扩展。
4. 专家是角色协议；执行是确定性 runtime，不是 agent。
5. 流程由代码强制，不由 agent 自由控制。
6. 观测跟假设无关：ObservationPlan / ObservationPatch 是 task/round 级，不是 hypothesis 级。

---

## 1. 闭环流程

```text
CLI
 ↓
Orchestrator / RoundController（代码强制状态机）
 ↓
ENV_SETUP（EnvironmentExpert / 有界 agent）
 ↓
CLEAN_BASELINE（observation off）
 ↓
ENV_SNAPSHOT commit + report
 ↓
OBSERVATION（task-level ObservationPlan + 可开关 ObservationPatch）
 ↓
OBSERVED_BASELINE（observation on）
 ↓
NEUTRALITY_CHECK（numeric fingerprint + overhead）
 ↓
CALIBRATED（reference = observed baseline）
 ↓
DECISION → HypothesisSet
 ↓
DEVELOPMENT → CandidateSpec
 ↓
EXECUTION → ExecutionResult（TrialExecutor，确定性）
 ↓
VERIFY（MetricExtractor + gates）
 ↓
JUDGMENT → Judgment
 ↓
ARCHIVE_REPORT → ArchiveBundle
 ↓
COMMIT / REPORT
 ↺ NEXT_ROUND（复用 observed baseline）
```

关键边界：

- `EnvironmentExpert` 只在最开始处理环境；跑通后环境快照固定，后续不再改环境。
- `ObservationPatch` 可 apply / revert；clean baseline 是 off，observed baseline 是 on。
- `clean baseline` 只做观测开销对照；**reference baseline 固定为 observed baseline**。
- `ExecutionStage` 只调用 `TrialExecutor`，不生成 prompt、不裁决。
- 每个候选一个 commit；正收益提交候选 patch + report，负收益回退候选并提交 report，失败 patch 不入库。

---

## 2. 组件与模块

### 2.1 入口层 + 流程编排

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `CLI` | `run` / `status` / `report`；解析 task 并触发一轮实验 | 用户命令、契约文件 | `RoundRequest` |
| `Orchestrator` | 单轮阶段状态机；选择专家、校验 artifact、控制预算与重试 | `RoundRequest`、`RoundState` | `RoundResult` |
| `RoundController` | 外层轮次控制；环境固定、baseline 校准、停止条件 | `RoundPlan`、`RoundResult` | 下一轮 `RoundRequest` |
| `ContextBuilder` | 组装每阶段 `StageContext` 切片 | task、records、skills、baseline | `StageContext` + `SkillView[]` |

**边界**：CLI 不执行训练；Orchestrator 不生成候选；RoundController 不裁决。

---

### 2.2 环境与执行

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `EnvironmentExpert` / `EnvironmentOperator` | 环境搭建、诊断、修复；有界 agent，可审计 | task、环境快照、错误 | `EnvironmentSnapshot` / `EnvironmentAction` |
| `EnvironmentSnapshot` | 记录 python、platform、repo commit、packages、env_setup | `TaskSpec` | `EnvironmentSnapshot` |
| `TrialExecutor` | 唯一执行原语：渲染配置、启动训练、超时清理、返回 `TrialResult` | spec、overrides、label、patch 状态 | `TrialResult` |
| `ExecutionStage` | 确定性执行候选；不生成 prompt、不裁决 | `CandidateSpec` | `ExecutionResult` |
| `Backend` | HyperParallel 等具体执行实现 | `CandidateSpec` | `TrialResult` |

**边界**：执行是确定性 runtime；环境搭建可能需要有界 agent；ExecutionStage 不控制流程。ExecutionStage 不捕获异常；`Orchestrator` 捕获执行失败，写 `crash` / `env_error` 记录，并标记 `rollback=not_committed`。

---

### 2.3 观测与基线

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `ObservationExpert` | 生成 task-level 观测计划；不依赖假设 | `TaskSpec` | `ObservationPlan` + `ObservationPatch` |
| `ObservationPatch` | 可开关的观测代码 patch；只做日志/指标，不改变计算 | 目标文件、diff | apply / revert |
| `TrialExecutor` | 跑 clean / observed baseline | 空 overrides、patch 状态 | 两个 `TrialResult` |
| `NeutralityChecker` | 检查 numeric fingerprint、性能/显存开销 | clean / observed `TrialResult` | `NeutralityResult` |
| `BaselineReference` | 冻结 `reference = observed baseline` | observed `TrialResult`、中性结果 | `baseline_metric` / `baseline_trial` |

**边界**：`clean baseline` 是控制变量；`observed baseline` 是实验基准。没有 `BaselineSelector`；单 profile 下直接固定 observed。

---

### 2.4 修改面：重计算

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `TaskSpec` | 冻结 workload、只读键、预算、显存上限、允许修改面 | 契约文件 | 只读约束 |
| `RecomputeSurface` | 生成重计算候选：`off/full/selective`、`layer_count`、`selection.source` | `TaskSpec` | `Hypothesis` |
| `CandidateGenerator` | 枚举单点候选，不越出修改面 | `RecomputeSurface` | `list[Hypothesis]` |

**硬约束**：候选只能落在 `writable_prefixes`；`read_only_keys` 永远优先。

---

### 2.5 验证面：数值精度

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `NumericPrecisionGate` | 二值硬门槛：bitwise / feature parity / model equivalence；PASS 或 FAIL | `TrialResult`、baseline | `GateResult` |
| `GateSuite` | 组合 receipt、bitwise、memory | `TrialResult` | 多个 `GateResult` |
| `ValidationPolicy` | 按 surface 选择 gate 与容差；数值精度不进入噪声带 | `CandidateSpec` | `GatePlan` |

**关键区分**：数值精度是 **PASS/FAIL**；`INCONCLUSIVE` 只用于性能 metric 的噪声带。

---

### 2.6 专家组

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `DecisionExpert` | 从修改面筛选、排序假设 | task、baseline、records、skills | `HypothesisSet` |
| `DevelopmentExpert` | 把假设转成 contract 允许的候选；只改 `writable_prefixes` | `Hypothesis` / `HypothesisSet` | `CandidateSpec` |
| `ObservationExpert` | 生成 task-level 观测计划与 patch | `TaskSpec` | `ObservationPlan` + `ObservationPatch` |
| `ExecutionStage` | 确定性执行候选 | `CandidateSpec` | `ExecutionResult` |
| `JudgmentExpert` | 用 gates、metric、observed baseline 判断 | `ExecutionResult`、gates | `Judgment` |
| `ArchiveReportExpert` | 整理 step/round report；不自动 commit | `Judgment` | `ArchiveBundle` |
| `ExpertRegistry` | 注册/选择专家角色 | role name | `ExpertRole` |

**边界**：专家只产出 artifact；ExecutionStage 不是 agent；ObservationExpert 不依赖 candidate；专家不控制阶段顺序、预算、retry、restore。

---

### 2.7 知识库

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `ExperimentRecordStore` | append-only 语义化实验记录 | 环境快照、观测 patch、中性结果、trial、judgment | `ExperimentRecord` |
| `RuntimeKnowledgeReader` | 只读查询 round / surface / status | query | `KnowledgeBundle` |
| `SkillCatalog` | skill 索引/检索 | `skill.yaml` / `SKILL.md` | `SkillBundle` |
| `HPKnowledgeProvider` | 加载 HP skill 包，不绑定核心 | `knowledge/skills/hp/*` | `list[Skill]` |
| `SkillResolver` | 按 stage/tag/surface 选择 skill | query、StageContext | `list[SkillView]` |

`ExperimentRecord` 字段分层：

```text
核心: record_id, round_id, step_id, stage, hypothesis_id,
      overrides, metric, status, detail, timestamp
状态: baseline / calibrated / keep / discard / crash / env_error / patch_error
推荐: surface, baseline_metric, gates, artifacts,
      environment_snapshot, observation_patch
可选: commit, rollback, prompt_hash, skill_ids, evidence, neutrality, report
```

**边界**：知识库只读写和沉淀，不产生候选，不裁决。专家不直接写 store；写入由 Orchestrator / RoundController 完成。

---

### 2.8 报告与提交

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `StepReport` | 每步：为什么改、改了什么、测试结果、提升/失败、commit | `ExperimentRecord` | step report |
| `RoundReport` | 一轮汇总：做了哪些事、每步提升、采纳/未采纳 | `StepReport[]` | round report |
| `ReportBuilder` | 生成 `report.json` / `report.md` | ledger / store | report files |
| `CommitRecorder` | 每个候选一个 commit；report 随 commit | patch、report | commit |

**边界**：报告 schema 由代码强制；`ArchiveReportExpert` 只整理 artifact，不自动 commit。失败 patch 不入库，失败修改描述写在 report；当前 config-only 候选的 rollback 标记为 `not_committed`。`CommitRecorder` 已接入：keep 提交 trial config + step report，discard/crash 只提交 step report。

---

### 2.9 HITT 成果审计（暂缓）

HITT 流程尚未对齐，暂不建 `HITTAudit` / `KnowledgeAudit` / `AuditRecord`。

---

## 3. 和任务表逐行对齐

| 任务表行 | 设计组件 | 产物 | 覆盖判断 |
|---|---|---|---|
| 流程编排 | `Orchestrator` + `RoundController` + `ContextBuilder` | `RoundPlan` / `RoundResult` | 待实现，流程由代码强制 |
| 运行时知识库：实验记录 | `ExperimentRecordStore` | `ExperimentRecord` | 已实现，补环境/观测/中性/报告字段 |
| hp 领域知识库 | `SkillCatalog` + `HPKnowledgeProvider` | `SkillBundle` | 已实现；6 个核心 skill |
| native infra 修改面：重计算 | `RecomputeSurface` + `CandidateGenerator` | `CandidateSpec` | 已实现 |
| native infra 验证面：数值精度 | `NumericPrecisionGate` | `GateResult` | 已实现，二值硬门槛 |
| agents 角色 | 5 个 `ExpertRole` + `ExecutionStage` | artifacts | 已调整：执行不是 agent |
| HITT 成果审计 | `HITTAudit` | `AuditVerdict` | 暂缓 |
| 报告 | `StepReport` + `RoundReport` + `ReportBuilder` | report | 待实现 |
| 入口层 cli | `CLI` | `RoundRequest` | 已有入口，待接编排 |

**未进入第一阶段、暂列扩展：**

- 并行策略、流水调度、通信调度、算子融合、内存优化、优化器优化、MoE 优化、模型结构等价替换、组合搜索
- cann 领域知识库、固化知识库
- 知识沉淀专家、并行策略分析/实施/验证专家、算子优化分析/实施/验证专家
- openJiuwen prompt 触发、openJiuwen 产物 RSI 入口、idea 结构化 skill
- 生产部署 / 上线门

---

## 4. 第一阶段知识库决议

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

Skill 只承载领域知识；流程、报告、审计、contract 约束由代码强制。

---

## 5. 第一阶段实现顺序

1. **专家修改**：ObservationExpert 任务级；去掉 ExecutionExpert agent；新增确定性 `ExecutionStage`。
2. **知识库修改**：ExperimentRecord 增加 `environment_snapshot`、`observation_patch`、`neutrality`、`report`，status 扩展。
3. **Orchestrator / RoundController / ContextBuilder**：代码强制阶段顺序、预算、停止条件。
4. **TrialExecutor / NeutralityChecker / BaselineReference**：执行与判断拆开；reference = observed。
5. **ExperimentRecordStore / RuntimeKnowledgeReader** 接入编排。
6. **ObservationPatch apply/revert**：可开关观测。
7. **ReportBuilder / CommitRecorder**：每个候选一个 commit，report 随 commit。
8. **HITTAudit**：审计流程对齐后再加。

---

## 6. 与现有代码的关系

| 设计组件 | 现有代码 | 状态 |
|---|---|---|
| `CLI` | `irsi/cli.py` | 已接入 `RoundController` |
| `Orchestrator` / `RoundController` / `ContextBuilder` | `irsi/orchestration/` | 已实现：状态机、上下文、候选循环 |
| `ExperimentRecordStore` | `irsi/knowledge/runtime/record_store.py` | 已实现 |
| `RuntimeKnowledgeReader` | `irsi/knowledge/runtime/reader.py` | 已实现 |
| `SkillCatalog / HPKnowledgeProvider / SkillResolver` | `irsi/knowledge/{skills,catalog,reader,providers}` | 已实现 |
| `RecomputeSurface` | `irsi/contract/surfaces/recompute.py` | 已实现 |
| `NumericPrecisionGate` | `irsi/gates/builtin.py` | 已实现 |
| `TrialExecutor` | `irsi/execution/trial_executor.py` | 已实现；统一执行原语 |
| `EnvironmentSnapshot` | `irsi/environment/snapshot.py` | 已实现；记录 baseline world |
| `EnvironmentExpert` | 无 | 未实现；env setup 仍靠 backend / 人工 |
| `ExecutionStage` | `irsi/execution/stage.py` | 已新增，确定性执行 |
| `ObservationExpert` | `irsi/experts/observation/expert.py` | 已改为 task-level |
| `ObservationPatch` | `irsi/experts/artifacts.py` + `irsi/runtime/observation_patch.py` | 已有 artifact；apply/revert 已实现 |
| `NeutralityChecker` / `BaselineReference` | `irsi/runtime/neutrality.py`, `irsi/runtime/baseline_reference.py` | 已实现；`BaselineCalibrator` 只分析两个 `TrialResult`，reference 固定 observed |
| `MetricExtractor` | `irsi/execution/metric_extractor.py` | 已实现 |
| 五个 `ExpertRole` | `irsi/experts/*/expert.py` | 已实现 |
| `PromptBuilder` | `irsi/prompting/builder.py` | 已实现 |
| `ExpertRuntime` / `NativePromptRuntime` | `irsi/runtime/native_prompt_runtime.py` | 已实现；渲染 prompt 并记录 prompt_hash / skill_ids |
| `RuntimeFacade` | `irsi/runtime/facade.py` | 已实现 |
| `ReportBuilder` / `StepReport` / `RoundReport` | `irsi/reporting/report_builder.py` | 已实现；从 `ExperimentRecordStore` 生成 report |
| `CommitRecorder` | `irsi/git/commit_recorder.py` | 已接入 Orchestrator/CLI；keep 提交 trial config + step report，discard/crash 只提交 step report |
| `HITTAudit` | 无 | 暂缓 |

**结论**：第一阶段剩余的是 **EnvironmentExpert、OpenJiuwen runtime 与真实远端运行**；CLI / Orchestrator / RoundController / ContextBuilder / TrialExecutor / NeutralityChecker / BaselineReference / ReportBuilder / ObservationPatchManager / NativePromptRuntime / CommitRecorder / EnvironmentSnapshot 已落地。

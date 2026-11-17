# 运行时知识库设计（第一阶段）

日期：2026-11-17  
定位：运行时知识库不是 skill 库，而是**实验记录、证据与查询接口**。  
skill 库回答“怎么做/为什么”，运行时知识库回答“过去发生了什么、结果如何、下一步参考什么”。

---

## 1. 数据模型

### `ExperimentRecord`：核心字段 + 可选字段

一条实验记录对应一个阶段或一个 trial。第一阶段只强制核心字段：

```text
record_id          # store 生成
round_id
step_id
stage
hypothesis_id      # 可为空
overrides          # baseline 可为 {}
metric             # crash 可为 null
status             # baseline / keep / discard / crash
detail
timestamp
```

推荐字段：

```text
surface
baseline_metric
gates              # gate name, passed, detail
artifacts          # config / log / metrics paths
```

可选 / 后加：

```text
commit
rollback
prompt_hash
skill_ids
evidence           # engaged, numeric hash, peak memory
```

建议用 JSON 可序列化结构，写入 `records.jsonl`。`record_id` 和 `timestamp` 可由 store 在缺失时自动生成。

---

## 2. 写入接口

### `ExperimentRecordStore`

职责：追加记录、读取记录、汇总 round。

```python
class ExperimentRecordStore(Protocol):
    def append(self, record: ExperimentRecord) -> ExperimentRecord: ...
    def get(self, record_id: str) -> ExperimentRecord | None: ...
    def recent(self, limit: int = 10, *, round_id: str | None = None) -> list[ExperimentRecord]: ...
    def query(
        self,
        *,
        round_id: str | None = None,
        status: str | None = None,
        surface: str | None = None,
        stage: str | None = None,
        limit: int | None = None,
    ) -> list[ExperimentRecord]: ...
    def summary(self, round_id: str) -> RoundSummary: ...
```

`RoundSummary` 建议包含：

```text
round_id
baseline_metric
best_record
counts: keep / discard / crash
steps: list[ExperimentRecord]
```

原则：

- append-only，不原地修改历史。
- 失败也记录，不删除。
- 不自动晋升知识；晋升由后续审计/人审决定。

---

## 3. 读取接口

### `RuntimeKnowledgeReader`

职责：只读查询，供编排和专家使用。

```python
class RuntimeKnowledgeReader(Protocol):
    def bundle(self, *, round_id: str | None = None, limit: int = 10) -> KnowledgeBundle: ...
    def best(self, surface: str) -> ExperimentRecord | None: ...
    def failures(self, surface: str, limit: int = 10) -> list[ExperimentRecord]: ...
    def recent(self, limit: int = 10, *, round_id: str | None = None) -> list[ExperimentRecord]: ...
```

`KnowledgeBundle` 建议包含：

```text
records
best_record
failures
```

它不是 skill bundle；它只提供运行时证据。

---

## 4. 由谁调用

| 角色/组件 | 调用 | 用途 |
|---|---|---|
| `Orchestrator` | `ExperimentRecordStore.append` | 每阶段/每 trial 后写入记录 |
| `RoundController` | `RuntimeKnowledgeReader.best` / `recent` | 选择 baseline、下一轮参考 |
| `ContextBuilder` | `RuntimeKnowledgeReader.bundle` | 组装 `StageContext.records` |
| `DecisionExpert` | 只读 `StageContext.records` | 参考历史实验提出/排序假设 |
| `ArchiveReportExpert` | 只接收 `Judgment`；记录由 Orchestrator 写入 | 不直接写 store |
| `ReportBuilder` | 读 `LedgerStore` / `ExperimentRecordStore` | 生成 step/round report |
| `HITTAudit`（暂缓） | 读 `ExperimentRecordStore` | 人审结果与知识沉淀 |

关键边界：

- **专家不直接写运行时知识库**；写入由 Orchestrator / runtime 做。
- **DecisionExpert 不直接查询 store**；它通过 `ContextBuilder` 得到 `StageContext.records`。
- **ExperimentRecordStore 与 LedgerStore 分工**：LedgerStore 是原始追加事件/决策账本；ExperimentRecordStore 是语义化实验记录。
- **运行时知识库不控制流程**；它只提供证据。

---

## 5. 与 skill 库的区别

```text
skill 库：怎么做、为什么、约束、事实
运行时知识库：做过什么、结果如何、证据是什么
```

Skill 由 `SkillResolver` 选择并注入 prompt；运行时记录由 `ContextBuilder` 读取并注入 `StageContext`。两者不能混成一个“知识 bundle”。

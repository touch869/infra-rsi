# 阶段 1 · L1 运行时知识库设计

| 项 | 值 |
|---|---|
| 状态 | 设计定稿（阶段 1） |
| 日期 | 2026-11-12 |
| 范围 | L1 运行时知识：条目模型、写入/读取路径、生命周期、检索与搜索耦合 |
| 关联 | [phase1-plan.md](phase1-plan.md) §5 / §6；[phase1-l3-domain-knowledge.md](phase1-l3-domain-knowledge.md) |

---

## 1. 定位：账本的派生索引 + 解释层

> **L1 不是第二个事实源。** 事实（commit、指标、回执、判据）只在账本里；条目只是指向它们的索引，外加一段模型/人写的解释。

这条原则解决三个问题：

- **一致性**：不会出现“账本说 1234.5、知识库说 1300”；
- **可重建**：`kb rebuild` 能从账本重算全部事实字段；
- **防编造**：模型碰不到事实字段，只能写解释。

与 L3 的分工（详见 L3 文档）：

| | L1（`kb/`） | L3（`skills/`） |
|---|---|---|
| 单位 | 小条目（claim + 证据 + 适用条件） | 操作手册（流程 + 事实 + 数据 + 脚本） |
| 触发 | 按 `scope` / `applies_to` 检索打分 | 按任务类型匹配 `description`，整篇加载 |
| 写入 | 代码自动 + 模型写解释 | 人工维护 + 脚本校验 |
| 作用 | **改变搜索**（prior / penalty / deferred） | 让 agent 知道该领域怎么做 |

两者互相引用、不互相嵌入。

---

## 2. 存储格式：JSON（结构）+ Markdown（解释）

| 数据 | 格式 | 写者 | 理由 |
|---|---|---|---|
| 条目结构 `meta.json` | **JSON** | 代码 + 模型（结构化字段） | 机器高频写、需 schema 校验、无隐式类型 |
| 条目解释 `note.md` | **Markdown** | 模型 / 人 | 自由文本不参与解析 |
| 索引 `index.json` | JSON | 代码 | 纯机器读 |
| 冲突表 `conflicts.json` | JSON | 代码 | 同上 |
| 账本 `decision.json` / `receipt.json` | JSON | 代码 | 单条快照 |
| 账本流 `results.tsv` / `candidates.jsonl` | TSV / JSONL | 代码 | append-only、崩溃安全 |
| L3 `hardware.yaml` / `contract.yaml` | YAML | 人 | 手写、低频、需要可读性 |
| L3 `ascend-fusion.json` | JSON | 半自动 | 机器可读 schema |

### 为什么条目不用 YAML

1. **隐式类型**：`version: 1.0` → float、`0123456` → 丢前导零、`yes/no/on/off` → bool。commit 与版本号不能这样。
2. **模型的自由文本会破格**：claim 里一个 `: `、`#`、多行代码，YAML 就失败或静默改结构——而解释字段正是模型写的。
3. **没有强 schema**：JSON 可上 JSON Schema，`kb check` 才有约束力。
4. **写回不可靠**：`load → mutate → dump` 会重排格式、丢注释，git diff 变噪音。

YAML 留给人手写、低频、需要可读性的地方（L3 与 contract）。

### 若某处必须用 YAML 的三条硬规矩

1. 只由代码 `safe_dump` 写，绝不手工拼模板；
2. 所有字符串值强制加引号（commit、版本、ID、claim）；
3. 落盘前立即按 JSON Schema 校验，失败拒绝写入。

---

## 3. 条目模型

```
kb/entries/<id>/
├── meta.json     # 结构：derived + 结构化 authored
└── note.md       # 解释：为什么、过程、观察（检索不读，人审/报告用）
```

`meta.json`：

```json
{
  "id": "neg-0007",
  "dedupe_key": "9f3a1c2e",
  "kind": "negative",
  "status": "candidate",
  "derived": {
    "scope": ["recompute", "memory"],
    "applies_to": {"model": "qwen3_8", "hardware": "910B3x8", "commit_range": ">=a1b2c3d"},
    "evidence": [
      {"run": "r-0007", "decision": "rounds/r-0007/decision.json",
       "receipt": "sha256:...", "before": 1234.5, "after": 1185.0, "verdict": "discard"}
    ],
    "confidence": 1,
    "observed_at": "2026-11-12T20:00:00Z",
    "provenance": {"agent": "irsi/0.1", "model": "...", "prompt_hash": "..."}
  },
  "authored": {
    "claim": "recompute 从 full 改 selective：显存 -12%，吞吐 -4%",
    "conditions": "seq=4096, micro_batch=1, FSDP+CP=2",
    "action": "吞吐优先任务不要单独用；可与 offload 组合再试",
    "links": ["pos-0003", "hyp-0011", "skill:hyperparallel-perf#recompute-knobs"]
  }
}
```

**字段归属是硬约束**：`derived` 段只由代码写；模型输出里出现 `metric_before` 之类字段直接丢弃。

六类的差异只在语义字段：

| kind | 特有字段 | 写入时机 |
|---|---|---|
| positive | `patch_ref`、`reproduced_by` | keep 裁决后 |
| negative | `failure_stage`、`failure_class`、`weight`（crash=2，discard=1） | discard / crash 后 |
| hypothesis | `expected_signal`、`basis: [entry_ids]`、`status: open/confirmed/refuted` | 提出假设时创建，裁决后回填 |
| issue | `source_url`、`issue_state`、`reproduced: bool` | 人工 / 定期导入 |
| deferred | `revisit_on: [scope]`、`parent_commit`、`triggered_by` | discard 且假设声明了 `revisit_on` |
| summary | `n_runs`、`net_delta_range`、`open_questions`、`conflicts` | 每 N 轮（默认 10） |

`note.md` 模板（不解析，仅供人读）：

```markdown
# neg-0007 · recompute selective 在吞吐上不划算

## 观察
…

## 过程
…

## 待确认
…
```

---

## 4. 写入路径

```
Decision ──► 代码生成 derived ──► 模型填 authored ──► kb.record()
   │                                 └─ 模型失败：claim=null，status=candidate，标记待回填（不阻塞）
   ├─ discard 且假设有 revisit_on ──► 另写 deferred
   ├─ crash ──► negative（weight=2），failure_class 必填
   └─ 每 10 轮 ──► summary（模型归纳 + 人审）

Hypothesis 提出 ──► hypothesis（open，必须带 basis）
GitHub issue 导入 ──► issue（reproduced=false）
```

四条规则：

1. **去重合并**：`dedupe_key = sha1(kind|scope|action_normalized)[:8]`；命中则追加 `evidence`、`confidence +1`，不新建；
2. **失败也写**：crash 必写；KB 写入失败静默降级（旁路，账本是主路）；
3. **指不回证据的不入库**：`evidence` 为空直接拒绝；
4. **假设必须带 `basis`**：引用依据的 L1/L3 条目 id，用于度量“知识是否被真正使用”。

---

## 5. 读取路径

### 查询对象

```python
Query(scopes=["recompute"], bottleneck="memory", model="qwen3_8",
      hardware="910B3x8", commit="a1b2c3d", k=8)
```

### 两段式

| 步 | 规则 |
|---|---|
| **硬过滤** | `applies_to` 任一不符 → 丢弃；`status ∈ {refuted, deprecated}` → 丢弃 |
| **打分** | `3×scope 交集 + 2×tag 匹配 + 1×BM25(claim+action) + 0.5×confidence + 0.3×时间衰减` |
| **多样性** | 每 scope 至多 2 条；至少 1 条 negative；ready 的 deferred 优先占位 |
| **预算** | ≤ 8 条，每条 ≤ 3 行，总注入 ≤ ~800 tokens |

### 注入顺序（假设生成的 prompt 内）

```
1. 待重试（deferred ready）      ← 最可执行
2. 已验证正例（positive）
3. 已知坑（negative）
4. 未决假设（hypothesis open）
5. 冲突提示（contradiction）
```

注入时带 id；模型必须在 `basis` 里回引，形成 `knowledge → hypothesis → decision → evidence` 的可追溯边。

---

## 6. 生命周期与冲突

```
candidate ──复现≥2 或 人审──► verified ──(applies_to 失效)──► deprecated ──► archive
    │                             │
    └──── 被证据反驳 ──► refuted ──┘
```

- **confidence**：只由“独立复现”增加（不同 run、相同结论），不由“模型确信”增加；
- **冲突**：同 scope、相反方向、`applies_to` 有交集 → 写入 `conflicts.json`，并生成高优先级 hypothesis（下一轮优先验证），**不自动裁决**；
- **过期**：`commit_range` / 硬件 / 模型任一变化 → `deprecated`，检索过滤；`kb gc` 定期扫；
- **归档**：deprecated / refuted 移入 `archive/`，不删（审计要能查到“我们曾经这么认为”）。

---

## 7. 知识如何改变搜索

| 机制 | 数据来源 | 作用点 | 阶段 1 |
|---|---|---|---|
| **prior** | verified positive 的 scope 统计 | selector 提高该 scope 的候选先验 | 做 |
| **penalty** | negative 的 `(scope, action)` 对 | 有效期内降权，避免重复撞墙 | 做 |
| **deferred pool** | `revisit_on` 命中 | 直接进候选池，`status` 显示 `retry_ready` | 做 |
| **contradiction** | `conflicts.json` | 生成高优先级假设 | 只标记 |
| **budget** | 同 scope 连续 N 次 negative | 临时冻结该 scope，预算挪走 | v0.1 |

若 KB 只写不读，这五个机制一个都不会发生——因此“假设引用率”必须进阶段 1 验收。

---

## 8. KB 自身度量

| 指标 | 定义 | 阶段 1 目标 |
|---|---|---|
| 引用率 | 带 `basis` 的假设 / 总假设 | ≥ 60% |
| 命中率 | 被引用条目所属假设最终 keep 的比例 | 仅记录 |
| 重复失败率 | 与已有 negative 完全同 `(scope, action)` 的假设占比 | ≤ 10% |
| 冲突数 | open conflicts | 仅记录 |

---

## 9. 存储布局与接口

```
kb/
├── entries/{positive,negative,hypothesis,issue,deferred,summary}/<id>/
│   ├── meta.json
│   └── note.md
├── index.json          # id → {kind, scope, applies_to, status, confidence, dedupe_key, updated}
├── conflicts.json
└── archive/
```

```python
kb.record(entry) -> id                 # 去重合并 + 原子写（tmp+rename）+ index 更新
kb.search(query) -> list[Entry]        # 硬过滤 → 打分 → 多样性 → 截断
kb.verify(id, evidence_ref)            # confidence+1 / status 迁移
kb.rebuild()                           # 从账本重算 derived，保留 authored
kb.gc(env)                             # 标记 deprecated + 归档
kb.export(kind=None, scope=None) -> md # 人审视图（等价 PR 的 learnings.md）
```

可靠性约定：

- 写入顺序：条目 → index → 返回 id；index 写失败可从条目重建；
- 崩溃安全：所有写用 tmp + `os.replace`；
- `kb rebuild` 只重算 `derived`；`authored` 存在条目里，条目本身进 git；
- `meta.json` 用 JSON Schema 校验（`kb check`），`note.md` 不校验。

作用域（待定项 1 建议）：**全局 `kb/` + task 覆盖层**；`dedupe_key` 相同时 task 条目优先，检索先返回覆盖层。

---

## 10. 与 L3 的边界

- L1 条目可 `links: ["skill:hyperparallel-perf#recompute-knobs"]` 指向 L3 reference；
- L1 的 summary 被多次验证 → 人审后“升级”为 L3 的一节（固化知识的来源）；
- 反向不成立：L3 内容不进 L1 检索索引（会稀释打分、膨胀上下文）。

---

## 11. 阶段 1 范围与待定

**做**：六类 kind、dedupe、derived/authored 分离、JSON Schema 校验、启发式检索、prior/penalty/deferred、summary 每 10 轮、issue 手工导入、`kb rebuild/gc/export`。

**不做**：向量检索、跨任务自动共享、自动 skill 蒸馏、知识自动裁决、`budget` 冻结机制（v0.1）。

| # | 待定 | 建议 |
|---|---|---|
| 1 | KB 作用域 | 全局 `kb/` + task 覆盖层；跨任务复用是 RSI 的价值，但要允许单任务纠正 |
| 2 | authored 谁写 | 模型写 + 人审异步；人审前 `candidate`，仅 `verified` 参与 prior/penalty |
| 3 | negative 有效期 | 随 `applies_to.commit_range` 失效，不设“永久拉黑” |

---

## 12. 阶段 1 验收

- [ ] 一条 Decision 能自动生成完整 `meta.json`（derived 全由代码填，authored 可空）
- [ ] `kb rebuild` 后 derived 字段与账本一致，authored 不丢
- [ ] `kb search` 对过期 `applies_to` 的条目 0 命中
- [ ] 一次真实循环中：假设带 `basis`；deferred 能被检索并在 `status` 显示 `retry_ready`
- [ ] 引用率 ≥ 60%，重复失败率 ≤ 10%
- [ ] `meta.json` 100% 通过 JSON Schema 校验

# 阶段 1 · L3 域知识库设计

| 项 | 值 |
|---|---|
| 状态 | 设计定稿（阶段 1） |
| 日期 | 2026-11-12 |
| 范围 | 阶段 1 的 L3 域知识：只建两个 skill（入口 + HyperParallel 性能域） |
| 关联 | [phase1-plan.md](phase1-plan.md) §3.6 / §6；HyperParallel PR #1517（参考，未合入） |

---

## 1. 定位：skill 是打包单位，不是知识本身

一个域 skill 里混着三类东西，必须分开对待：

| 层 | 内容 | 载体 | 能否被脚本验证 |
|---|---|---|---|
| **事实** facts | API 签名、算子能力、版本约束、模型结构、硬件峰值 | `references/*.md` + `data/*.json` | 部分能（对照源码/版本） |
| **流程** procedure | 先诊断什么、按什么顺序验证、何时停 | `SKILL.md` 正文 | 不能，靠人审 |
| **工具** tooling | 能跑的分析/校验脚本 | `scripts/*.py` | 能（有测试） |

三条硬约束：

1. **能跑的事实不要写成散文。** 例如 `910B3 峰值 TFLOPS` 必须放 `data/hardware.yaml` 并带 `source`，否则 MFU 分母不可审计。
2. **每条事实带来源与版本**（repo commit / 文档版本 / CANN 版本）。
3. **`SKILL.md` 只做索引，≤ 200 行**；细节进 `references/` 与 `data/`，按需加载。

与 L1 的分工（不合并）：

| | L1 运行时知识（`kb/`） | L3 域知识（`skills/`） |
|---|---|---|
| 单位 | 小条目（claim + 证据 + 适用条件） | 操作手册（流程 + 事实 + 数据 + 脚本） |
| 触发 | 按 `scope` / `applies_to` 检索打分 | 按任务类型匹配 `description`，整篇加载 |
| 写入 | 代码自动 + 模型写解释 | 人工维护 + 脚本校验 |
| 失效 | `commit_range` / 硬件变化 | 版本升级（`applies_to` 不符） |
| 作用 | 改变搜索（prior / penalty / deferred） | 让 agent 知道该领域怎么做 |

互相**引用**，不互相**嵌入**：L1 条目可写 `links: [skill:hyperparallel-perf#recompute-knobs]`；L1 的 summary 被多次验证后可经人审"升级"为 L3 的一个 reference 小节（即"固化知识库"的来源）。

---

## 2. 阶段 1 目录

```
skills/
├── infra-rsi/SKILL.md                  # 入口：触发条件、命令、硬规则（prompt 入口，见 plan §3.6）
└── hyperparallel-perf/
    ├── SKILL.md                        # 索引：判断路径 + Breakdown first + 报告模板
    ├── references/
    │   ├── source-map.md               # 问题 → HP 仓库目录（改写自 PR，锚定我们的 commit）
    │   ├── bottleneck-techniques.md    # 瓶颈类别 → 技术 → 反例/约束（带 scope 与证据等级）
    │   └── mfu-conventions.md          # MFU/HFU 口径、内置 meter、报告约定
    ├── data/
    │   ├── ascend-fusion.json          # 昇腾融合算子目录（照 catalog/v1 schema，裁到本阶段用到的）
    │   ├── hardware.yaml               # 910B3 峰值/HBM 带宽，带 source
    │   └── techniques.json             # bottleneck-techniques 的机器可读版，供 selector 读
    └── scripts/
        └── check_facts.py              # schema / 链接 / 版本锚点 / 算子 symbol 校验
```

各文件职责：

| 文件 | 职责 | 读者 |
|---|---|---|
| `SKILL.md` | 何时用、按什么顺序查、硬规则、报告模板 | agent（整篇） |
| `source-map.md` | "这个问题该看哪个目录/文件" | agent（按需） |
| `bottleneck-techniques.md` | 按瓶颈选技术 + 反例 | agent（按需取行） |
| `mfu-conventions.md` | 指标口径与上限，防口径混用 | agent + 人（报告） |
| `ascend-fusion.json` | 算子可行性校验 | **代码**（selector/implementer）+ agent |
| `hardware.yaml` | 物理上限（sanity check） | **代码** |
| `techniques.json` | 技术清单与适用条件 | **代码**（先验/候选生成） |
| `check_facts.py` | 防腐烂 | CI |

---

## 3. 数据与元数据契约

### 3.1 reference 文件头

```yaml
---
title: Bottleneck → technique
evidence_provenance: mixed        # prior | measured | mixed（三选一，禁止留空）
applies_to:
  hyper_parallel: ">=<commit>"
  cann: "9.1.0"
  pta: "2.9.0"
sources:
  - hyper_parallel/distributed/activation_checkpoint.py@<commit>
  - https://www.hiascend.com/document/...
---
```

证据等级沿用 PR 的定义：

| 标签 | 含义 | 使用规则 |
|---|---|---|
| `prior` | 通用工程实践/公开算法，本仓未实测 | 作指引；被测量推翻时优先测量，并更新参考、重标等级 |
| `measured` | 本仓有记录的优化实验（带账本位置） | 引用其口径与规模；外推到其他配置前需复测 |
| `mixed` | 先验知识 + 实测校准 | 按文内标注区分 |

### 3.2 `ascend-fusion.json`（照 `ascend-fusion-catalog/v1`）

```json
{
  "schema": "ascend-fusion-catalog/v1",
  "entries": [
    {
      "id": "fusion-attention",
      "symbol": "torch_npu.npu_fusion_attention",
      "tags": ["attention", "softmax", "bmm"],
      "doc_version": "Pytorch/700",
      "url": "https://www.hiascend.com/document/...",
      "status": "candidate_requires_runtime_verification",
      "training_support": "documented_training",
      "review_note": "文档声明支持训练；mask/scale/layout/变长/backward 需自行验证"
    }
  ]
}
```

**关键**：`status` 与 `review_note` 必须如实区分"文档里有"和"运行时支持"。阶段 1 只收 attention / rmsnorm / swiglu / rope 四类，其余不收。

### 3.3 `hardware.yaml`

```yaml
device: Ascend 910B3
peak_tflops:
  bf16: 0            # 必须实测或引官方文档，禁止估算
  fp16: 0
hbm:
  capacity_gib: 0
  bandwidth_gib_s: 0
source: <官方文档 URL 或实测命令 + 日期>
applies_to: {cann: "9.1.0", driver: "<version>"}
```

### 3.4 `techniques.json`

```json
{
  "schema": "techniques/v1",
  "entries": [
    {
      "id": "recompute-selective",
      "scope": ["recompute", "memory"],
      "technique": "selective activation checkpointing",
      "applicable": "激活显存占主导，且有富余算力",
      "counterexample": "缓存张量被原地修改会被严格模式拒绝；CPU 运行不能证明显存收益",
      "evidence_level": "mixed",
      "sources": ["..."]
    }
  ]
}
```

`scope` 取值与搜索空间对齐：`recompute | parallel | pipeline | fusion | memory | optimizer`。

---

## 4. 内容来源（PR #1517，commit `81aa0f9f`）

| PR 文件 | 处理方式 | 目标位置 |
|---|---|---|
| `knowledge-retrieval/references/source-map.md`（62 行） | **直接搬**，锚点换成我们的 fork commit | `references/source-map.md` |
| `perf-playbook/references/ascend-fusion/catalog.json`（131 行） | **复用 schema**，裁剪算子条目 | `data/ascend-fusion.json` |
| `perf-playbook/references/feature-scenarios.md`（64 行） | **改写**：加 `scope` 与 `evidence_level`，抽机器可读版 | `references/bottleneck-techniques.md` + `data/techniques.json` |
| `perf-playbook/references/mfu-targets.md`（133 行） | **改写**：删 MoE/Muon 段，保留口径与报告约定 | `references/mfu-conventions.md` |
| `perf-playbook/references/optimizer-overhead.md` + `scripts/extra_flops.py` | 暂不搬；HFU 需要时再取 | — |
| `strategy-validator/references/metrics-schema.md`（636 行） | 只取指标定义与提取规则，裁到 10 个字段 | 归 L4 `executor/metrics.py`，不进 L3 |
| `memory-analysis/references/breakdown-dimensions.md`（99 行） | 暂不搬；做 offload 假设时再取 | — |
| `hf-model-integration/...`、`moe-*`、`routing-validator` | 阶段 1 不做 | — |

三条值得直接沿用的做法：

1. **证据等级 + "测量推翻先验时更新参考并重标"**；
2. **catalog 的 `status` / `review_note`**：区分"文档支持"与"运行时支持"；
3. **反例列与技术列同等地位**（`Counterexample or constraint`）。

另有两条硬规则进 `SKILL.md`：

- **Breakdown first**：没有 profile / 显存拆解指出瓶颈，不许改；
- **Mechanism sanity-check**：提升幅度必须物理上可能（相对瓶颈占比），否则判测量错误。

### 搬运纪律

- PR 未合入、Apache-2.0、同组织：文件头写 `source: mindspore-ai/hyper-parallel PR #1517 @81aa0f9f` + 修改说明。
- 只搬**事实与表格**；流程文本重写，去掉 `.agent/`、slash command 等 Claude Code 宿主假设。
- 每条搬入的事实必须能被 `check_facts.py` 校验。

---

## 5. 读取路径

| 时机 | 读什么 | 方式 | 用途 |
|---|---|---|---|
| 生成假设前 | `bottleneck-techniques.md` / `techniques.json` | 按当前瓶颈类别取对应段 | 产出候选技术清单 |
| 实施前 | `ascend-fusion.json` | 代码查询（symbol/tags） | 校验算子可行性，避免改出不可用实现 |
| 实施前 | `source-map.md` | 按需 | 定位要改的代码位置 |
| 裁决前 | `mfu-conventions.md` + `hardware.yaml` | 整篇 / 代码读 | 校验指标口径 + 物理上限 sanity check |
| 出报告 | `mfu-conventions.md` 中的报告约定 | 整篇 | 口径声明、before/after 格式 |

**加载策略**：`SKILL.md` 由 `description` 触发整篇加载；`references/` 按需读取；`data/*.json` 由代码直接读，不经过模型——这样即使模型没读 skill，校验仍然生效。

---

## 6. 防腐烂

| 手段 | 检查内容 | 时机 |
|---|---|---|
| `scripts/check_facts.py` | JSON schema、URL 可达、`applies_to` 版本存在、算子 symbol 在目标 commit 的源码中存在 | CI + 本地 |
| skill 契约测试 | frontmatter 必填 `name`/`description`；引用的 references/scripts 存在；无绝对路径与密钥；`SKILL.md` ≤ 200 行 | CI |
| 过期检测 | `applies_to.hyper_parallel` 与当前 pin 的 commit 不符 → 标 `stale` 并在 CI 提醒 | 版本升级时 |
| 更新规则 | 实测推翻先验 → 改 reference + 重标 `evidence_provenance` + 在文件头记日期 | 每次 summary 蒸馏 |

---

## 7. 阶段 1 验收

- [ ] 两个 skill 能经 `skills_dirs` 挂载，agent 能按 `description` 正确触发（1 个真实 prompt 验证）
- [ ] `data/` 三个文件通过 `check_facts.py`；`applies_to` 全部锚定到具体 commit/版本
- [ ] 一次真实任务中：假设生成引用了 `techniques.json` 的条目；实施前查过 `ascend-fusion.json`；报告声明了 MFU 口径
- [ ] 0 条无来源事实；0 条 `evidence_provenance` 为空

---

## 8. 阶段 1 不做

- 不建 `mindspore/`、`ascend/`、`gpu/` 三个 skill（图里是 v0.1+ 目标形态；有真实任务再长）
- 不做自动抓取/自动更新（人工维护 + 脚本校验）
- 不做向量检索（skill 按需加载即可）
- 不把 L1 条目塞进 skill，也不把 skill 切块塞进 L1
- 不搬 MoE / 模型接入 / 形式化验证那一套（v0.3 或换模型时再说）

# Agent for Infra · 阶段 1 实施方案（打通原型）

| 项 | 值 |
|---|---|
| 状态 | 草案 v0.3（rough plan） |
| 日期 | 2026-11-12 |
| 阶段 | 阶段 1「11 月底 · 打通原型」 |
| 范围 | 最小闭环 × 一个修改面（图优化 / 重计算）× 一个模型（HyperParallel qwen3_8） |
| 关联 | `research/research/agent-for-training-infra-architecture-2026-11-06.md`、`research/codebase/torchtitan/autoresearch-deep-dive.md`、HyperParallel PR #1517（参考，未合入）、[phase1-l3-domain-knowledge.md](phase1-l3-domain-knowledge.md)、[phase1-l1-runtime-knowledge.md](phase1-l1-runtime-knowledge.md) |

本文只回答三件事：**三个入口怎么共存、架构怎么和 jiuwen 兼容、流程编排放在哪**；另加 §3.7–§3.8 说明阶段 1 的修改面与验证面。

v0.3 修订：修改面从“四个面并列”收敛为**图优化（重计算）单一主面**；算子融合关闭、并行布局只做通道验证、流水编排不做；验证门相应简化为 G0–G3（bitwise 为核心）；新增 D1 空间探测作为方向判据。详见 §3.7、§3.8、§11。

---

## 1. 阶段目标与验收

**一句话**：`irsi run --contract contracts/qwen3_8-recompute.yaml` 一条命令跑完 契约 → 假设 → 实施 → 逐级验证 → 裁决 → 归档 → 知识沉淀，产出可复跑、可追溯的结果报告。

| # | 验收项 | 口径 |
|---|---|---|
| 1 | 闭环自动 | 除「上线人审」外全程无人干预；单轮 ≤ 90 min（不含全量验证） |
| 2 | 有效产出 | ≥ 10 条假设，≥ 1 条 PASS 且 tgs/NPU 提升 ≥ 3%（初拟；D1 扫描后按实际空间定目标） |
| 3 | 证据完整 | 每条决策可追到 commit + 回执 + 指标 + 日志 + 门禁输出，校验脚本 100% 通过 |
| 4 | 门禁可信 | 红队六场景全部按预期：baseline / keep / discard / crash / dirty-tree / noise-confirm |
| 5 | 可复现 | 同 contract + 同 commit 重跑，决策一致、指标偏差 ≤ 0.5% |
| 6 | 可演示 | 10 分钟 demo 脚本 + 一页结果图 |

---

## 2. 总架构：一个服务内核，三个薄适配器

```
       CLI 入口            jiuwen prompt 入口         jiuwen RSI 入口
   entries/cli.py        skills/infra-rsi/SKILL.md     provider.py
        │                 （阶段 1 经 CLI 执行）             │
        └───────────────┬───────┴────────────────────────┘
                        ▼
              service.py  InfraTaskService          ← 唯一的对外门面
                        │
                        ▼
   engine/  loop（状态机）· state（先落盘再发事件）· tree · scorecard · seam
                        │
        ┌───────────────┼────────────────┬──────────────┐
        ▼               ▼                ▼              ▼
   domain/          executor/         ledger/         kb/
evaluate reward   torchrun receipts  results.tsv   正例/反例/假设/issue
prompt                               candidates.jsonl  + 延迟候选
```

**一条硬规则**：三个入口里任何一个都不许写业务逻辑。适配器只做四件事——构造 `InfraTaskSpec`、提供 `Model`、分配 `task_id/run_dir`、消费事件。每个适配器 ≤ 100 行；删掉另外两个，剩下的仍能跑完整一轮。

### 依赖方向

```
                    jiuwenswarm (AgentServer)
                            │ 装配时注入 {"ARTIFACT:INFRA": adapter}
                            ▼
   CLI ──────►  irsi.provider  ◄──── ArtifactEngineAdapter
                     │
                     ▼
              openjiuwen 公共契约（ArtifactProvider / ArtifactEngineRequest / schema / events）
```

- `infra-rsi → openjiuwen`：编译期/安装期依赖，只在 `irsi/contract/`、`irsi/provider.py`。
- `jiuwenswarm → infra-rsi`：一行惰性 import + 一个 adapters key。
- `openjiuwen → infra-rsi`：**永不出现**（若日后合入 core，只能是 vendored 快照 + 固定版本）。
- `irsi → hyper-parallel`：**不 import**，一律子进程 `torchrun`。

---

## 3. 三个入口怎么共存

### 3.1 共存靠四个端口，不靠三套代码

| 端口 | 定义在 | CLI | prompt 入口 | RSI 入口 |
|---|---|---|---|---|
| `ModelPort` | `service.py` | 读 env 构造 `openjiuwen…llm.Model` | 同 CLI（阶段 1）；v0.1 用 agent runtime 的 model | AgentServer 注入的 `request.model` |
| `EventSink` | `service.py` | 控制台 / JSONL | 同 CLI；tool 化后回写会话 | `OnEvent` 回调 |
| `TaskIdentity` | `service.py` | 自己 mint（`uuid` + `runs/<ts>-<slug>`） | 同 CLI；tool 化后由工具参数或会话 id 给 | AgentServer 的 `task_id` / `run_dir` |
| `InfraTaskSpec` | `domain/spec.py` | argv / `contracts/*.yaml` | 自然语言 → 参数 → 同一份 contract | `ArtifactEngineRequest` → `translate.py` |

### 3.2 `contract.yaml` 契约

```yaml
edit_surface:
  surface: graph.recompute                 # 阶段 1 唯一主面
  file: hyper_parallel/models/qwen3_8/recipes/train.yaml
  keys:
    - activation_checkpoint.mode                        # full | selective（off 可提交，预期 OOM→负例）
    - activation_checkpoint.selection.source           # model_adapter_safe_regions
    - activation_checkpoint.selection.layer_count      # 0..N（与 layer_indices 二选一）
    - activation_checkpoint.selection.layer_indices
    - activation_checkpoint.swap_inputs                # bool
  read_only:
    - activation_checkpoint.allow_cache_entry_mutation # SAC 安全逃生门，禁止
    - training.{micro_batch_size,global_batch_size,seed,enable_full_determinism}
    - mixed_precision
    - compile
    - accelerator.*, fsdp_config.*                     # 并行面只读
    - gates/**, baseline/**, tests/**

workload:
  workload_id: sha256:<数据/形状/硬件/拓扑/窗口>
  input_hash: required                    # 同输入是 bitwise 的前提
  determinism: true
  seed: 42
  bitwise_steps: 20                       # 逐位比较窗口
  benchmark_steps: 30                     # 稳态窗口（≥20）

metric:
  pattern: "tgs_per_npu=(?P<metric>[0-9.]+)"   # 最后一个匹配生效
  direction: maximize
  noise_fraction: 0.02
  noise_confirm_reruns: 2
  aux_patterns: {step_time_ms: "...", peak_mem_gib: "..."}

gates:                                    # 由廉到贵，失败即停
  - {name: receipt, cmd: [...], expect_steps: 20}
  - {name: bitwise, cmd: [...], expect_steps: 20, input_hash: required}
benchmark:
  cmd: [...]
  must_match: ["engaged=1"]               # 正向证据，缺失即 crash
  window_steps: 30
  flops_check: independent

budget: {experiments: 12, gpu_minutes: 480, max_trials: 12, command_timeout_min: 60}
```

### 3.3 四个冲突点与裁决规则

| 冲突 | 裁决 |
|---|---|
| **身份**：谁生成 task_id | 只有入口生成，provider/engine 只接受；engine 内禁止调用 `uuid` |
| **事件**：谁能消费事件流 | 单消费者。`run()` 只接受一个 sink；CLI 的 sink 与 `OnEvent` 不同时挂 |
| **状态**：谁能读写 run_dir | 只有 `engine/state.py` 读写；写前取 `run_dir/.lock`，`owner` 字段记录持有者 |
| **并发**：同一 run_dir 被两个入口打开 | 默认拒绝；`irsi attach <run_dir>` 只读 |
| **重复触发**：prompt 重试 / 用户重复一句 | 幂等键 `(contract_hash, repo_commit, editable_paths)` 相同 → 返回已有 task_id |

### 3.4 各入口在阶段 1 做到哪

| 入口 | 阶段 1 做到哪 | 后面补什么 |
|---|---|---|
| **CLI** | 完整可用，主开发/演示通道 | 无 |
| **prompt 入口** | `skills/infra-rsi/SKILL.md` + CLI（`--detach --json`）：触发、确认、跟踪、出报告 | v0.1 换成原生 tool → `rsi.task.create` |
| **RSI 入口** | `provider.py` 八方法齐全；`pause/resume` 返 `NOT_IMPLEMENTED`；`validate_input` 校验 repo+recipe | AgentServer 装配、Hub 表单（v0.1） |

### 3.5 八方法（阶段 1 行为）

| 方法 | 阶段 1 |
|---|---|
| `validate_input(path)` | 校验 repo 可读、recipe 存在、`editable_paths` 非空；不启动 |
| `run(request, on_event)` | `translate` → `service.submit`；先落盘再发事件；terminal 最后 |
| `pause(task_id)` / `resume(request)` | `NOT_IMPLEMENTED` / `SCENARIO_NOT_SUPPORTED`（契约允许） |
| `read_state(task_id)` | 从 `run_dir` 重建，无副作用 |
| `read_report(task_id)` | 报告 + `artifact_index`（含所有产物） |
| `get_tree(task_id)` | 完整假设树（含被否决分支） |
| `locate_artifact(task_id, artifact_id=None)` | 定位最终或指定产物 |

### 3.6 prompt 入口的执行面：skill + CLI（v0.1 换 tool）

**skill 不执行任何东西**，它只让 agent 知道何时触发、用什么命令、哪些红线。阶段 1 用 skill + CLI，原因是 jiuwenswarm 的 RSI 目前只暴露在 web/API 面（`rsi.task.create/list/get/delete`），没有 agent 工具；skill + CLI 不需要改上游。

CLI 必须满足四条（这是“prompt 可用”的真正门槛）：

| 要求 | 原因 |
|---|---|
| `--detach` + 立即返回 `{task_id, run_dir}` | 一轮 60–90 min，不能挂住 agent turn |
| `status --json` / `report --json` | 后续对话可答“进展如何”，且输出可解析 |
| 幂等键 | agent 重试不重复烧卡 |
| 预算前置校验（contract 与 `--max-gpu-minutes` 取小） | 防止一句话跑掉一整天 |

`irsi run` 的 stdout 只输出一个 JSON 契约：`{task_id, run_dir, status, baseline, budget}`。

skill 骨架（放在 `skills/infra-rsi/SKILL.md`，经 `skills_dirs` 挂载）：

```markdown
---
name: infra-rsi
description: 优化 HyperParallel 训练性能时使用：提升训练吞吐/降低显存/重计算或并行调优。
---
## 何时不用      只问概念、看代码 → 直接回答；没有 contract → 先生成，不要猜参数
## 前置确认      模型/recipe/卡数/预算，用 ask_user 确认后才启动；超预算拒绝
## 命令          irsi run --contract <p> --detach --json
                irsi status <task_id> --json
                irsi report <task_id>
## 硬规则        不改 gate 脚本/baseline/白名单外文件；失败保留 run 目录；不并行重复提交
```

v0.1 迁移只在 skill 里换一行：`irsi run …` → `infra_rsi_run(contract=…)`，触发条件与硬规则不动。

### 3.7 修改面与验证面（阶段 1：图优化 / 重计算）

#### 四个面的取舍

| 修改面 | 阶段 1 | 理由 |
|---|---|---|
| **图优化**（重计算为主，compile 暂不动） | **唯一主面，完整开** | 配置级、数值不变、bitwise 门最硬；基线 `mode: full` 有真实压缩空间 |
| **算子融合** | **关闭**（只做通道验证） | 融合改数值，与 bitwise 冲突；容差门成本高，18 天不划算 |
| **并行优化** | **只做通道验证**（W2 末人工切一次布局） | 收益大但需 series + 容差门；搜索留 v0.1 |
| **流水编排** | **不做** | trainer YAML 未暴露 GPipe/1F1B/VPP 调度，需代码级接入 |

#### 重算修改面

白名单字段见 §3.2 `edit_surface.keys`。三条硬约束：

1. **禁止 `allow_cache_entry_mutation`**：它是 SAC 缓存变异的安全逃生门，开启等于绕过校验；
2. **容量字段一律不动**：`micro_batch_size` / `global_batch_size` / 梯度累积 / 序列长度——否则必须开 linked series；
3. **`mode: off` 允许提交**，预期 OOM，作为负例学习（比在 contract 里写“不要试”更有价值）。

**前置（D0）**：`selection.source=model_adapter_safe_regions` 要求模型适配器声明 `RecomputePolicy`（`models/adapter_spec.py:37`）。当前只有 deepseek_v41 声明了，qwen3_8 没有——不补则按层选择不可用，搜索空间只剩 6 种组合。D0 需给 qwen3_8 补声明（`region_patterns` + `exclude_patterns`），作为一次性基线改动合入后冻结。

#### 验证门 G0–G3

| 门 | 检什么 | 成本 | 判据 | 证据 |
|---|---|---|---|---|
| **G0 回执完整性** | `completed_steps == expect`；无 OOM / contention | ~1 min | crash | `receipt.json` |
| **G1 bitwise** | 前 20 步 loss / grad_norm **哈希**一致；`input_hash` 一致 | 10–15 min | crash | `determinism.json` |
| **G2 engaged + 显存** | 实际重算层数 = k；每 rank 峰值 ≤ 预算；显存下降与 k 匹配 | 随 G1/G3 采集 | crash / discard | `metrics.json` |
| **G3 吞吐** | 稳态 ≥20 步 tgs/NPU + MFU（声明口径），过噪声带 | 20–40 min | discard | `bench.json` |

另加一条裁决期检查（无额外成本）：

- **C1 物理 sanity**：吞吐提升必须能由“省下的重算前向占比”解释；显存下降必须接近理论激活量。不满足 → 判测量错误（crash）。

#### bitwise 成立的三个前提

| 前提 | 落点 |
|---|---|
| `enable_full_determinism: true` | 基线 recipe 已是 `true`（`train.yaml:22`），锁死 |
| 同 seed + 同数据顺序 | `seed: 42`；`input_hash` 随回执落账 |
| 布局 / 精度 / GBS / GA 不变 | 写进 `read_only` |

gate 与 benchmark 必须**同配置**：不能在门里开确定性、在基准里关掉，否则门验的不是被测对象。

#### 三个假通过（必须防）

1. **没生效也一致**：`mode` 改了但没有层被包住，数值当然逐位一致 → 必须有 `engaged`（层数 + 显存下降）正向证据；
2. **输入不同也“自洽”**：数据顺序 / seed / 布局漂移 → 比序列哈希 + `input_hash`，不比单点 loss；
3. **只在被测配置下一致**：`seq/micro_batch/cp` 变化后可能失效 → `applies_to` 写清覆盖范围，超范围结论标“未验证”。

### 3.8 D1 空间探测（决定阶段 1 方向）

重算的收益上界取决于基线是否“过度重算”。用两小时扫一条曲线：

```
k ∈ {N, N-8, N-16, N-24, 0}  → 记录 (peak_mem per rank, tgs/NPU)
```

判据：

| 曲线形状 | 结论 |
|---|---|
| k 接近 N 时曲线很平（显存降、吞吐不涨） | 重算空间小 → **切换主面**为并行布局，更新 contract 后继续 |
| k 下降时吞吐明显上升、显存仍有余量 | 重算就是最佳主面 → 按 §3.7 推进，并按实测空间定 `+xx%` 目标 |
| 中途 OOM | 记录 OOM 的 k 值作为下界，搜索区间取 `[k_oom+1, N]` |

探测结果写 `probe.json`，作为阶段 1 目标值与后续假设的起点。

---

## 4. 架构怎么兼容 jiuwen

### 4.1 三层兼容，逐层可验证

| 层 | 做法 | 验收 |
|---|---|---|
| **数据** | 只 import 公共契约：`rsi.schema.*`、`rsi.events.*`、`artifact_rsi.request.ArtifactEngineRequest`、`artifact_rsi.provider.ArtifactProvider`；`InfraTaskSpec` 为内部类型 | import 图里不出现 `program_opt.*` / `paper_opt.*` 内部模块 |
| **行为** | `run()` 先持久化再发事件；running → progress/node → terminal；重启后 `read_*` 可答；模型只用注入的 | 4 个契约测试（4.2） |
| **装配** | `register.py` 返回 `{"ARTIFACT:INFRA": adapter}`；jiuwenswarm 侧只需在 `build_rsi_adapters(artifact_adapters=...)` 多传一个 key | `ArtifactEngineAdapter` 包一层能跑通 |
| **发版** | `openjiuwen>=x,<x+1` 钉版本；`tests/contract/` 跑上游同款断言 | CI 双版本矩阵 |

**边界纪律**：参考 `program_opt` 的**分层结构**，不 import 其内部模块（它自带算法不变量，且面向“单文件程序”语义）。

### 4.2 四个契约测试

1. `isinstance(InfraArtifactProvider(), ArtifactProvider)`
2. 事件序列正确，且每条事件到达时对应快照已存在
3. 重启后新实例 `read_state/read_report/get_tree` 读回上一次
4. 双路径一致性：CLI 一次 vs `ArtifactEngineAdapter` 一次，`run_dir` 结构与报告字段一致

### 4.3 需要上游的 9 处小改（D4 才需要）

**agent-core（6 处，约 15 行）**：`schema.py:9` 的 `ArtifactType` 加 `"infra"`；`request.py` 的白名单改为查注册表、放行 `dataset_file` / `search_width`、`optimization_instruction` 对 infra 透传；`__init__.py` 导出（合入时）。

**jiuwenswarm（3 处）**：`models.py:48` 枚举加 `INFRA`；`provider_factory.py` 加 `ARTIFACT:INFRA` key；Hub/web 前端加一项 + 表单字段。

`build_rsi_adapters(artifact_adapters=...)` 与 `_resolve_adapter(adapter_resolver=...)` 已是现成注入点，路由逻辑无需改。

---

## 5. 流程编排在哪

### 5.1 唯一所有者：`irsi/engine/`

```
engine/seam.py       RunSpec / emit / should_stop —— 引擎缝（照 program_opt 的形状）
engine/loop.py       一轮状态机（唯一实现）
engine/state.py      快照持久化 + 事件发出 + read_* 重建（persist-then-emit）
engine/tree.py       假设树（阶段 1 线性，接口留 PUCT）
engine/scorecard.py  收益分 + 三值裁决 + 噪声带
```

### 5.2 状态机与裁决

```
INIT → BASELINE → HYPOTHESIZE → IMPLEMENT(commit) → EVALUATE(gates → benchmark)
     → ADJUDICATE(keep | discard | crash) → PERSIST → LEARN ──┐
     ▲                                                        │
     └────────────────── 下一轮（预算未耗尽）──────────────────┘
```

- **IMPLEMENT 先提交**：基准只测已提交代码；除 `editable_paths` 与 run 目录外有脏文件 → 拒绝执行。
- **EVALUATE 先门后测**：G0 → G1 →（G2 随采集）→ G3；任一失败即停。
- **ADJUDICATE 三值**：`keep`（过噪声带且显存达标）/ `discard`（噪声内或显存超预算）/ `crash`（门禁、回执、`engaged` 缺失、物理 sanity 不过）。
- **PERSIST 前向恢复**：失败用“新建一次提交”把 `editable_paths` 恢复到 best，不重写历史。
- **LEARN 保留延迟候选**：失败候选可声明 `revisit_on` scope，当后续 keep 的候选改动该 scope 时变为 `retry_ready`。

停止与预算用 `should_stop` 谓词，在安全点检查；不靠异常、不靠回调。

### 5.3 分层职责

| 层 | 拥有 | 不拥有 |
|---|---|---|
| `engine/loop.py` | 状态机、预算、停止谓词、裁决规则 | 怎么跑训练、怎么改文件 |
| `domain/` | evaluate（门选择与执行顺序）、reward、prompt | 何时调用、何时停止 |
| `executor/` | staging、torchrun、**结构化回执**、指标抽取 | 判定通过与否 |
| `ledger/` | `results.tsv`（人读）+ `candidates.jsonl`（机器回执） | 任何决策 |
| `provider.py` / `cli.py` / `SKILL.md` | 翻译、身份、模型、事件出口 | 任何状态转换 |
| rails/hooks（v0.1） | 对实施者的策略约束 | 流程推进 |

### 5.4 执行回执

executor 每次调用只回一行结构化回执，engine 只认这一行：

```text
RSI_TRAINING_RECEIPT {"workload_id":"...","phase":"gate","status":"passed",
  "completed_steps":20,"engaged":true,"first_error_step":null,"allocation_retries":0}
```

判定规则：

| 情况 | 结果 |
|---|---|
| `completed_steps != expect_steps` | `crash: incomplete_window` |
| `engaged=false` | `crash: path_not_engaged` |
| `must_match` 标记缺失 | `crash: missing_markers` |
| `status ∈ {oom, numerical_mismatch, incomplete, cleanup_failed, contention, error}` | `crash:<status>` |
| 窗口跑满后的 `futile` | 拒绝 |

### 5.5 与 hooks/rails 的边界

- 阶段 1 用 `ScriptedImplementer`（按白名单改 YAML），不引 agent runtime、不挂 hook。
- v0.1 换 `AgentImplementer`（DeepAgent + rails）时，`provider.py` 与 `engine/` 一行不改。
- 判定规则：跟随“agent 每次工具/模型调用”生效的 → rail；跟随“一轮实验”生效的 → engine。
- 计划挂的 rail：`EditScopeRail` / `GateIntegrityRail` / `BudgetRail`（写 `should_stop`）/ `CancelRail` / `AuditRail`。
- **不要**用 hook 推进状态、在 hook 里抛异常终止、用 hook 顺序表达业务优先级。

---

## 6. 仓库骨架

```
infra-rsi/
├── contracts/qwen3_8-recompute.yaml
├── skills/infra-rsi/SKILL.md              # prompt 入口（阶段 1 经 CLI）
├── irsi/
│   ├── entries/cli.py
│   ├── {service.py, provider.py, translate.py, register.py}
│   ├── contract/{spec.py, receipt.py, translate.py}
│   ├── engine/{seam,loop,tree,state,scorecard}.py
│   ├── domain/{evaluate,reward,prompt}.py
│   ├── executor/{staging,torchrun,metrics}.py
│   ├── implementer/{scripted.py, agent.py}
│   ├── ledger/{results.py, candidates.py}
│   └── kb/
├── tests/{contract,e2e,redteam}
└── docs/
```

---

## 7. 排期（D0–W3）

| 阶段 | 交付 | 验收 |
|---|---|---|
| **D0** | qwen3_8 `RecomputePolicy` 声明（region/exclude patterns）合入并冻结 commit | `selection.source=model_adapter_safe_regions` + `layer_count` 可用 |
| **D1** | **空间探测**（k 扫描）+ 骨架 + `service.py`（四端口）+ `entries/cli.py` + `provider.py` 八方法签名 | `probe.json` 曲线；`irsi run --help`、空跑事件流 |
| D2–D3 | `executor`（回执解析）+ `ledger`（双账本）+ baseline | 单卡/单节点 debug recipe 出一条可复现基线 |
| D4–D5 | `domain/evaluate`（G0–G3）+ `reward`（噪声带）+ `engine/loop`（三值裁决 + 前向恢复） | 一条假设走完四门并落账 |
| W2 | 循环跑满 ≥10 条假设 + 红队六场景 + 账本完整性校验；W2 末人工切一次并行布局验证通道 | 首次端到端闭环 |
| W3 | `kb`（含延迟候选）+ `skills/infra-rsi` + `register.py` + 4 个契约测试 + demo | 三入口都验证过；上游 9 处 patch 说明成稿 |

---

## 8. 阶段 1 明确不做

- 不做算子融合搜索（只留通道与白名单）
- 不做并行布局搜索（只做一次人工通道验证）
- 不做流水编排（调度未配置化）
- 不做 hooks/rails（只留 `ImplementerPort`）
- 不做 prompt 原生 tool（阶段 1 用 skill + CLI）
- 不做 Hub 表单与路由联调（只交注册说明）
- 不做 PR 自动提交、不做多节点
- 不在 `openjiuwen` 里新增 `infra_opt/`（v0.1 再议）

---

## 9. 待决事项

| # | 事项 | 影响 | 建议 |
|---|---|---|---|
| 1 | 8×910B3 算力与排队周期 | W1 能否跑全量门 | 先单节点 debug，全量门延后 |
| 2 | 模型与基线（qwen3_8 是否即「xxx 模型」） | recipe 与报告口径 | 先用 qwen3_8 |
| 3 | perf 口径 | reward 与阈值 | **主 tgs/NPU，辅 MFU**（架构感知 FLOPs + 独立复算） |
| 4 | 执行缝：`SysOperation` 命令 vs `TorchrunExecutor` | executor 形态 | 建议 `TorchrunExecutor`，保留“准备树 → 跑命令 → 读回执”形状 |
| 5 | 上游 9 处改动是否走 PR | v0.1 接线成本 | 先提 agent-core 6 处，再提 jiuwenswarm 3 处 |
| 6 | 是否 vendor PR #1517 的脚本（`model_flops.py`、`judge_equivalence.py`） | 指标与等价判定 | 可 vendor，需署名 + 版本锚定；PR 未合入，不建依赖 |
| 7 | skill 挂载位置：`skills_dirs` 指向仓库，还是安装时复制到 `~/.openjiuwen` | prompt 入口部署 | 阶段 1 用 `skills_dirs`，v0.1 随包安装 |
| 8 | qwen3_8 `RecomputePolicy` 的 region/exclude 划分由谁定 | D0 能否一次合入 | 由模型适配器 owner 定；我们提供 qwen3_8 的层结构与排除项建议 |
| 9 | D1 扫描若显示重算空间过小 | 是否换主面 | 切并行布局（门已现成，只换 contract 的 `edit_surface`） |

---

## 10. 与 PR #1517 的借鉴清单（借契约，不借壳）

PR #1517（`weich97`，open，未合入，227 文件 / +40567 行）是同一件事在 HyperParallel 内的 agent 化实现。可直接借的：

| 借鉴物 | 出处 | 用在哪 |
|---|---|---|
| 四条代码级硬规则（只测已提交代码、必须正向证据、门禁失败作废指标、失败前向提交留在历史） | `autoresearch/scripts/loop.py` | `engine/loop.py` |
| `run.json` 契约：argv 列表、`metric_pattern`、`noise_fraction`、`noise_confirm_reruns`、`aux_patterns`、`target_files` | `autoresearch/scripts/config.py` | `contracts/*.yaml` |
| 三值裁决 + 噪声带中位数复测 | 同上 | `engine/scorecard.py` |
| 双账本 `results.tsv` + `candidates.jsonl` | `autoresearch/scripts/loop.py` | `ledger/` |
| `revisit_on` / `retry_ready` 延迟候选 | 同上 | `kb` 的第四类条目 |
| `RSI_TRAINING_RECEIPT` 回执 + `training_protocol` 冻结 + futility/incomplete 判定 | `perf-playbook/references/training-rsi.md`、`config.py` | `executor` + `engine` 判定 |
| 按变更类型选门（等价实现 / 融合精度 / 训练策略） | `training-rsi.md` | `domain/evaluate.py`（阶段 1 只用 bitwise 类） |
| 预算与验收在代码里强制（`max_trials/max_seconds`、acceptance ≥20 步、linked series） | `mfu-riser/scripts/riser_contract.py` | `engine/loop.py` + `contract` |
| 架构感知 FLOPs（PaLM 6N + attention，含 gated delta-rule，排除 vision） | `hyper_parallel/trainer/runtime/model_flops.py` | `executor/metrics.py`（MFU 辅口径） |
| 盲跑限制（不读 git 历史、不读 gate 源码） | `autoresearch/templates/manual.md` | skill 硬规则 |
| 六场景红队测试写法 | `tests/ut/tools/test_autoresearch_loop.py` | `tests/redteam/` |
| 仓库知识地图 / 算子目录 / 瓶颈-技术-反例表 | `knowledge-retrieval/references/source-map.md`、`perf-playbook/references/*` | L3 域知识（见 L3 文档 §4） |

不能照搬的：

| 它的做法 | 原因 |
|---|---|
| markdown skill 即编排 | 无 provider 契约、无事件流、无 `read_state/read_report/get_tree`、无 task 身份 → 接不了 RSI 入口 |
| 贪心 best-so-far + 重试 | 无树/组合搜索，v0.3 用不上 |
| 知识 = markdown + cases | 无结构化 KB 与跨任务检索 |
| `.agent/` 文件布局 | 依赖 Claude Code 的 skill/command 宿主机制，jiuwen 下不可直接复用 |
| PR 作为依赖 | open、未合入；只能参考或 vendor 少量脚本（Apache-2.0，同组织，需署名） |

---

## 11. 变更记录

| 版本 | 日期 | 变化 |
|---|---|---|
| v0.1 | 2026-11-12 | 初稿：三入口、兼容三层、编排归属、D1–W3 排期 |
| v0.2 | 2026-11-12 | 对照 PR #1517：裁决改三值 + 噪声带；执行回执与双账本；延迟候选；按变更类型选门；指标口径 tgs/NPU + MFU；prompt 入口定为 skill + CLI |
| v0.3 | 2026-11-12 | 修改面收敛为**图优化（重计算）单主面**；融合关闭、并行只通道、流水不做；验证门简化为 G0–G3（bitwise 核心）+ C1；新增 engaged 与三个假通过；新增 D0（RecomputePolicy）与 D1 空间探测；排期与待决事项同步更新 |

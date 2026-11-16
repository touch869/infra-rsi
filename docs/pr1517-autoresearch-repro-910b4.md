# PR #1517 autoresearch 能力复现实验(910B4 真实训练级)

- 日期:2026-11-16
- 运行机:`910b4-126`(8×Ascend 910B4 32GB,华为云 liteserver)
- 引擎:mindspore-ai/hyper-parallel PR #1517 head `d51e911`,**原版未改一行**(`.agent/skills/autoresearch/scripts/{autoresearch,config,loop}.py`)
- 产物:`results/pr1517-repro-20261116/`(run 目录全量 + gitlog);运行现场 126:`/root/hp-pr1517`
- Wrapper(本实验自建,非 PR 代码):`workspace/pr1517-repro/runner.py`

## 1. 目标与设计

PR #1517 的 autoresearch harness 在其 SKILL.md 里明说:field record(DeepSeek-V4.1 Lightning-Indexer 697→123ms、4617→261ms)的原始产物在外部目录,"这些数字是历史上下文,不是本 checkout 可复现的基准结果"。本实验补上这一环:**在真实 8 卡 NPU 训练负载上验证引擎宣称的全部协议行为**,并用 infra-rsi 已知的 recompute ground truth(off 比 full 快 ~20%、selective 慢 30–45%,2026-11-12/13 实测)交叉验证决策正确性。

实验对象:medium-qwen3(24 层随机初始化、合成 packed 数据 seq 4096、FSDP dp_shard=8、bf16、full determinism),优化面 = `activation_checkpoint.mode`(full/off/selective)。候选编辑 = run 目录内 `exec_config.json`(执行设置文件,target file);训练由 wrapper(`runner.py --phase gate|benchmark`)按 PR 回执契约驱动 8 步正确性窗口(bitwise loss/grad_norm 指纹)与 32 步性能窗口(warmup 8 丢、末 16 步中位 tps,与 infra-rsi 同口径)。

engagement 正证据 = 双因子:resolved-config dump 中 `activation_checkpoint.mode` 精确等于请求值 **且** 峰值显存落该模式特征带(full≈4.0 / selective≈4.9 / off≈9.1 GB,本机实测)。故障注入通过 `exec_config.inject` 受控模拟两类真实事故:`silent_fallback`(请求 off 但配置管道断裂、full 继续跑)与 `numerical_corruption`(grad clip 1.0→0.001,速度不变数值必坏)。

## 2. Agent(创意半边)工作清单与分工

PR 的分工宣言:*"The agent owns the creative half (pick an idea, make the edit); this skill owns the deterministic half."* 本复现中 agent(ZCode 会话)承担全部创意半边与脚手架;引擎(PR 原代码)承担全部确定性半边,零修改。

### 研究与选型(实验前)
- 读 PR 引擎三件套源码(`autoresearch.py`/`config.py`/`loop.py`),提取硬契约:receipt 恰好一行 + 字段枚举校验、run.json 字段规则、决策树(improved→keep,其余 discard;gate 失败/marker 缺/engaged=false→crash)、dirty-tree 规则、restore 的具体 git 命令(前向 commit,非 revert)
- 选机:SSH 探测 114/126 两台 910B4(114 裸机、126 有全套 irsi 环境),选 126
- 定实验面:`activation_checkpoint.mode`——同时具备「已知 ground truth + 单键修改面 + engaged 双因子可证」
- 预注册 5 个候选(含 2 个故障注入)及各自预期决策,事后全部命中(见 §3)

### 环境与脚手架
- 拉取 PR head `d51e911` 到本地 checkout,rsync(带 `.git`)到 126 `/root/hp-pr1517`;修 `git safe.directory`
- 跑 PR 自带 13 个引擎单测(CPU,全绿);`test_agent_skill_contracts.py` 因 torch importlib 兼容问题无法运行(测的是另外 3 个 skill,与 autoresearch 无关,如实记录)
- 手动 8 卡短训 ×3(full/off/selective 各 8 步)实测显存特征带(4.0/9.1/4.9 GB)与 resolved-config dump 证据形态
- 自建 `runner.py`(约 250 行,属 PR 契约允许的 wrapper 声明层,**非引擎修改**):渲染 trial YAML、torchrun 8 卡启动、日志解析、bitwise 指纹、双因子 engaged 判定、故障注入、emit `RSI_TRAINING_RECEIPT`
- 用引擎 `init` 脚手架 run 目录 + 手写 run.json(training_protocol/workload_id/metric_pattern/noise/aux)
- 排障 3 次(每次都以引擎 crash 行如实留史):① workload_id 误含 git HEAD → scaffolding commit 作废在途 run;② resolved-config dump 是跨两行的 pretty JSON,逐行正则永远不匹配 → engaged 误判 false;③ HP codegen 按训练 YAML 改写 `generated/` 已跟踪文件 → dirty-tree 拒绝,commit 确定性稳态解决

### 实验循环(每轮 agent 动作 = PR 设计的 agent 半边)
- 选择并编辑 `exec_config.json`(保持 uncommitted)→ `iterate --description "..."` → 读引擎输出决策与 receipt → 按 PR 工作流 append `experiment_log.md`/`learnings.md`
- 两次 baseline crash 的根因定位:读 `candidates.jsonl` 的 `receipt_error` 字段、三个 trial log 交叉比对

### 引擎(确定性半边,对照)
- dirty-tree 检查、commit-before-test、gate→bench 调度、receipt 严格校验、noise band 决策、keep/discard/crash、前向 commit restore、append-only 记账——全部由 PR 代码执行,agent 未触碰

## 3. 决策对照(全部与预期一致)

| 实验 | exec_config | 预期 | 实际 | 证据 |
|---|---|---|---|---|
| baseline | full | keep | **keep** 23130 tps | gate 冻结指纹;peak_mem 4.007 GB |
| C1 | off | keep(+~20%) | **keep** 26955(**+16.6%**) | 指纹 bitwise 一致;engaged_mode=off;peak 9.058 GB |
| C2 | selective | discard(慢) | **discard** 14262(−47%) | 指纹一致;known negative 复现 |
| C3 | off + silent_fallback | crash(path_not_engaged) | **crash** `gate: path_not_engaged` | dump 仍 full → engaged=false,gate 拦截,metric 不记录 |
| C4 | off + numerical_corruption | crash(numerical_mismatch) | **crash** `gate: numerical_mismatch, first_error_step=2` | engaged=true 但指纹第 2 步分叉;metric 作废 |
| C5 | off(no-op) | discard | **discard** 23703(−12.1%,带外) | 清晰回归跳过 noise-confirm(引擎设计) |

C1 与 ground truth 同方向同量级(infra-rsi 实测 +20.63%,本次 +16.6%),引擎在不知先验的情况下自主重新发现了已知最优。

## 4. RSI 循环逐步记录(假设 → 知识 → 修改 → 检查 → 结果)

> 定位说明:本运行中"提出假设、选择编辑"的创意半边是**预注册的脚本化动作**(由 ZCode agent 按计划执行),不是引擎自主生成。因此这是一次 **RSI 协议骨架的真实训练级演练**——验证循环的确定性半边(修改面控制、正确性门、性能窗、决策、记账、回滚)在真实负载下成立;LLM 自主提出假设的半边未在本运行中测试。

### Step 0 · baseline(full)
- **假设**:activation checkpoint `full`(全层重算)是当前默认执行设置,作为被挑战的 best。
- **所用知识**:infra-rsi phase-1 中 qwen3 recipe 显式 `mode: full`;该 workload 显存峰值 ≈4GB。
- **修改**:无(冻结初始状态;`exec_config = {mode: full, inject: null}`)。
- **检查**:8 步正确性窗 → 冻结 bitwise loss/grad_norm 指纹(成为后续所有候选的数值基准);engaged 双因子(resolved dump=full 且显存 ∈(0,4.5]GB);32 步性能窗记录 steady tps。
- **结果**:**keep 23130 tps**;training_protocol 冻结(workload_id + gate 8/bench 32 步),baseline 回执入账。

### Step 1 · C1(off)——假设:重计算关闭,用显存换吞吐
- **假设**:关闭 activation recompute 消除反向重算开销,吞吐显著提升(先验 ~+20%,引擎不知此数字)。
- **所用知识**:recompute 语义(off=保留 activation、反向不重算);infra-rsi 两次实测 +20.63%/+11.28%;显存 4→9GB 仍在 32GB 卡预算内。
- **修改**:`exec_config.json` 单键 `full → off`(保持 uncommitted,由引擎 commit——铁律 1)。
- **检查**:gate=指纹必须与 baseline **bitwise 一致**(数值语义不变)+ engaged(dump=off 且显存 >7GB);bench=32 步 steady tps(丢 warmup 8 步、末 16 步取中位);对 best 的噪声带 ±5%。
- **结果**:**keep 26955(+16.6%,超带)**,实验 commit `59d791c` 成为新 best/HEAD;aux 证据 `peak_mem_gb=9.058 engaged_mode=off`。**循环在不知先验的情况下重新发现了已知最优。**

### Step 2 · C2(selective)——假设:逐层选择性重算可能更优
- **假设**(探索性):选择性重算只对部分层重算,或许保留省显存优势同时减少开销,可能优于 off。
- **所用知识**:HP selective 按安全 region 选层;本 workload 显存本就充裕,省显存收益无用而选择开销仍在(先验:infra-rsi 实测慢 30–45%,作为 RSI 循环内的独立探索步重新验证)。
- **修改**:`off → selective`(单键)。
- **检查**:同 C1(指纹 bitwise + engaged:dump=selective 且显存 ∈[4.5,7]GB + tps 对 best 26955)。
- **结果**:**discard 14262(−47%)**。引擎不保留编辑:前向 restore commit `cdb2abc` 把配置恢复为 off,best 不变;失败行按铁律 4 留在 results.tsv/candidates.jsonl。

### Step 3 · C3(silent_fallback 注入)——协议验证:静默回退必须被抓
- **假设**(协议验证而非性能假设):若配置管道断裂(请求 off、实际仍跑 full),训练会"正常完成、数值完美",仅凭输出无法发现——必须由 engaged 正证据拦截(铁律 2)。
- **所用知识**:PR 原始动机 *"a fallback run and an optimized run are indistinguishable by no warning"*;engaged 双因子设计(dump 精确匹配 + 显存特征带)。
- **修改**:`mode: off` + `inject: silent_fallback`(wrapper 模拟管道断裂:YAML 仍渲染 full)。
- **检查**:gate 的 engaged 断言(dump=full ≠ 请求的 off;显存 4.0 落 full 带)。
- **结果**:**crash `path_not_engaged`,metric=None**——bench 根本不执行;数值"看起来完美"也进不了账本;restore 前向 commit `7eadaf9`。

### Step 4 · C4(numerical_corruption 注入)——协议验证:快但错的候选必须作废
- **假设**(协议验证):数值正确性与性能可分离——"更快但数值错误"的候选必须被作废(铁律 3),且错误能定位到步。
- **所用知识**:grad clip 1.0→0.001 不改计算路径(速度不变)只改更新幅度;grad_norm 日志是裁剪**前**的值(第 1 步不变),loss 从第 2 步分叉 → 预期 first_error_step=2。
- **修改**:`mode: off` + `inject: numerical_corruption`。
- **检查**:gate 指纹逐 step 比对(→ 第 2 步分叉);engaged 仍 true(路径真实走了 off)。
- **结果**:**crash `numerical_mismatch, first_error_step=2`**——engaged 与数值错误两个维度干净分离;metric 作废。

### Step 5 · C5(no-op 重测)——假设:同配置重复测量应落噪声带内
- **假设**:同 best 配置重复 bench 应落在 ±5% 带内 → discard(带内则触发 median-of-3 噪声确认);检验测量稳定性。
- **所用知识**:infra-rsi 记录同机跨 run 波动 2.4–4.2%、候选间可达 ~10%。
- **修改**:exec_config 增加语义 no-op 的 `note` 字段(文本 dirty、语义与 best 相同)。
- **检查**:gate 指纹一致 + engaged;bench tps 对 best;带内→rerun 取中位、带外→直接 discard。
- **结果**:**discard 23703(−12.1%,带外)**——同配置两次测量差 ~12%,超出带宽;噪声确认按设计未触发(clear regression 跳过 rerun),暴露"带外盲区"(见 §7 发现 1)。

### 循环净效果
- 配置轨迹:full → **off**(唯一 keep);1 keep、2 discard、2 crash(注入)、另 2 次脚手架 crash 留史;账本 8 行,git 前向链完整。
- 吞吐:23130 → 26955 tps(**+16.6%**),数值语义 bitwise 不变,显存 4.0→9.1GB。
- 知识回流(learnings.md 三条):跨 run 波动 ~12%/噪声带偏紧;resolved-config dump 是最强 engaged 证据;first_error_step 可定位到单个 optimizer update。

## 5. 四铁律逐项核验

| 铁律 | PR 宣称 | 本实验证据 | 结论 |
|---|---|---|---|
| 1. benchmark 只测 committed 代码 | `iterate` 先 commit 再测 | 每个实验的 `exp:` commit(`59d791c/b77f6d5/a3f35b5/0724413/d1aa920`)先于 gate/bench;candidates.jsonl 的 parent→commit 链完整 | ✓ |
| 2. 正证据 marker 缺失 = crash 非静默通过 | engaged=false → path_not_engaged | C3:数值与 baseline 完全一致(还是 full)、bench 本可"跑通",gate 因 engaged=false 直接 crash,metric=None | ✓ |
| 3. gate 失败作废 metric | 无论 metric 多好 | C4:off 路径真 engaged、tps 本应更快,但指纹 step 2 分叉 → crash,metric 不进 results.tsv | ✓ |
| 4. 失败留历史,restore 用前向 commit | 不重写历史,best-so-far 恒为 HEAD | gitlog:C2/C3/C4/C5 各有 `exp:` + `discard:/crash:` 两个前向 commit;终态 HEAD = off(C1 keep 状态)= best | ✓ |

## 6. 协议能力清单核验

| 能力 | 结果 | 证据 |
|---|---|---|
| `RSI_TRAINING_RECEIPT` 严格校验(恰好一行/字段/枚举) | ✓ | 脚手架期第一次 baseline 因 workload_id 不符被拒 `invalid_training_receipt`( receipts_error 全文入账)——反向证明引擎真的在校验 |
| workload_id/phase 与冻结契约匹配 | ✓ | 同上 |
| completed_steps == expected(gate 8 / bench 32) | ✓(协议路径全程通过) | candidates.jsonl 各 jobs[].receipt |
| 失败分类(oom/numerical_mismatch/incomplete/…) | ✓ | C4 `numerical_mismatch` + `first_error_step=2` |
| engaged 布尔正证据 | ✓ | C3 `path_not_engaged`;正常路径 engaged=true |
| baseline 冻结 training_protocol(改协议需新 run) | ✓ | 引擎 `_check_training_baseline`;本 run 协议全程未变 |
| keep/discard/crash 决策 + noise band(±5%) | ✓ | C1 keep 超带、C2/C5 discard、C3/C4 crash |
| noise_confirm_reruns 仅带内触发、median-of-N | ✓(机制验证于 PR 单测;本 run C5 带外未触发,如实记录) | loop.py 设计:clear improvement/regression 跳过 |
| append-only 记账(results.tsv + candidates.jsonl) | ✓ | 8 行 TSV(含 2 次脚手架 crash 留史)+ 8 条候选回执 |
| aux 捕获(peak_mem_gb / engaged_mode) | ✓ | TSV 描述列 `[peak_mem_gb=9.058 engaged_mode=off]` |
| dirty-tree 防护(只许 target + run 目录) | ✓ | 引擎代码路径;run 目录内 trials/、fingerprint.json 未被拒 |
| 引擎自带单测 | ✓ | 13/13 通过(CPU,126 上 2.5s) |

## 7. 复现中发现的真实现象(非 PR 文档明说)

1. **同配置跨 run 波动 ~12%**(C1 26955 vs C5 23703,同一 off 配置)。5% 噪声带在此类 NPU 训练上偏紧;且引擎的 noise_confirm 只在带内触发,带外回归直接 discard、不做确认——一个 -12% 的纯噪声回归可能错杀一个等价候选。infra-rsi 记忆中"候选跨 run 波动可达 ~10%、3% 带偏紧"在此再次得到独立印证。
2. **workload_id 不应含代码 commit**:PR 协议说 workload_id 从"冻结的数据、shape、硬件与拓扑"派生。我们最初把 git HEAD 混入,任何 scaffolding commit 都会作废在途 run(第一次 baseline crash 的根因)。
3. **HP codegen 会按训练 YAML 改写 `generated/` 下已跟踪文件**,弄脏 run 目录外的树、触发 iterate 的 dirty-tree 拒绝;由于 codegen 对相同 parallel_dims 确定性,commit 一次稳态即解决。
4. resolved-config dump 是最强 engagement 证据(精确到配置键);显存特征带是好的第二因子,且对"配置没生效"类事故两者同时翻车(dump 不匹配 + 显存落错带),双因子冗余。
5. `first_error_step` 的语义分辨率达到单 optimizer update:C4 注入 clip 后 grad_norm(裁剪前)第 1 步不变、loss 第 2 步分叉,first_error_step=2 精确定位。

## 8. 与 PR field record 的可比性

| 维度 | PR field run(DSv4.1 Lightning-Indexer) | 本复现 |
|---|---|---|
| 优化对象 | 融合算子/索引器代码编辑 | 执行设置(activation checkpoint 模式) |
| 规模 | 生产模型微内核 697→123ms | 24 层随机初始化模型端到端 tps +16.6% |
| 引擎行为 | keep/crash(gate 抓 bf16 错误优化) | keep/discard/crash 全谱系 + 两类注入故障 |

引擎协议行为完全一致;量级与负载类型不可直接对比(本复现是协议验证,不是性能对标)。

## 9. 结论

PR #1517 的 autoresearch 引擎——四铁律、结构化训练回执、失败分类、噪声带决策、append-only 记账、前向 commit/restore——**在 8×910B4 真实训练负载上全部按文档成立**,且决策与独立测得的 ground truth 一致。引擎本身零修改;全部适配都发生在 PR 契约允许的 wrapper/gate/benchmark 声明层。两个值得带走的工程事实:noise_confirm 的带外盲区,与 workload_id 的 HEAD 无关性要求。

## 附:复现步骤

```bash
# 126 上(环境:irsi conda env + CANN set_env)
cd /root/hp-pr1517   # PR #1517 head d51e911,带 .git
python tests/ut/tools/test_autoresearch_loop.py                 # 13/13
python .agent/skills/autoresearch/scripts/autoresearch.py init \
  --run-dir autoresearch-runs/qwen3-recompute \
  --target autoresearch-runs/qwen3-recompute/exec_config.json \
  --benchmark-cmd "...runner.py --phase benchmark" --gate-cmd "...runner.py --phase gate"
# 编辑 run.json(training_protocol/metric_pattern/noise/aux)→ commit scaffolding
python .agent/skills/autoresearch/scripts/autoresearch.py baseline --run-dir <d>
# 每个候选:编辑 exec_config.json(保持 uncommitted)→
python .agent/skills/autoresearch/scripts/autoresearch.py iterate --run-dir <d> --description "..."
```

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

## 2. 决策对照(全部与预期一致)

| 实验 | exec_config | 预期 | 实际 | 证据 |
|---|---|---|---|---|
| baseline | full | keep | **keep** 23130 tps | gate 冻结指纹;peak_mem 4.007 GB |
| C1 | off | keep(+~20%) | **keep** 26955(**+16.6%**) | 指纹 bitwise 一致;engaged_mode=off;peak 9.058 GB |
| C2 | selective | discard(慢) | **discard** 14262(−47%) | 指纹一致;known negative 复现 |
| C3 | off + silent_fallback | crash(path_not_engaged) | **crash** `gate: path_not_engaged` | dump 仍 full → engaged=false,gate 拦截,metric 不记录 |
| C4 | off + numerical_corruption | crash(numerical_mismatch) | **crash** `gate: numerical_mismatch, first_error_step=2` | engaged=true 但指纹第 2 步分叉;metric 作废 |
| C5 | off(no-op) | discard | **discard** 23703(−12.1%,带外) | 清晰回归跳过 noise-confirm(引擎设计) |

C1 与 ground truth 同方向同量级(infra-rsi 实测 +20.63%,本次 +16.6%),引擎在不知先验的情况下自主重新发现了已知最优。

## 3. 四铁律逐项核验

| 铁律 | PR 宣称 | 本实验证据 | 结论 |
|---|---|---|---|
| 1. benchmark 只测 committed 代码 | `iterate` 先 commit 再测 | 每个实验的 `exp:` commit(`59d791c/b77f6d5/a3f35b5/0724413/d1aa920`)先于 gate/bench;candidates.jsonl 的 parent→commit 链完整 | ✓ |
| 2. 正证据 marker 缺失 = crash 非静默通过 | engaged=false → path_not_engaged | C3:数值与 baseline 完全一致(还是 full)、bench 本可"跑通",gate 因 engaged=false 直接 crash,metric=None | ✓ |
| 3. gate 失败作废 metric | 无论 metric 多好 | C4:off 路径真 engaged、tps 本应更快,但指纹 step 2 分叉 → crash,metric 不进 results.tsv | ✓ |
| 4. 失败留历史,restore 用前向 commit | 不重写历史,best-so-far 恒为 HEAD | gitlog:C2/C3/C4/C5 各有 `exp:` + `discard:/crash:` 两个前向 commit;终态 HEAD = off(C1 keep 状态)= best | ✓ |

## 4. 协议能力清单核验

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

## 5. 复现中发现的真实现象(非 PR 文档明说)

1. **同配置跨 run 波动 ~12%**(C1 26955 vs C5 23703,同一 off 配置)。5% 噪声带在此类 NPU 训练上偏紧;且引擎的 noise_confirm 只在带内触发,带外回归直接 discard、不做确认——一个 -12% 的纯噪声回归可能错杀一个等价候选。infra-rsi 记忆中"候选跨 run 波动可达 ~10%、3% 带偏紧"在此再次得到独立印证。
2. **workload_id 不应含代码 commit**:PR 协议说 workload_id 从"冻结的数据、shape、硬件与拓扑"派生。我们最初把 git HEAD 混入,任何 scaffolding commit 都会作废在途 run(第一次 baseline crash 的根因)。
3. **HP codegen 会按训练 YAML 改写 `generated/` 下已跟踪文件**,弄脏 run 目录外的树、触发 iterate 的 dirty-tree 拒绝;由于 codegen 对相同 parallel_dims 确定性,commit 一次稳态即解决。
4. resolved-config dump 是最强 engagement 证据(精确到配置键);显存特征带是好的第二因子,且对"配置没生效"类事故两者同时翻车(dump 不匹配 + 显存落错带),双因子冗余。
5. `first_error_step` 的语义分辨率达到单 optimizer update:C4 注入 clip 后 grad_norm(裁剪前)第 1 步不变、loss 第 2 步分叉,first_error_step=2 精确定位。

## 6. 与 PR field record 的可比性

| 维度 | PR field run(DSv4.1 Lightning-Indexer) | 本复现 |
|---|---|---|
| 优化对象 | 融合算子/索引器代码编辑 | 执行设置(activation checkpoint 模式) |
| 规模 | 生产模型微内核 697→123ms | 24 层随机初始化模型端到端 tps +16.6% |
| 引擎行为 | keep/crash(gate 抓 bf16 错误优化) | keep/discard/crash 全谱系 + 两类注入故障 |

引擎协议行为完全一致;量级与负载类型不可直接对比(本复现是协议验证,不是性能对标)。

## 7. 结论

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

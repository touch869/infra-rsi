# Autoresearch as the optimization controller

更新日期：2026-11-19

## 结论

寻优主控制器使用 `irsi/knowledge/skills/execution/autoresearch/SKILL.md`。
infra-rsi 不再维护第二套 analysis → decision → execute 编排器，只提供可复现的
单次测量、合同约束、gate、指标解析和证据落盘。

这样分工的原因是：`autoresearch` 已经拥有更严格的确定性协议，包括：

- 只测已提交代码；
- baseline / keep / discard / crash 的明确裁决；
- 每步一个 commit，包含 why / change / test result；
- 失败或无效候选回退代码，只提交报告与证据；
- 噪声带、正向证据 marker、retry 和 append-only ledger。

## 运行边界

```text
用户自然语言目标
  → 宿主 Agent 读取 autoresearch/SKILL.md
  → Agent 探测目标仓库与训练配置，生成 contract draft
  → Agent 用自然语言展示 workload / 指标 / gate / 可改面 / 预算
  → 用户明确确认（确认码 + 确认原话）
  → 写入 contract hash lock
  → 初始化 run，填写 manual.md 约束与命令
  → baseline：测量一次并提交配置/手册/冻结证据/账本
  → 分析子 agent：baseline/profile → diagnosis + evidence
  → 策略子 agent：diagnosis → ranked candidates
  → 实现子 agent：一个 candidate → target_files 内的最小编辑
  → autoresearch iterate：gate → benchmark → keep/discard/crash
  → 每步 commit、记录、回退
  → 主控制器更新 ideas/learnings，判断继续或停止
```

`irsi measure` 只负责一次 trial：

1. 按合同渲染 base workload；
2. 启动当前已提交代码；
3. 执行 receipt / memory 等合同 gate；
4. 输出稳定 metric marker 与 `measurement.json`；
5. 校验合同 sidecar lock 与语义 hash；
6. `--freeze-baseline` 冻结数值参考，`--reference` 对后续 trial 做数值比对。

## 合同生成、确认与冻结

合同不是用户手填的 YAML，而是 Agent 根据目标仓库和基础训练配置生成的评估边界。
生成器只做可核查的推断，最终仍由用户通过自然语言确认：

```bash
python -m irsi.cli contract draft \
  --objective "<优化目标>" --base-config <train.yaml> \
  --repo-root <目标仓库> --out contracts/<task>.generated.yaml
python -m irsi.cli contract show --contract contracts/<task>.generated.yaml

# 把 summary、hash 和确认码展示给用户并等待明确回复；不得自行确认

python -m irsi.cli contract confirm \
  --contract contracts/<task>.generated.yaml --code <确认码> \
  --statement "<用户确认原话>" --confirmed-by user
```

产物是同目录 sidecar：

- `<contract>.draft.json`：生成时的目标、hash、确认码和摘要；
- `<contract>.summary.md`：供用户审阅的自然语言摘要；
- `<contract>.lock.json`：用户确认原话、确认人、时间和冻结 hash。

hash 基于规范化后的合同语义 JSON，不受 YAML 注释和排版影响。`irsi measure`
在 baseline 与 candidate 前都会核对磁盘合同、运行 spec 和 lock 三者；任何语义
变更都会使 lock 失效。此时必须重新生成、重新确认，并重新冻结 baseline。旧
baseline 不可跨合同复用。

## Baseline 可追溯边界

baseline 不是“跑一次 `irsi measure` 后手动保存一个数字”。对 `irsi measure`
流程，run.json 必须把冻结证据路径固定下来：

```json
{
  "baseline_cmd": ["python", "-m", "irsi.cli", "measure", "--contract", "contracts/qwen3.yaml", "--freeze-baseline", "runs/ar/baseline.json", "--label", "baseline"],
  "baseline_artifact": "baseline.json",
  "benchmark_cmd": ["python", "-m", "irsi.cli", "measure", "--contract", "contracts/qwen3.yaml", "--reference", "runs/ar/baseline.json", "--label", "candidate"]
}
```

`init` 会从 `--freeze-baseline` 自动推断 `baseline_artifact`，也可显式传
`--baseline-artifact`。路径必须是 run 目录内相对路径；逃逸到 run 目录外会被拒绝。

baseline 执行时依次完成：

1. 运行 `baseline_cmd`，通常是 `irsi measure --freeze-baseline`；
2. 校验冻结 JSON 的 schema、`source_commit`、metric、`numeric_hash`、
   `contract_hash` 和 confirmed lock；
3. 把 `run.json`、`manual.md`、`baseline.json`、`results.tsv`、
   `candidates.jsonl`、`experiment_log.md`、`ideas.md`、`learnings.md`
   放入同一个 baseline commit；
4. 在 `candidates.jsonl` 中记录 run.json / manual / baseline 的 SHA-256、
   合同 hash、确认码、数值 hash 与 measured commit。

baseline commit 是运行的可追溯边界。baseline 之后，`iterate` 会拒绝修改
`run.json`、`manual.md` 或冻结 baseline 证据；需要调整评估边界时必须新建 run
目录并重新 baseline。合同 sidecar（`.draft.json`、`.summary.md`、`.lock.json`）
应在合同所在仓库单独提交，baseline 证据中的合同 hash 与确认码负责把两边关联起来。

## 子 agent 协作

主控制器保留预算和最终裁决权。子 agent 只做窄职责，并通过 artifact 交接：

| 阶段 | 角色 | 交接物 | 禁止事项 |
|---|---|---|---|
| Observe | 分析 | 诊断、证据路径、允许的变更范围 | 改源码、选最终候选 |
| Propose | 策略 | 候选排序、why、目标文件、预期 gate | 跑 benchmark、改源码 |
| Implement | 实现 | 一个最小 patch、变更摘要 | 同时改多个候选、越过 target_files |
| Execute | 确定性工具 | `results.tsv`、`candidates.jsonl`、实验日志、commit | 用子 agent 口述指标覆盖记录 |
| Judge | 主控制器 | keep/discard/crash 与停止判断 | 绕过 gate 或噪声带 |
| Reflect | 主控制器 | `ideas.md`、`learnings.md`、下一轮候选 | 把未验证结论写成 learning |

baseline 完成后 Observe 与 Propose 可以并行；Implement 必须串行；Execute 只在
实现者停止后开始。所有子 agent 必须收到同一份 `manual.md` 约束和原始命令。

## 与旧固定 surface 的关系

`contract/surfaces/` 与 `irsi run` 保留为确定性回归路径，不再承担“发现新优化”
的主流程。Agent 可以从代码、profile 和 skill 中提出 surface 之外的候选，但必须：

- 通过合同冻结 workload、metric、gate 和配置只读键；
- 只修改 `run.json` 的 `target_files`；
- 由 `autoresearch` 的确定性记录裁决，不能直接宣告收益。

完整运行规则以 `autoresearch/SKILL.md` 和 run 目录中的 `manual.md` 为准。

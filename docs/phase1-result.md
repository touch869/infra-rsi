# 阶段 1 实施结果：闭环打通与重计算收益

| 项 | 值 |
|---|---|
| 状态 | 已完成（阶段 1 原型闭环） |
| 日期 | 2026-11-12 |
| 机器 | `910b4-126`，8 × Ascend 910B4（32 GiB HBM/die） |
| 框架 | HyperParallel，torch 2.9.0 + torch_npu 2.9.0.post9，CANN 8.5.2，Python 3.11 |
| 模型 | 24 层 Qwen3（hidden 2048、seq 4096、随机初始化），另用 12 层 tiny 配置做冒烟 |
| 收益 | **吞吐 +20.63%**（vs baseline），**+15.78%**（vs no-op control），数值逐位一致 |

---

## 1. 摘要

阶段 1 的目标是“打通流程”，即用一条命令完成 契约 → baseline → 假设 → 实施 → 验证 →
裁决 → 归档，并给出可追溯的收益。现在已达成：

- `irsi run --contract contracts/medium-qwen3.yaml` 一次跑完 5 个 trial（1 baseline + 4 候选），
  全程无人工干预，0 crash；
- 主结论：在 24 层 Qwen3、8 卡、32 步口径下，关闭基线中保守的**全量重计算**把吞吐从
  **21 416.4 → 25 834.9 tokens/s/NPU（+20.63%）**，代价是峰值显存 4.01 → 9.06 GiB（预算 24 GiB）；
- 数值等价门通过：baseline 与最优候选的 loss/grad_norm 指纹完全相同
  （`48f4302f…`），说明该改动没有改变训练语义；
- no-op 对照 trial 的漂移为 +4.19%，超过 3% 噪声带，报告标记 `drift.suspected=true`；
  因此对外以相对该对照的 **+15.78%** 为保守口径，报告仍标记 `robust=true`。

---

## 2. 交付物

### 2.1 代码（`infra-rsi`）

提交按模块切分；下表为截至证据导出的提交序列（`git log --oneline`）。

| 提交 | 内容 |
|---|---|
| `db96bc7` chore | 包骨架、pyproject、插件注册表 |
| `5933124` feat(contract) | 冻结契约、点号覆盖、**key 级可写面校验** |
| `3d4d378` feat(receipt) | 日志 → 逐步指标 + bitwise 指纹 |
| `2a4acc4` feat(backend) | append-only 账本 + HyperParallel torchrun 后端 |
| `499ae1e` feat(plugins) | receipt / bitwise / memory 门 + recompute 领域插件 |
| `a3dffd5` feat(engine) | baseline → 候选 → 三值裁决 状态机 |
| `5736cc2` feat(cli) | `irsi run/status/report` + 契约实例 |
| `eb3c58b` feat(engine) | no-op 对照漂移检测与 robust 判定 |
| `4a499a7` docs | 阶段计划、L1/L3 知识库设计、结果初稿 |
| `9607cdb` results | 第一次 medium 运行的证据导出 |
| `98c7364` refactor(backend) | 改用 `python -m torch.distributed.run`，task.json 记录解释器/环境 |
| `50715a8` docs(results) | 最终运行、可重复性表与漂移说明 |
| `8a24582` feat(workspace) | 运行输入版本化 + 确定性数据生成器（已从零重建验证） |

### 2.2 证据

`results/medium-qwen3-20261112/`：最终报告、baseline 摘要、四条决策、每个 trial 的逐 step
指标与实际渲染配置。原始日志留在运行机的 task 目录（路径见证据 README）。

运行输入（模型配置、基础训练 YAML、数据生成器）版本化在 `workspace/`，可在运行机上从
仓库重建；`workspace/README.md` 给出步骤。

---

## 3. 方法

### 3.1 修改面（key 级）

契约只允许改 `activation_checkpoint.*`：

- `mode ∈ {full, selective, off}`
- `selection.*`、`swap_inputs`

`contract.check_overrides_allowed` 在启动前拒绝任何越界键（例如 `training.seed`、
`mixed_precision`），不是靠提示词约束。候选由 `contract/surfaces/recompute.py` 生成，共 4 条。

### 3.2 验证门

| 门 | 判据 | 本 run 结果 |
|---|---|---|
| `receipt` | exit 0、无 traceback、步数 = 32 | 全部通过 |
| `bitwise` | loss/grad_norm 指纹与 baseline 完全相同 | 全部通过（含 off） |
| `memory` | 峰值 ≤ 24 GiB | 最高 9.06 GiB |

裁决为三值：`keep`（超过噪声带且门全过）/ `discard`（未超噪声）/ `crash`（任一门失败）。
噪声带 3%，measured window 为第 9–32 步的中位数。

### 3.3 对照与漂移

契约中固定一条 **no-op 候选**（overrides 为空）。它测的是“同一配置再跑一次”，用来估计机器漂移：

- 若 no-op 被判 `keep`，说明噪声估计失效；
- 报告同时给出 `gain_vs_baseline` 与 `gain_vs_control`，后者更保守。

---

## 4. 结果

| trial | 状态 | tps | Δ vs baseline | Δ vs control | 峰值 GiB | bitwise |
|---|---|---|---|---|---|---|
| baseline（full） | reference | 21 416.4 | — | — | 4.01 | — |
| `off` | **keep** | **25 834.9** | **+20.63%** | **+15.78%** | 9.06 | 相同 |
| `control`（no-op） | discard | 22 314.0 | +4.19% | — | 4.01 | 相同 |
| `selective` | discard | 14 616.0 | −31.75% | −43.43% | 4.88 | 相同 |
| `selective + swap_inputs` | discard | 13 938.1 | −34.92% | −46.05% | 4.70 | 相同 |

- 单 trial 墙钟 54–70 s（32 步，含建模型）。
- `robust=true`，`drift.suspected=true`（对照漂移 4.19%），`counts={kept:1, discarded:3, crashed:0}`。

### 4.1 可重复性

同机同契约三次运行：**+17.64%**（24 步）、**+11.18%**（32 步）、**+20.63%**（32 步）。
方向一致，区间 +11%~+21%；no-op 对照漂移 2.4%~4.2%，所以保守口径（vs control）为
**+8.6%~+15.8%**。tiny（12 层）单候选冒烟 +17.93%。

---

## 5. 解读

1. **为什么 `off` 有效**：基线为了保守而全量重算。这个 24 层模型在 8 卡、seq 4096、
   micro-batch 1 下，关闭重算后显存只用到 9.06/24 GiB，说明基线存在明显的“过度重算”，
   省掉一次前向重放直接换成吞吐。
2. **为什么 `selective` 更慢**：selective checkpointing 的策略判断与缓存管理在逐算子层面
   引入额外开销，而该模型激活并不是瓶颈——这属于“机制存在但代价不划算”的典型负例，
   已作为知识条目保留（`decisions/h03-selective.json`）。
3. **bitwise 全绿的意义**：重计算是确定性重放，数值本应完全一致。四条候选的指纹都与
   baseline 相同，说明这些改动没有偷偷改变训练语义——这是重算面能使用最严格门的依据。
4. **为什么要 no-op 对照**：本次 baseline 与 control 相差 +4.19%，若只看 baseline 会把漂移算进收益。
   报告同时给出两个口径，并在漂移超阈值时标记 `drift.suspected=true`。

---

## 6. 架构落地情况（模块化 / 插件化）

```
cli.py ──► engine.py ──► execution/backends/hyperparallel.py
                │            (torchrun + log parsing)
                ├──► gates/builtin.py     receipt / bitwise / memory
                ├──► contract/surfaces/recompute.py  candidate generation
                ├──► execution/metric_extractor.py           metrics + fingerprint
                ├──► knowledge/runtime/ledger_store.py            results.tsv / candidates.jsonl / decisions
                └──► contract/task_spec.py          key-level writable surface
```

扩展点全部是注册表（`irsi/registry.py`）：

- 新后端：`@BACKENDS.register("k8s")`，实现 `run(spec, trial_dir, overrides, label)`；
- 新门：`@GATES.register("tolerance")`，实现 `check(ctx)`；
- 新修改面：`@SURFACES.register("fusion")`，返回 `Hypothesis` 列表，并在契约里声明
  `writable_prefixes`。

`engine.py` 不 import torch 或 HyperParallel，也不认识任何具体门/后端/修改面——测试里用一个
fake backend 和一个临时 surface 就能驱动完整状态机（`tests/test_engine.py`）。

---

## 7. 局限

- **模型是随机初始化的 24 层 Qwen3**：吞吐与显存趋势可信，但绝对数值不代表真实大模型；
  收敛质量不在阶段 1 的验证范围内（重算面不需要）。
- **单节点 8 卡**：没有跨机通信，结论不外推到多节点。
- **只覆盖图优化/重计算一个面**：融合、并行、流水尚未进入搜索（旧计划见 `docs/archive/phase1-plan.md` §8）。
- **对照只有一条**：no-op 只采了一次，漂移估计的置信度有限；后续可加 `noise_confirm_reruns`。
- **吞吐随机器状态波动**：同一配置两次运行可差 2–4%，因此所有结论都以“vs 同日对照”为准。

---

## 8. 复现

```bash
# 运行机（910b4-126）
cd /root/irsi-workspace
irsi run --contract /root/infra-rsi/contracts/medium-qwen3.yaml \
         --runs-dir /root/irsi-workspace/runs
irsi report runs/<task-dir>

# 本地
python -m pytest -q          # 16 个单测
```

依赖准备（运行机）：Python 3.11 conda env、torch 2.9.0 + torch_npu 2.9.0.post9、
CANN 8.5.2、`pip install -e .`；HyperParallel 位于 `/root/hyper-parallel`。

运行输入从仓库重建：

```bash
cp -r workspace/. /root/irsi-workspace/
cd /root/irsi-workspace && python make_data.py --out data/tiny-packed
```

`workspace/` 内含 tiny/medium 两个随机初始化配置、基础训练 YAML、`PackedTensorDataset`
与确定性数据生成器。已在 910b4-126 上用该目录从零冒烟验证：baseline 42 779.8 →
`off` 47 605.2 tps（+11.28%），三道门全过、指纹相同（`84b0ad95…`）。

---

## 9. 下一步

1. **接入第二个修改面**（并行布局）：需要 series 概念与容差门，见计划 §3.7/§3.8 的备选路径；
2. **把 no-op 对照做成契约强制项**（当前是领域插件里的一条候选）；
3. **ImplementerPort**：把当前“直接改 YAML”的实现者换成 agent 实现者，接 v0.1；
4. **jiuwen provider 适配层**：`provider.py` + `register.py` + 4 个契约测试，让同一内核支持三入口。

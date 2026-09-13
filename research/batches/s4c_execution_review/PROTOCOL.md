# S4C authoritative execution review protocol

冻结时间：提交前。Accepted starting commit：`8df12b2`（Batch 05 principal architect review + 开发验证解释器固定）。本协议在任何 S4C 权威执行运行之前冻结；protocol commit（Commit A）必须先于真实结果存在。

本批只回答一个问题：冻结语义的 S4C ERC 目标能否在 RQAlpha 原生语义下被忠实执行？它不是新的策略研究、参数研究、候选冻结或前瞻激活。

## Immutable inputs

| Input | SHA-256 |
| --- | --- |
| canonical prices | `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93` |
| canonical calendar | `ad942a3e1e3e3ae4b7703ea5319ec12793d484b4c49423181682357a1a9d7512` |
| `config/universe.csv` | `190aacbca6feadd2ba825b1f284c06f48f30bdc3b5a4618f405711e5aadb8829` |
| S2 R1 manifest | `e280c60b9a0698e6fd19a2f268913dbb7ac42492b2062e5f3268d2a61bc4326f` |

运行环境：Python 3.11（仓库 `.python-version`）、RQAlpha 6.3.0、skfolio 1.0.6、VectorBT 0.28.5、Pandas 2.3.3、NumPy 1.26.4。

## Frozen strategy semantics

- skfolio `RiskBudgeting`；`RiskMeasure.VARIANCE`；equal risk budgets；long-only、fully invested、无杠杆；min eligible 6。
- aligned returns 固定 60（价格窗口 61）；不得重测 40 或 80，不得择优窗口。
- 沿用既有 S2 risk universe 与 511010.SS 防御；月末估计、下一 canonical observation execution；既有 10 bps fee + 5 bps slippage；既有 PIT lifecycle/tradability contract。
- RQAlpha 只使用 `order_target_portfolio` 提交冻结目标行，启用原生账户、撮合、整手、现金、成本、滑点与 `partial_fill_on_insufficient_cash=true`；回调内不得重算信号、波动、ERC 权重或 fallback。
- 不添加集中度 cap；集中度只作诊断证据。

## Frozen target artifact

路径：`research/results/s4c_pit_corrected_frozen_targets_v1.csv`
生成命令：`uv run python research/experiments/run_s4c_rqalpha_execution_review.py --freeze-targets`

| 属性 | 值 |
| --- | --- |
| row count | 161 |
| first execution date | 2013-04-01 |
| last execution date | 2026-08-03 |
| SHA-256（LF 归一化序列化） | `f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47` |

该 artifact 必须与已接受的 corrected inception（2013-04-01）和 161 个 target changes 一致。任何不一致都是 reproduction blocker，不得修改语义以求通过。执行运行必须在 RQAlpha 之前验证 committed artifact 与冻结语义重新推导的序列化完全一致；不一致立即停止且不运行 RQAlpha。

## Reproduction gate

对 committed frozen target 文件直接做 VectorBT replay，必须machine tolerance（`1e-12`）重现已接受的 60-return PIT-corrected 基线（`research/results/s4c_pit_corrected_comparison_v1.csv`）的 CAGR、signed MaxDD、Sharpe、Calmar、turnover。

失败决定：`BLOCK_S4C_EXECUTION_REPRODUCTION`。reproduction 失败后不得启动 RQAlpha。

## Native execution gate

必须全部成立：

| Gate | 阈值 |
| --- | --- |
| all frozen execution dates processed | 全部 161 |
| extra replay dates | 0 |
| `cash_rejection_events` | 0 |
| 平均 execution-date total absolute weight deviation | <= 3% |
| materially off-target execution dates | <= 10% of frozen dates |
| 平均 cash ratio | <= 2% |
| RQAlpha CAGR | > 0 |
| RQAlpha CAGR vs VectorBT | >= VectorBT CAGR - 2pp |
| signed RQAlpha MaxDD vs VectorBT | >= VectorBT MaxDD - 5pp |
| material execution difference 解释 | 全部有具体 native 解释；`UNKNOWN` / `UNEXPLAINED_EXECUTION_DIFFERENCE` 不算通过 |

material difference 沿用既有 5pp（`MATERIAL_DEVIATION`）口径。

Allowed terminal decisions：

```text
ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW
DO_NOT_ADVANCE_S4C_EXECUTION
BLOCK_S4C_EXECUTION_REPRODUCTION
BLOCK_S4C_EXECUTION_ENVIRONMENT
```

PASS 只获得 candidate-freeze review 资格，不创建 candidate、不激活 prospective shadow、不替代 S2。

## Artifacts

执行运行产出：

```text
research/results/s4c_rqalpha_execution_vectorbt_reproduction_v1.csv
research/results/s4c_rqalpha_execution_summary_v1.csv
research/results/s4c_rqalpha_execution_target_tracking_v1.csv
research/results/s4c_rqalpha_execution_material_differences_v1.csv
research/results/s4c_rqalpha_execution_user_effort_v1.csv
research/results/S4C_RQALPHA_EXECUTION_REVIEW_V1.md
```

报告必须包含：冻结 count/hash/dates、VectorBT reproduction、RQAlpha 版本、CAGR/signed MaxDD/Sharpe、turnover 与交易成本、订单/成交数量、cash rejection、native cash-residual cancellation、volume-limit 计数、期末/最低现金与平均 cash ratio、平均/最大 target deviation、material execution dates 比例、material difference 解释、既有集中度证据（P95 51.84%、maximum 66.35%、effective-assets 诊断）作为背景而非新 gate，以及机械决定。

## 停止条件

- S2 完整性校验失败。
- committed frozen target hash 在 Commit A 与执行之间发生变化。
- 无法重现已接受的 60-return 基线。
- RQAlpha / skfolio 环境版本错误或缺少 bundle（标记 `ENVIRONMENT_BLOCKED`，不得生成 synthetic authoritative result）。
- 需要改变 covariance、window、risk measure、fallback、成本或添加 cap。
- 需要本地会计、现金预留、手工 sizing、撮合或 retry。
- 需要在 RQAlpha 内重算信号或 ERC 权重。
- 任何 `INVALID_RUN` 实现缺陷：保留 artifact，走 `INVALID_RUN → 新 Protocol 版本 → freeze → 完整 rerun`，不得静默重跑。

## 边界

不修改 S2、策略经济语义、Batch 05 冻结产物、外部证据 tier 或永久架构/规则；不新增通用 execution / robustness framework；不建立第二个候选或前瞻影子。

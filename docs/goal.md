# Goal: TactiCore — S4C Authoritative Execution Review

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Execution mode:

```text
Codex with ChatGPT / C2C
```

## Why this work exists

Batch 05 以冻结证据确认 S4C（canonical ERC / skfolio）通过 bounded robustness，得到 `ADVANCE_S4C_TO_EXECUTION_REVIEW`；[Batch 05 principal architect review](../research/results/BATCH_05_PRINCIPAL_ARCHITECT_REVIEW_V1.md) 在 S27A candidate-freeze review（与 S2 趋势信号机制重叠，已推迟）与 S4C authoritative execution review 之间选出后者，作为本里程碑之后的唯一 Goal。

本 Goal 只回答一个问题：**冻结语义的 S4C 目标能否在 RQAlpha 原生语义下被忠实执行？** 它不是策略发现、不是参数研究，也不是候选冻结或前瞻激活。

## External Evidence Gate

- Canonical mapping：equal risk contribution / risk parity，registry `strategy_id: ERC_RISK_PARITY`。
- External tier：`E2_ESTABLISHED_METHOD`（成熟构造方法，非收益异常；软件可用不等同经济优越）。
- External conclusion：ERC 是既定风险配置算法，需处理相关性与协方差估计、无杠杆约束与集中度。
- Relevant contradictions：估计误差方法在 1/N 基准前并不自动占优；无杠杆 equal-risk-budget 在少量资产上可能高度集中。
- Upstream implementation：官方 skfolio `RiskBudgeting`，`RiskMeasure.VARIANCE`、equal risk budget、long-only（1.0.6）；权威执行由 RQAlpha 6.3.0 原生账户承担。
- Existing TactiCore evidence：`S4C_ERC_SKFOLIO_TRANSFER_V1`（transfer 通过）、`S4C_ROBUSTNESS_V1`（40/60/80 neighborhood、固定 periods、rolling、50bps 通过；P95 max weight 51.84%）。
- Remaining local gap：冻结 ERC targets 在 RQAlpha 原生账户、撮合、现金、整手与成本下的执行保真、目标跟踪与现金行为尚未被验证。
- Research action：`UPSTREAM_COMPARE`。

## PIT Tradability Gate

- Date-aware universe：`config/universe.csv` 的生命周期元数据决定每个 execution date 的 eligible 集合；不使用收益数据回填今天的 ETF 到历史。
- Asset lifetime metadata：RQAlpha instrument lifecycle 与本地 universe 已在 RL-031 交叉验证一致（12/12）。
- Fallback 上市前处理：S4C 沿用 S2 risk universe 与 511010.SS 防御资产；fallback 不可交易时不存在可执行 target，除非冻结语义已明确其他处理。
- Execution price 缺失处理：正权重只在 execution date `active` 且 canonical 价格有限为正时合法；NaN 不表示现金、持有、跳过或 fallback。
- Strategy inception：由完整冻结 target 首次可合法执行的日期定义，不是 dataframe 首日或首个 signal。
- 正目标可执行性：每个正目标在进入 RQAlpha 前必须通过 `validate_execution_targets`；失败即 `BLOCK`，不得以本地 cash 逻辑、手工 sizing 或 retry 修补。

以上前提由 Batch 04/05 的 PIT contract 建立；若 canonical 数据契约或策略语义变化使其失效，本 Goal 转为 `NO BACKTEST`。

## 预先冻结的范围

- skfolio `RiskBudgeting`；`RiskMeasure.VARIANCE`；equal risk budgets；long-only、fully invested、无杠杆；min eligible 6。
- Aligned returns center 固定为 60（价格窗口 61）；不得重测 40 或 80，不得择优窗口。
- 月末估计，下一 canonical observation execution；沿用既有 10/5 bps 费用与滑点、既有 PIT/lifecycle 规则与既有成本语义。
- 只做 frozen-target replay 进 RQAlpha；TactiCore 只负责冻结目标、映射代码、编排回放与有界 target tracking。

## 禁止

- 不改 covariance、window、risk measure；不添加集中度 cap；不做任何参数或邻域搜索。
- 不在 RQAlpha 内重算信号、波动或 fallback；不实现本地会计、现金预留、sizing、撮合或 retry。
- 不创建 candidate、不激活 prospective shadow、不修改 S2、Batch 05 冻结产物、外部证据 tier 或永久架构/规则。

## Protocol before result

执行前先冻结 protocol：Commit A = protocol + implementation + tests，且不产生真实结果；随后运行实验，Commit B = 结果 + ledger / catalog / current-state 同步。

Execution gates 必须在任何运行前于 protocol 中预先声明，沿用 Batch 05 execution-review 的 discipline：frozen dates 全覆盖、无额外日期、native cash rejection、execution-date deviation、material date 比例、平均现金、与 VectorBT baseline 的 CAGR/MaxDD 差异，以及所有 >5pp 差异必须有 native 解释。集中度只作诊断证据，不得转为优化触发。

任何实现缺陷必须走 `INVALID_RUN → 新 Protocol 版本 → freeze → 完整 rerun`，不得静默覆盖。

## 完成时

- 只有架构或职责边界变化才更新 `docs/ARCHITECTURE.md`；只有形成新的永久方法才更新 `docs/RESEARCH_RULES.md`。
- `docs/RESEARCH_LEDGER.md` 只追加决策条目；`docs/STRATEGY_CATALOG.md` 承担策略生命周期状态；`docs/CURRENT_STATE.md` 只保留当前前沿；实验数字写入 `research/results/`。
- 结束时给出 S4C 的明确执行结论与下一步有界问题，不顺手开启下一阶段。

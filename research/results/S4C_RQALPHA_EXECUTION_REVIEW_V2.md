# S4C RQAlpha execution review V2

Protocol V2 下对 **committed 冻结 ERC 目标日程**做一次 RQAlpha 6.3.0 原生 target-only 回放。冻结目标由 skfolio 官方 `RiskBudgeting`（variance / equal risk budget / long-only）在冻结语义下生成，RQAlpha 回调内不重算信号、波动或 ERC 权重。

## 冻结身份

| 属性 | 值 |
| --- | --- |
| 冻结目标文件 | [s4c_pit_corrected_frozen_targets_v1.csv](s4c_pit_corrected_frozen_targets_v1.csv) |
| row count | 161 |
| first / last execution date | 2013-04-01 / 2026-08-03 |
| SHA-256 | `f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47` |
| 结构校验 | 日期唯一且严格递增；权重非负；逐行合计为一；PIT `validate_execution_targets` 通过 |
| 语义再推导审计 | 以冻结语义重新推导的序列化与 committed artifact 逐字符相等 |

## VectorBT reproduction（Protocol V2 容差）

| Metric | baseline | observed | delta | tolerance | pass |
| --- | --- | --- | --- | --- | --- |
| CAGR | 0.1163753501739464 | 0.11637515674509435 | -1.9343e-07 | 1.0e-04 | yes |
| signed MaxDD | -0.1835119628859864 | -0.18351236292732442 | -4.0004e-07 | 1.0e-04 | yes |
| Sharpe | 1.0911209093079228 | 1.091119082443939 | -1.8269e-06 | 1.0911e-04 | yes |
| Calmar | 0.634156751111909 | 0.6341543146669736 | -2.4364e-06 | 1.0e-04 | yes |
| turnover | 11.79026465782429 | 11.790377273598702 | +1.1262e-04 | 1.1790e-03 | yes |

reproduction 整体 PASS。V1 的 `1e-12` 判据不可跨平台达成，已作为 [INVALID_RUN R1](INVALID_RUN_S4C_EXECUTION_R1.md) 保留并由 [Protocol V2](../batches/s4c_execution_review/PROTOCOL_V2.md) 取代。

## RQAlpha 原生结果

RQAlpha `6.3.0`，原生账户 / 撮合 / 整手 / 现金 / 成本 / 滑点，`order_target_portfolio`，`partial_fill_on_insufficient_cash=true`。

| 指标 | 值 |
| --- | --- |
| CAGR | 12.0929% |
| signed MaxDD | -18.3512% |
| Sharpe | 0.7758 |
| total return | 3.3829 |
| turnover | 11.2436 |
| transaction cost | 44,411.47 |
| native order count | 1,184 |
| trade count | 1,181 |
| native failed order events | 112 |
| **cash rejection events** | **0** |
| native cash-residual cancellation events | 0 |
| volume-limited events | 3 |
| ending cash | 550.60 |
| minimum cash | 0.1461 |
| average cash ratio | 0.1399% |

对比同冻结目标的 VectorBT replay（CAGR 11.6375%、signed MaxDD -18.3512%、Sharpe 1.0911、turnover 11.7904），RQAlpha 的 CAGR 高 0.46pp，MaxDD 差 0.0000pp。

## Target tracking

| 指标 | 值 |
| --- | --- |
| 处理日期 | 161 / 161 frozen dates，额外日期 0 |
| 平均 execution-date total absolute weight deviation | 0.3246% |
| 最大 deviation | 15.9521% |
| materially off-target execution dates | 3 / 161 = 1.86% |
| 提交订单的月份 / 实际成交月份 | 150 / 150 |
| 交易标的数 | 10 |
| annualized target-change months | 12.00 |

## Material execution differences

3/161 execution dates 超过组合层 tracking 阈值。其中两个 >5pp 的单资产 material difference 都有具体 native 解释；第三个日期是组合层偏离，最大单资产偏差 3.84pp、现金残差 3.80%。

机器可读的 [material differences](s4c_rqalpha_execution_material_differences_v2.csv) 只包含 **2 行**，因为该表按既有 5pp 单资产口径生成；第 3 个日期没有单资产差异超过 5pp，因此不产生条目，冻结协议也未要求为它提供 >5pp 的 native event 解释。

| date | 现象 | native 证据 |
| --- | --- | --- |
| 2014-05-05 | 513500.SS target 21.61% vs realized 16.48% | 市场单 205,000 股超过当前 bar 成交量 25% 上限，实际成交 156,200 股后被取消 |
| 2026-02-02 | 518880.SS target 9.44% vs realized 14.67% | 触及跌停价（`limit_down`）拒单 |
| 2015-01-05 | 组合层 total deviation 7.68%、cash residual 3.80%；单资产层面只有 513030.SS 偏离（13.80% → 9.96%，-3.84pp），其余标的差异均在 0.01pp 内 | 无单资产差异达到 5pp，因此 material-difference artifact 中没有该日条目；冻结 gate 的 explained 判据作用于该表，2015-01-05 是以“无 >5pp 单资产差异”满足判据，而不是以一条已记录的 native 原因满足 |

因此：前两行有明确记录的 native 原因；第三行在冻结口径下不产生未解释条目。这里不推测 513030.SS 未达目标的上游原因（现金残差 3.80% 与原生部分成交路径一致，但 runner 未为该日期记录 native order event，故不作断言）。

## 集中度背景（诊断证据，不是 gate）

Batch 05 的集中度证据保持为背景：median maximum weight 26.94%、P95 51.84%、maximum 66.35%、9 个月任一资产超过 50%、effective assets median 6.23 / P05 3.24。本审查未添加 cap，也未因集中日期执行不佳而重跑 40/80。

## 决定

所有预注册 gate（reproduction、native execution、economics、material difference 解释）均成立，机械决定为 **`ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW`**。

这只获得独立 candidate-freeze review 资格；未创建 candidate、未激活 prospective shadow、未替代 S2、未改变任何 S4C 经济语义。

## 机器可读证据

[V2 reproduction](s4c_rqalpha_execution_vectorbt_reproduction_v2.csv)、[native summary](s4c_rqalpha_execution_summary_v2.csv)、[target tracking](s4c_rqalpha_execution_target_tracking_v2.csv)、[material differences](s4c_rqalpha_execution_material_differences_v2.csv)、[user effort](s4c_rqalpha_execution_user_effort_v2.csv)。

## 尚未证明

本结果是历史 execution review 证据，不是前瞻样本外证据，也不是生产可交易性结论。集中度风险仍然存在且未被消除或优化。

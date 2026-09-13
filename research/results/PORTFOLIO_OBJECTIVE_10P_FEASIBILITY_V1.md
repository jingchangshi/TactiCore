# Portfolio Objective 10P — 可行性历史诊断 V1

## 执行结论

预注册裁决为 **`FEASIBLE_WITH_EXISTING_COMPONENTS`**：在不修改任何冻结候选语义的前提下，
两个已冻结组件的**固定粗粒度混合**在主评价窗口内已经出现达到组合 10% 量级的历史路径
（`BLEND_S2_25_S4C_75` after-cost CAGR 10.4849%）。

但该结论有三条必须同时成立的限定：

1. 这是**历史诊断**，不是未来收益预测，也不是生产批准；
2. 达到该量级依赖于对 `S4C_R1` 的较高权重（主窗口 25/75、共同窗口 50/50 及以上），
   即收益水平主要由 ERC 侧贡献，而 `S2_R1` 的贡献主要体现在回撤与机制分散；
3. 两个组件都还没有真正的锚前证据；`S4C_R1` 前瞻影子仍未激活。

运行与协议：

| 项 | 值 |
| --- | --- |
| 运行 HEAD | `44b8018`（Commit A 被独立复核接受后唯一一次运行） |
| 生效协议 | [PROTOCOL_V3](../batches/portfolio_objective_10p/PROTOCOL_V3.md)（V1/V2 为历史记录） |
| 运行命令 | `uv run python research/experiments/run_portfolio_objective_10p.py` |
| 组件 correctness | `component_correctness_ok=True`（详见 `portfolio_objective_10p_correctness_v1.csv`） |
| 组合引擎 | VectorBT `Portfolio.from_orders`（未建任何本地会计或执行框架） |

前置说明：本 Goal 的 V1 阶段曾被提前执行一次，其输出被判定为
`INVALID_FOR_RESEARCH_INTERPRETATION`、未提交并已移除；本报告的全部数字只来自上述被授权的一次运行。

## 1. 冻结输入与组合定义

| 输入 | SHA-256 |
| --- | --- |
| `research/results/s2_v2_frozen_targets.csv`（103 行，`SIGNAL_CHANGE_ONLY`） | `9cc5a8e7…0b61` |
| `research/results/s4c_pit_corrected_frozen_targets_v1.csv`（161 行，月频提交） | `f7bf398d…7e47` |

```text
T_i(t)     = 组件 i 在 t 或之前最后一次冻结提交的意图目标
T_blend(t) = w_S2 * T_S2(t) + w_S4C * T_S4C(t)
```

组合在提交日并集上提交，因此有自己的政策 `DERIVED_UNION_TARGET_SUBMISSION`。**语义边界必须随结果
一起陈述**：在单一 cash-sharing 组合中，target-percent 订单是组合级目标；S4C 的月度提交会把 S2
的贡献重新拉回其当前目标，即使 `S2_R1` 自身因 `SIGNAL_CHANGE_ONLY` 不会提交。因此

- 不得把内部 blend 说成"S2_R1 与 S4C_R1 在同一账户中原样运行"；
- 不得声称 blend 保持了 S2 单独运行时的执行政策行为；
- 两个 anchor 是**分别单独回放**的（S2 用其 103 行日程，S4C 用其 161 行日程），它们是各自候选
  的正确性参照；派生的 100/0 端点不是 standalone `S2_R1`。

## 2. 组件 anchor（独立回放，主窗口 2013-04-01 – 2026-08-31）

| 序列 | 提交政策 | CAGR | signed MaxDD | Sharpe | Calmar | Worst year | Turnover | 交易数 | 年化动作日 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `S2_R1_committed_anchor` | SIGNAL_CHANGE_ONLY（103 行） | 6.5713% | -26.1813% | 0.648 | 0.251 | -16.28% | 25.34 | 379 | 7.68 |
| `S4C_R1_committed_anchor` | MONTHLY_TARGET_SUBMISSION（161 行） | 11.6375% | -18.3512% | 1.091 | 0.634 | -8.07% | 11.46 | 575 | 11.11 |

组件身份与复现证据（`portfolio_objective_10p_correctness_v1.csv`）：两个 anchor 的冻结 SHA-256、
行数、日期唯一递增、行合计序列化容差、逐行 PIT 合法性与"回放输入逐值等于冻结 artifact"全部通过；
S4C 指标复现沿用**早于本 Goal** 的 portability 规则 `max(1e-4, 1e-4·|baseline|)` 并通过。
S2 的 correctness 是身份式的，其与旧全精度运行的指标差异仅作**描述性**报告（`descriptive_only`）。

## 3. 固定混合结果（主窗口）

| 序列 | S2/S4C | CAGR | signed MaxDD | Sharpe | Calmar | Worst year | Turnover | 交易数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `BLEND_S2_100_S4C_00`（派生端点） | 100/0 | 6.7142% | -26.1813% | 0.675 | 0.256 | -16.28% | 26.02 | 523 |
| `BLEND_S2_75_S4C_25` | 75/25 | 8.0167% | -20.5610% | 0.817 | 0.390 | -12.98% | 21.19 | 684 |
| `BLEND_S2_50_S4C_50` | 50/50 | 9.2696% | **-15.9165%** | 0.940 | 0.582 | -9.72% | 17.23 | 676 |
| `BLEND_S2_25_S4C_75` | 25/75 | **10.4849%** | -17.1282% | 1.034 | 0.612 | -7.12% | 13.66 | 667 |
| `BLEND_S2_00_S4C_100`（派生端点） | 0/100 | 11.6375% | -18.3512% | 1.091 | 0.634 | -8.07% | 11.46 | 575 |

裁决只使用三个**内部**固定 blend 与两个 standalone anchor；两个派生端点仅作上下文。
据此 `c_div = 10.4849% ≥ 10%`，得到 `FEASIBLE_WITH_EXISTING_COMPONENTS`。

## 4. 共同窗口与复杂度 vs S30（2014-01-15 – 2026-08-31）

S30 的 natural inception（`513500.SS` 上市）为 2014-01-15，运行时断言通过。

| 序列 | CAGR | signed MaxDD | Sharpe | Calmar | Worst year | Turnover | 交易数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `S30_REFERENCE`（复杂度门槛） | 9.9249% | -15.0381% | 1.114 | 0.660 | -5.47% | 1.15 | 27 |
| `S2_R1_committed_anchor` | 8.6391% | -22.4611% | 0.840 | 0.385 | -4.57% | 21.33 | 379 |
| `S4C_R1_committed_anchor` | 12.7285% | -18.3512% | 1.153 | 0.694 | -8.07% | 10.96 | 575 |
| `BLEND_S2_75_S4C_25` | 9.8382% | -17.1014% | 0.984 | 0.575 | -5.33% | 18.09 | 684 |
| `BLEND_S2_50_S4C_50` | 10.8404% | -15.9165% | 1.068 | 0.681 | -6.21% | 15.01 | 676 |
| `BLEND_S2_25_S4C_75` | 11.8127% | -17.1282% | 1.125 | 0.690 | -7.12% | 12.31 | 667 |

预注册报告规则给出 `COMPLEXITY_CLEARS_S30_HURDLE`（内部 blend 最高 CAGR 相对 S30 为
`+1.888pp ≥ +0.5pp`）。如实解读：

- `50/50` 相对 S30 为 `+0.916pp` CAGR、signed MaxDD 略差（-15.92% vs -15.04%）、Sharpe 略低
  （1.068 vs 1.114）；`25/75` 为 `+1.888pp` CAGR，但 signed MaxDD 差约 `-2.09pp`、Sharpe 相近。
- 也就是说，动态复杂度换取的是**收益量级**，代价是**更深的回撤与更高的维护负担**（S30 年化动作
  1.03 次，blend 约 11.85 次）。没有任何 blend 在 Sharpe 上超过 S4C 单独运行。

## 5. 分散度证据

| 序列 | S2/S4C | CAGR | 加权 anchor CAGR | 超出加权 anchor | signed MaxDD | 优于最好 anchor | Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| 100/0 | 100/0 | 6.7142% | 6.5713% | +0.1429pp | -26.1813% | 否 | 0.675 |
| 75/25 | 75/25 | 8.0167% | 7.8378% | +0.1788pp | -20.5610% | 否 | 0.817 |
| 50/50 | 50/50 | 9.2696% | 9.1044% | +0.1652pp | -15.9165% | **是** | 0.940 |
| 25/75 | 25/75 | 10.4849% | 10.3710% | +0.1139pp | -17.1282% | **是** | 1.034 |

两个冻结机制的日收益相关性为 **0.7835**，下行相关性为 **0.6541**（2013-04-02 – 2026-08-31，
3260 个观测）。解读：

- 每个 blend 的 CAGR 都高于同权重的 anchor 加权值，说明组合不是两个 CAGR 的简单加权；
- `50/50` 与 `25/75` 的 signed MaxDD 优于**任何一个单独 anchor**，这是 S2 作为下行分散机制的
  直接证据；
- 下行相关性明显低于全样本相关性，说明两个机制在不同市场状态下的暴露并不相同；
- 但没有任何 blend 的 Sharpe 超过 `S4C_R1` 单独运行；S2 的价值是**回撤与机制分散**，
  不是提高风险调整后收益。

## 6. 分期与滚动

四个固定分期的 CAGR（区间起于各期首个 canonical 观测日）：

| 序列 | 2013–2016 | 2017–2019 | 2020–2022 | 2023–2026 |
| --- | ---: | ---: | ---: | ---: |
| `S2_R1_committed_anchor` | 3.2759% | 7.0697% | 3.6306% | 12.3550% |
| `S4C_R1_committed_anchor` | 9.4090% | 9.1512% | 5.6429% | 21.4205% |
| `BLEND_S2_50_S4C_50` | 6.6980% | 8.1392% | 4.8549% | 16.8799% |
| `BLEND_S2_25_S4C_75` | 8.1025% | 8.6624% | 5.2796% | 19.1644% |

四个分期均为正 CAGR；`2020–2022` 是所有序列最弱的区间（组合仍为正）。滚动证据
（`portfolio_objective_10p_rolling_v1.csv`）：3 年与 5 年窗口的 **positive-CAGR 占比对全部序列均为
100%**；5 年 CAGR 中位数分别为 S2 7.14%、S4C 9.97%、50/50 8.99%、25/75 9.57%。

## 7. Gap 分析

| Gap | 当前状态 | 说明 |
| --- | --- | --- |
| `RETURN_GAP` | 小 | 内部固定 blend 已在历史主窗口达到 10.48%；目标量级不需要新的收益来源 |
| `DRAWDOWN_GAP` | 中等 | 达到 10% 的组合历史上对应 signed MaxDD 约 -15.9% 至 -17.1%（共同窗口），比 S30 更深 |
| `DIVERSIFICATION_GAP` | 部分关闭 | 50/50 与 25/75 的回撤优于任一 anchor；但 Sharpe 未超过 S4C，分散收益主要体现在回撤 |
| `EXECUTION_GAP` | 已建立、未前瞻验证 | S2 与 S4C 的历史执行闭环均已通过 RQAlpha 6.3.0 原生审查；派生组合本身**没有**独立执行审查 |
| `PROSPECTIVE_EVIDENCE_GAP` | **最大** | S2 R1 前瞻影子仍在积累；S4C R1 前瞻影子未激活；组合层没有任何前瞻观测 |
| `DATA_GAP` | 已封闭（有界） | canonical 契约、生命周期与 PIT 已建立；未解决的是幸存者/工具域偏差这一长期限制 |
| `MAINTENANCE_GAP` | 明确 | blend 年化动作日约 11.85 次，S30 约 1.03 次；复杂度确实需要更高维护 |

**关键判断**：当前真正的 blocker 是 `PROSPECTIVE_EVIDENCE_GAP`，**不是**缺少 alpha 策略。
历史 return gap 很小，而前瞻证据为零。

## 8. 经济角色判断

| 组件 | 机制 | 在本组合中的角色 |
| --- | --- | --- |
| `S30` | 固定 25/25/25/25 静态战略配置 | 复杂度门槛：单独即达 9.92%（其自身窗口），说明 10% 量级主要是长期多资产 beta / 战略配置问题 |
| `S2_R1` | 时序趋势 + 单资产防御切换 | 机制分散与回撤控制：单独 CAGR 最低，但 50/50 把 signed MaxDD 从 -18.35% 改善到 -15.92%，且下行相关性低于全样本 |
| `S4C_R1` | 无杠杆 ERC 风险预算 | 收益引擎 + 风险分配引擎兼有：收益量级的主要来源，但集中度（P95 最大权重 51.84%）是其已知候选风险 |

对"10% 是否已经是 beta 问题"的独立判断：**在很大程度上是**。S30 单独即达 9.92%，
S4C 单独达 11.64%，而 25% 权重的 S2 只把量级抬高约 0.1–0.2pp（相对加权 anchor）。
因此战术机制的首要任务应被理解为改善回撤、regime 稳健性、执行与分散度，而不是制造额外 CAGR。

## 9. 风险包络建议（建议，不是永久规则）

本 Goal **不**声明永久 MaxDD 阈值。历史证据中"约 10% 量级"对应的取舍大致为：

```text
CAGR                 9.3% – 10.5%（主窗口 50/50、25/75）
signed MaxDD         -15.9% – -17.1%
Sharpe               0.94 – 1.03
Calmar               0.58 – 0.61
Worst year           -9.7% – -7.1%
年化动作日            约 11.9
```

这是**建议性包络**，用于之后的候选/生产讨论提供参照；它不是 gate，也不应直接写入
`RESEARCH_RULES.md`。

## 10. 最终裁决

```text
OBJECTIVE_FEASIBILITY_DECISION = FEASIBLE_WITH_EXISTING_COMPONENTS
```

理由与限定：内部固定 blend 在历史主窗口达到 10.4849% after-cost CAGR，并在共同窗口达到
10.84%/11.81%（50/50 与 25/75），因此"现有经济机制是否支持 10% 目标"的答案是支持。
但该量级依赖对 S4C 的较高权重，且没有任何前瞻观测；组合层也没有独立执行审查。

## 11. 本结果不证明

- 不证明未来收益、不证明 10% 会重复、不把历史可行性称为 expected future return；
- 不证明组合历史冻结目标日程在 RQAlpha 下的原生可执行性（本实验只做 VectorBT 研究层诊断）；
- 不证明 S4C R1 前瞻有效性，也不激活其前瞻影子；
- 不构成生产配置、不创建任何候选身份（无 `S31` / `Portfolio_R1` / `Blend_R1`）；
- 不证明 S2 或 S4C 单独运行的执行政策在组合中保持不变（见第 1 节语义边界）。

## 12. 架构漂移与禁止事项审计

- 复用 VectorBT `Portfolio.from_orders`、订单/交易/回撤记录与既有 PIT 校验；**未**建设第三套会计、
  执行模拟器、optimizer、`PortfolioEngine`、`StrategyMixer` 或通用 blend 框架；
- 未修改 `S2_R1` / `S4C_R1` 的 manifest、日程、语义、verifier，也未修改 config、canonical 数据、
  universe 或任何既有冻结证据；
- 未添加杠杆、未添加 S4C 集中度 cap、未搜索权重、未使用细粒度权重、未按历史最佳点选配置；
- `ARCHITECTURE.md`、`RESEARCH_RULES.md` 未因实验数字而修改；
- correctness gate 在 fail-closed 顺序下先于任何组合层计算执行。

机器可读证据：

```text
portfolio_objective_10p_summary_v1.csv          主窗口（不含 S30）
portfolio_objective_10p_common_window_v1.csv   共同窗口（含 S30）
portfolio_objective_10p_diversification_v1.csv 分散度证据
portfolio_objective_10p_correctness_v1.csv      identity / portability 证据
portfolio_objective_10p_periods_v1.csv
portfolio_objective_10p_rolling_v1.csv
portfolio_objective_10p_correlation_v1.csv
portfolio_objective_10p_annual_returns_v1.csv
```

## 13. 下一项研究决策

本报告只回答可行性。下一单位研究预算的选择属于独立的 research-priority decision，由 Commit C
单独记录；本文件不预先决定，也不自动启动任何下一 Goal。

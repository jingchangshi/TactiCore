# Portfolio Objective 10P — 预注册协议 V1

> 状态：由 [`PROTOCOL_V2.md`](PROTOCOL_V2.md) 取代裁决基础、窗口归属、年度报告口径、复现容差与
> 输出 schema。V1 保留为历史记录，本文件其余条款继续有效。

本协议在任何 blend 结果产生之前提交（Commit A）。它只回答一个问题，且只做历史诊断。

## 1. 唯一问题

```text
在不修改 S2_R1 / S4C_R1 任何冻结语义的前提下，
简单固定混合是否已经能形成接近或达到长期 10% CAGR 的合理 risk-return profile？
```

这是 historical diagnostic。它不是新候选、不是 production portfolio、不是真正的 prospective result。

## 2. External Evidence Gate

本 Goal 不提出新的策略族、signal、allocator 或 overlay。它只做**已冻结组件之间的固定权重组合**，
因此不创建新的 canonical mapping；两个组件各自的 canonical mapping 与 tier 保持不变。

| 项 | S2_R1 | S4C_R1 | S30（比较器） |
| --- | --- | --- | --- |
| Canonical mapping | time-series momentum / trend following | equal risk contribution / risk budgeting | 1/N 与 static diversified allocation |
| External tier | `E1_MATURE` | `E2_ESTABLISHED_METHOD` | `E1_MATURE` |
| External conclusion | 跨资产期货趋势证据成熟，域不等于长多 ETF | 成熟构造方法，不是 alpha 主张 | 强估计误差复杂度基准，不是 alpha 主张 |
| Relevant contradictions | 期货/多空/波动缩放域不匹配；ETF 转移待验 | 协方差与相关性估计、无约束下的集中度、无杠杆 ETF 实现 | 权重依赖投资者目标 |
| Upstream implementation | VectorBT 原生组合记录 | 官方 skfolio `RiskBudgeting`；RQAlpha 6.3 原生执行 | VectorBT 原生组合记录 |
| Existing TactiCore evidence | RL-015 参数平台、RL-016 冻结、RL-017 前瞻协议 ACTIVE | RL-030/RL-037/RL-040、RL-042 冻结 | RL-024 |
| Remaining local gap | 前瞻本地稳定性 | 前瞻影子未激活；集中度为已知候选风险 | 机制匹配的简单比较器 |
| Research action | `TRANSFER_VALIDATE`（本 Goal 不执行） | `UPSTREAM_COMPARE`（本 Goal 不执行） | `REFERENCE_ONLY` |

固定权重组合本身不是 canonical strategy，不构成新的外部主张，也不改变任何 tier。

## 3. PIT Tradability Gate

沿用 RL-031 / RL-033 / RL-034 已关闭的 PIT contract，本 Goal 不重新审计它：

```text
date-aware universe        : config/universe.csv 的生命周期 metadata
asset lifetime metadata    : tacticore/data/tradability.py
上市前 fallback 处理        : 冻结组件的完整 target contract 已定义；本 Goal 不新增 fallback 规则
execution price 缺失处理    : 正目标只在 execution timestamp 上 active 且 canonical 价格有限、正值时合法
strategy inception         : S2_R1 与 S4C_R1 均为 2013-04-01
每个正目标是否可执行        : 由 run_target_weights → validate_execution_targets 强制
```

任何 blend 的每一行目标都必须通过 `validate_execution_targets`，否则整轮结果作废。若目标在
inactive 或 NaN-priced 标的上为正，必须直接失败，而不是让 VectorBT 静默解释。

## 4. 冻结输入（只读）

| 输入 | SHA-256 |
| --- | --- |
| `research/results/s2_v2_frozen_targets.csv` | `9cc5a8e70751f274cb7c4f900784400bd8de684450833ba6d4034fd75ca70b61` |
| `research/results/s4c_pit_corrected_frozen_targets_v1.csv` | `f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47` |

两个候选的 manifest、verifier 与冻结语义均不改写。canonical 数据、universe、`config/strategy.toml`
与 `config/s30_static_allocation.toml` 均只读。

## 5. 组合定义（预注册）

```text
component target state:   T_i(t) = 组件 i 在 t 或之前最后一次冻结提交的意图目标
derived portfolio target: T_blend(t) = w_S2 * T_S2(t) + w_S4C * T_S4C(t)
```

- `T_i(t)` 前向保持的是**组件已经冻结的目标决定**，不是价格，也不是任何未知行情。
- 资产列取 canonical universe 全列；组件未使用的列按 0 处理（S4C 的 `511260.SS`、`511880.SS`
  恒为 0；S2 的日程只含 10 列）。不得因此改写任一冻结 CSV。
- 已提交冻结日程以 8 位小数保存，S2 的 1/9 sleeve 因此合计为 `0.99999999`。逐行合计只允许
  `|sum - 1| <= 1e-7` 的定点舍入容差；不重新归一化、不修改任何冻结数值。

派生组合在**两个组件提交日的并集**上提交，因此它有自己的新政策：

```text
DERIVED_UNION_TARGET_SUBMISSION
```

已核实 S2 的 103 个提交日全部落在 S4C 的 161 个提交日之内，所以并集等于 S4C 的月频日程。

**语义声明（必须随结果陈述）**：在单一 cash-sharing 组合中，target-percent 订单是组合级目标。
S4C 的月度提交会把 S2 的贡献重新拉回其当前目标，即使 S2_R1 自身因 `SIGNAL_CHANGE_ONLY`
不会提交。因此：

```text
不得把内部 blend 说成"S2_R1 与 S4C_R1 在同一账户中原样运行"
不得声称 blend 保持了 S2 单独运行时的执行政策行为
不得把派生的 100/0 端点当作 standalone S2_R1，或据此声明复现
```

组件自身的 anchor 必须**单独回放**（S2 用其 103 行 `SIGNAL_CHANGE_ONLY` 日程，S4C 用其 161 行
月频日程），作为各自候选的正确性参照。冻结的组件目标生成语义与产物完全没有被改动；本实验评估的
只是一个显式派生的组合构造政策。

## 6. 固定权重（预注册，禁止增删）

```text
(S2, S4C) = (100, 0) / (75, 25) / (50, 50) / (25, 75) / (0, 100)
```

禁止 63/37、22/78 等为了接近 10% 而产生的细粒度权重，禁止按历史最佳点选择"最终配置"。

## 7. 评估窗口（预注册）

```text
主窗口（S2 / S4C / 五个 blend）: 2013-04-01 .. 2026-08-31
S30 比较窗口（全部序列）        : S30 自然 inception（513500.SS 上市）.. 2026-08-31
```

S30 的 inception 由 `build_execution_weights` 在运行时导出并断言，不硬编码。两个窗口都必须在结果中
显式标注；不得为了获得更长历史而降低 PIT 标准，也不得把任一历史区间称为真正样本外。

## 8. 序列（预注册）

```text
1. S2_R1_committed_anchor    103 行冻结日程 + SIGNAL_CHANGE_ONLY（可复现性 gate）
2. S4C_R1_committed_anchor   161 行冻结日程 + MONTHLY_TARGET_SUBMISSION（可复现性 gate）
3. S30_REFERENCE             复杂度门槛（只作参考，不升级为候选，不是第三个组件）
4. BLEND_S2_100_S4C_00       派生端点 (1.00, 0.00)
5. BLEND_S2_75_S4C_25        派生内部点 (0.75, 0.25)
6. BLEND_S2_50_S4C_50        派生内部点 (0.50, 0.50)
7. BLEND_S2_25_S4C_75        派生内部点 (0.25, 0.75)
8. BLEND_S2_00_S4C_100       派生端点 (0.00, 1.00)
```

端点仅用于几何/上下文，必须标注为派生端点；可行性裁决建立在真实的内部固定 blend 与两个显式
候选 anchor 上，不得把两者混为一谈。

## 9. 指标（预注册）

每个序列报告：CAGR、signed MaxDD、Sharpe、Calmar、worst year、turnover、trade count、average
holding days、submission count、annualized submission count、actual order days、rolling 3Y/5Y CAGR
与 positive share、四个固定分期。

额外描述性统计：两个冻结机制日收益的 full-sample 相关性与 downside 相关性；以及每个 blend 相对
两个 anchor 的加权 CAGR、增量 CAGR、signed MaxDD 与 Sharpe 改善（"客观接近目标"与"机制分散证据"
分开报告，不允许"历史 CAGR 最高者获胜"）。

不为此建设通用 analytics platform：只使用 VectorBT 原生订单/交易/回撤记录与既有研究 helper。

## 10. 复现 gate（先于任何比较）

结果可信的前提是 anchors 能复现已提交证据：

```text
S2_R1_committed 在 2013-03-29..2026-08-31 上必须复现 s2_parameter_plateau_summary.csv 的 trend_window=200 行
                （cagr / max_drawdown / sharpe / calmar 容差 1e-9，turnover 容差 1e-6）
S4C_R1_committed 必须复现 s4c_pit_corrected_comparison_v1.csv 的 committed 行
                （cagr / max_drawdown / sharpe / calmar / turnover 容差 1e-12）
```

任一失败即 `BLOCKED_BY_CORRECTNESS`，不得继续解释 blend。

## 11. 裁决规则（预注册）

不定义 `CAGR >= 10% → PASS / else FAIL`，也不采用"历史最高者获胜"。令 `c_max` 为五个派生 blend
的最大 after-cost CAGR，
`c_div` 为三个内部 blend（75/25、50/50、25/75）的最大值：

```text
if 复现 gate 失败                              → BLOCKED_BY_CORRECTNESS
if c_div >= 10.0%                              → FEASIBLE_WITH_EXISTING_COMPONENTS
if c_max >= 10.0% > c_div                      → FEASIBLE_BUT_DEPENDS_TOO_HEAVILY_ON_ONE_COMPONENT
if 9.5% <= c_max < 10.0%                       → PLAUSIBLE_BUT_PROSPECTIVE_EVIDENCE_INSUFFICIENT
if c_max < 9.5%                                → NOT_SUPPORTED_BY_EXISTING_COMPONENTS
```

`9.5%` 是预注册的"历史缺口小于估计误差量级"边界，不构成收益预测。无论裁决如何，都必须声明历史
可行性不等于未来收益，且任何生产决定都需要前瞻证据与独立的生产审查。

## 12. 复杂度 vs S30（预注册的报告规则）

在 S30 比较窗口上，取 CAGR 最高的 blend 与 S30 比较：

```text
COMPLEXITY_CLEARS_S30_HURDLE        if ΔCAGR >= +0.5pp 或 Δsigned MaxDD >= +2pp
COMPLEXITY_NOT_JUSTIFIED_BY_THIS_EVIDENCE   otherwise
```

这不是候选 gate，只是一条如实报告规则。

## 13. 输出 schema

```text
research/results/portfolio_objective_10p_summary_v1.csv           主窗口
research/results/portfolio_objective_10p_common_window_v1.csv     S30 比较窗口
research/results/portfolio_objective_10p_diversification_v1.csv   分散度证据
research/results/portfolio_objective_10p_periods_v1.csv
research/results/portfolio_objective_10p_rolling_v1.csv
research/results/portfolio_objective_10p_correlation_v1.csv
research/results/portfolio_objective_10p_annual_returns_v1.csv
research/results/PORTFOLIO_OBJECTIVE_10P_FEASIBILITY_V1.md
```

Commit A 只包含目标文档、本协议、实验实现与契约测试，**不生成任何** `research/results/` 产物；
结果只在 Commit B 中由显式运行产生。

## 14. 禁止事项与停止条件

```text
不搜索最优 strategy mix；不微调 blend 权重
不修改 S2_R1 或 S4C_R1（manifest、日程、语义、verifier）
不添加杠杆；不添加 S4C concentration cap
不为 CAGR 开新 strategy；不重开任何 REJECTED / CLOSED 策略
不建设 generic portfolio framework / optimizer / analytics platform
不回填历史-前瞻边界；不把历史可行性称为 expected future return
不创建 S31 / S32 / Portfolio_R1 / Blend_R1 等候选
```

看到结果后不得新增权重、不得修改目标、不得更换 comparator、不得改动风险评价。

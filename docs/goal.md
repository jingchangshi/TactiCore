# Goal: Bootstrap TactiCore — Low-Frequency Multi-Asset Tactical Allocation Research System

Repository:

```text
https://github.com/jingchangshi/tacticore
```

你正在作为：

```text
Principal Quant Research Engineer
+
Quant Systems Architect
+
Research Correctness Reviewer
```

工作。

本项目名称：

```text
TactiCore
```

全称：

```text
Low-Frequency Multi-Asset Tactical Allocation Research System
```

---

# 0. 第一原则：始终记住为什么要建立这个新仓库

TactiCore 不是 DailyETF 的重写版。

TactiCore 的建立，是因为 DailyETF / TacticalETF 在长期开发过程中逐渐把大量工程投入消耗在：

```text
自研 backtest engine
自研 reference engine
provider capability framework
data semantic governance
artifact lifecycle
复杂 frozen evidence
generic experiment governance
portfolio accounting
交易撮合
corporate action correctness
通用 infrastructure correctness
```

最终导致大量 Codex 工作没有直接转化为：

```text
更好的策略
更可信的 alpha
更可靠的资产配置
更少的实际交易次数
更好的风险收益比
```

TactiCore 必须从架构上防止再次走上这条路。

牢记：

```text
Research Infrastructure != Alpha

Backtest Engine != Strategy

More Infrastructure != Better Return

TactiCore exists to research robust low-frequency strategies,
not to build another quantitative trading platform.
```

---

# 1. 项目最终目标

TactiCore 的目标不是开发通用量化框架。

最终产品应该回答一个非常具体的问题：

> 在当前市场状态下，一个没有时间高频盯盘的个人投资者，应该持有什么资产、持有多少，以及现在是否需要操作？

系统面向：

```text
Low-Frequency
Multi-Asset
Tactical Allocation
```

而不是：

```text
High-Frequency Trading
Intraday Trading
Market Making
Generic Quant Platform
Universal Backtesting Framework
```

最终生产输出应接近：

```text
Current Portfolio
Target Portfolio

Asset A   20% -> 20%
Asset B   20% -> 30%
Asset C   20% -> 20%
Gold      20% -> 20%
Cash      20% -> 10%

Action:
Reduce cash
Increase Asset B

or:

NO ACTION
```

绝大多数交易日允许、甚至鼓励输出：

```text
NO ACTION
```

---

# 2. 用户的现实约束

所有架构与策略设计必须始终考虑：

```text
用户没有时间频繁交易
不希望日内盯盘
不追求高换手
不局限于 A 股 ETF
可以研究全球多资产
希望系统每日可以计算，但实际交易频率较低
```

推荐目标：

```text
signal computation:
daily

normal rebalance:
weekly / biweekly / monthly

actual trades:
尽量控制在每月 0~4 次附近

portfolio holding horizon:
weeks to months
```

这不是绝对硬编码限制。

但任何明显增加换手率的策略，都必须证明：

```text
新增收益
>>
交易成本
+
执行复杂度
+
人工维护成本
```

否则不应进入主线。

---

# 3. 核心架构原则

## 3.1 不允许建设第三套回测引擎

TactiCore 的核心双引擎：

```text
VectorBT
+
RQAlpha
```

职责必须明确区分。

### VectorBT

用于：

```text
idea exploration
parameter sweep
cross-sectional ranking
sensitivity analysis
walk-forward analysis
parameter robustness
strategy comparison
large-scale research iteration
```

它回答：

> 这个策略是否值得继续研究？

---

### RQAlpha

用于：

```text
authoritative event-driven backtest
portfolio accounting
cash
position
transaction cost
slippage
order execution
dividend
corporate action
suspension
Chinese market trading semantics
```

它回答：

> 在更接近真实交易语义的情况下，这个策略是否仍然成立？

---

明确禁止：

```text
自研 Reference Engine
自研 Generic Backtest Engine
第三套 Portfolio Simulator
第三套 Accounting Engine
```

除非未来存在一个非常具体、被真实策略 blocker 证明无法由 RQAlpha / VectorBT 解决的问题。

即使出现这种情况，也必须先：

```text
document blocker
prove necessity
implement smallest possible adapter
```

禁止为了“架构完整性”新增基础设施。

---

# 4. 数据原则

数据层必须保持：

```text
thin
replaceable
strategy-oriented
```

允许未来支持：

```text
Tushare
RQData
AKShare
Yahoo Finance
Stooq
FRED
其他可靠公开/付费数据源
```

但是不要在第一阶段创建：

```text
generic provider framework
provider capability matrix
provider governance plane
universal economic semantic engine
```

数据层只实现当前策略真正需要的数据。

原则：

```text
Data work must be demand-driven by strategy research.
```

如果当前策略只需要：

```text
OHLCV
trading calendar
basic instrument metadata
```

就只实现这些。

---

# 5. Universe 设计

TactiCore 不再局限 A 股 ETF。

长期 universe 可以包含：

```text
A-share ETFs
Hong Kong ETFs
QDII ETFs
US ETFs
Global equity ETFs
Bond ETFs
Gold
Commodity proxies
Cash / money-market proxy
Index / macro series for regime signals
```

必须区分：

```text
Tradable Instrument
vs
Research / Regime Reference Series
```

优先采用：

```text
Tradable Instrument First
```

而不是重新进入 DailyETF 的：

```text
Abstract Economic Exposure
→ 找 Total Return Index
→ 证明 semantic correctness
→ ETF mapping
```

主组合收益应尽可能来自：

```text
真实可交易 instrument
```

指数、宏观序列主要用于：

```text
benchmark
regime
risk signal
relative-strength reference
macro confirmation
```

---

# 6. 第一阶段策略方向必须严格受控

初始只允许三条主要策略线：

```text
S1 Global Dual Momentum

S2 Multi-Asset Trend Following

S3 China Sector / Theme Rotation
```

不要第一轮就建立几十个 strategy。

---

## S1 — Global Dual Momentum

主要研究：

```text
Absolute Momentum
+
Relative Momentum
```

候选资产例如：

```text
China equity
US equity
HK equity
Japan equity
Gold
Bond
Cash
```

策略回答：

> 当前最值得承担哪些大类资产风险？

---

## S2 — Multi-Asset Trend Following

主要研究：

```text
medium-term trend
moving-average filter
volatility-aware allocation
risk-on / risk-off
```

策略回答：

> 当前是否应该承担风险？

---

## S3 — China Sector / Theme Rotation

吸收 DailyETF / TacticalETF 已经积累的策略研究思想，例如：

```text
创新药
科技
电网
红利
资源
消费
金融
新能源
其他行业/主题 ETF
```

但研究重点应是：

```text
medium-term momentum
relative strength
trend
regime
crowding
fund flow
valuation where useful
```

不是预测明天哪个 ETF 上涨。

---

# 7. 从 DailyETF 继承什么

禁止直接复制整个 DailyETF。

TactiCore 应继承的是：

```text
knowledge
lessons
strategy hypotheses
research findings
failed strategy lessons
data pitfalls
look-ahead lessons
return semantics lessons
risk-management ideas
rotation ideas
regime ideas
```

而不是：

```text
old infrastructure
old backtest engine
old reference engine
old artifact machinery
old generic governance
```

需要创建：

```text
docs/LESSONS_FROM_DAILYETF.md
```

作为知识迁移入口。

必须说明：

```text
What we keep
What we intentionally abandon
Why
```

---

# 8. Alpha-First Development Rule

这是整个仓库最重要的开发原则之一。

每次准备新增代码前必须问：

> 这项工作是否直接提高我们判断策略有没有经济价值的能力？

如果答案是否定的：

```text
STOP
```

默认禁止主动建设：

```text
generic DAG
generic workflow engine
generic plugin system
generic data platform
generic experiment database
generic artifact lifecycle
generic governance system
generic scheduler
UI platform
generic broker abstraction
```

除非存在真实 blocker。

---

# 9. 研究目标优先级

策略评价不得只看 CAGR。

至少按以下维度评估：

```text
CAGR
Max Drawdown
Calmar
Sharpe
Worst Year
Turnover
Trade Count
Average Holding Period
Parameter Stability
Regime Stability
Walk-Forward Stability
Out-of-Sample Stability
Transaction-Cost Sensitivity
```

更偏好：

```text
moderate CAGR
+
smaller drawdown
+
lower turnover
+
parameter robustness
```

而不是：

```text
maximum backtest CAGR
```

例如：

```text
Strategy A:
CAGR 12%
MaxDD -35%

Strategy B:
CAGR 9.5%
MaxDD -14%

```

不能仅因为 Strategy A CAGR 更高就判定 A 更好。

---

# 10. Parameter Robustness Rule

禁止：

```text
寻找一个最佳参数
```

优先寻找：

```text
parameter plateau
```

例如：

```text
lookback = 80 / 100 / 120 / 140 / 160
```

如果仅：

```text
lookback = 117
```

表现异常突出，而附近参数显著恶化，应视为强烈过拟合信号。

VectorBT 应主要帮助完成这种研究。

---

# 11. 第一阶段 Milestones

当前只实现：

```text
M0 Repository Bootstrap

M1 Minimal Multi-Asset Universe

M2 Global Dual Momentum Baseline
```

不要提前实施：

```text
S2
S3
production broker
live trading
UI
复杂调度
完整日报系统
ML
AI strategy generation
```

---

# 12. M0 — Repository Bootstrap

建立最小仓库结构。

建议：

```text
tacticore/
├── README.md
├── pyproject.toml
├── .gitignore
│
├── tacticore/
│   ├── data/
│   ├── engines/
│   ├── strategies/
│   ├── portfolio/
│   └── research/
│
├── config/
│
├── research/
│   └── experiments/
│
├── tests/
│
└── docs/
    ├── ARCHITECTURE.md
    ├── RESEARCH_RULES.md
    ├── STRATEGY_CATALOG.md
    ├── LESSONS_FROM_DAILYETF.md
    └── CURRENT_STATE.md
```

保持简单。

如果实际实现不需要某个目录，不要为了满足目录图而创建空 abstraction。

---

# 13. M1 — Minimal Multi-Asset Universe

第一阶段只建立一个非常小的 canonical research universe。

目标：

```text
approximately 10–20 assets
```

用于验证 Global Dual Momentum。

覆盖：

```text
China equity
US equity
HK equity
Japan or developed ex-US equity
Gold
Bond
Cash proxy
```

如果某资产暂时没有可靠数据：

```text
do not build infrastructure to solve the entire data world
```

先选择可可靠获得的 representative instrument。

记录：

```text
symbol
asset_class
region
currency
tradable/reference
data_source
start_date
```

即可。

---

# 14. M2 — Global Dual Momentum Baseline

实现第一个最简单、可解释、低频 baseline。

必须尽量简单，例如：

```text
rebalance:
monthly

absolute momentum:
N-month return > 0

relative momentum:
rank eligible assets by N-month return

hold:
top K

fallback:
bond / cash / defensive asset
```

不要第一版就加入：

```text
10 个 technical indicators
复杂宏观模型
ML model
dynamic Bayesian regime model
```

第一目标是建立一个：

```text
transparent
reproducible
low-turnover
easy-to-understand
baseline
```

---

# 15. VectorBT / RQAlpha 第一阶段职责

实现最薄 adapter。

## VectorBT adapter

只需要能：

```text
consume canonical price data
run baseline strategy
return portfolio equity / trades / metrics
```

---

## RQAlpha adapter

只需要能：

```text
represent equivalent strategy logic
run event-driven validation
obtain comparable portfolio/trade metrics
```

如果当前环境下完整 RQAlpha 数据 bundle 或外部数据接入存在现实障碍：

不要因此建设大量 infrastructure。

应该：

```text
document exact blocker
complete everything possible offline
leave a bounded next action
```

---

# 16. Differential Validation 原则

允许比较：

```text
VectorBT
vs
RQAlpha
```

但目标不是 bit-for-bit identical。

需要重点比较：

```text
rebalance date
selected assets
target weight
trade direction
portfolio return
turnover
transaction costs
```

如果有差异：

优先解释：

```text
execution timing
fee model
price convention
corporate action
rounding
market rule
```

禁止创建：

```text
third reference engine
```

来“仲裁”。

---

# 17. 测试要求

测试应该主要覆盖：

```text
strategy logic
look-ahead prevention
rebalance timing
ranking
missing data behavior
portfolio weight invariants
adapter correctness
```

不要为了追求高 coverage 创建大量无经济价值测试。

重点测试：

```text
economic correctness
```

而不是：

```text
line coverage vanity metric
```

---

# 18. 文档必须是每轮工作的第一等产物

这是长期强制要求。

每完成一次 Goal，都必须刷新：

```text
docs/CURRENT_STATE.md
```

并在需要时更新：

```text
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/STRATEGY_CATALOG.md
docs/LESSONS_FROM_DAILYETF.md
README.md
```

文档必须与当前代码真实状态一致。

禁止：

```text
代码已经改变
文档仍描述旧架构
```

---

# 19. 每轮必须帮助用户理解发生了什么

每个 Goal 完成后，不仅要告诉用户：

```text
modified files
tests passed
commit SHA
```

还必须用面向系统负责人的方式解释：

## What We Changed

具体做了什么。

## Why We Changed It

为什么当前整体方案需要这项工作。

## What It Enables

它现在使我们能够研究/验证什么以前不能做的事情。

## What It Does NOT Solve

明确说明：

```text
哪些问题仍然没有解决
```

防止用户误以为某个 infrastructure feature 就等于策略有效。

## Architecture Impact

说明：

```text
是否改变整体架构
如果没有，明确说没有
如果有，为什么改变
```

## Strategy Impact

说明：

```text
对实际 alpha research 有什么影响
```

## Complexity Impact

说明本轮：

```text
增加了多少复杂度
删除了什么复杂度
是否出现 infrastructure creep
```

## Next Decision

不是简单列 TODO。

必须告诉用户：

> 当前证据下，下一步最值得做的唯一主方向是什么，以及为什么。

---

# 20. Architecture Drift Check

每轮完成前必须显式检查：

```text
Did we accidentally start rebuilding DailyETF?
```

至少回答：

```text
Are we building infrastructure without a strategy blocker?
Are we duplicating VectorBT?
Are we duplicating RQAlpha?
Are we creating abstractions without two real use cases?
Are we making the system harder to understand?
Are we increasing maintenance burden without increasing research power?
```

如果任意一个答案为：

```text
YES
```

优先回退或简化实现。

---

# 21. No Premature Abstraction Rule

不要因为未来可能需要：

```text
multiple brokers
multiple execution engines
multiple data stores
dozens of providers
dozens of strategy types
```

就提前抽象。

原则：

```text
Rule of 2:
no generic abstraction until at least two concrete real use cases exist.
```

即使有两个 use case，也优先考虑 duplication 是否比 abstraction 更简单。

---

# 22. Repository-First Rule

如果 repository 已经存在代码：

开始工作前必须：

```text
git status
git log --oneline -10
read README
read docs/ARCHITECTURE.md
read docs/CURRENT_STATE.md
read docs/RESEARCH_RULES.md
```

不得只根据本 Goal Prompt 推断仓库状态。

Repository 是 source of truth。

如果本提示词与最新 repository 状态发生冲突：

```text
follow repository evidence
```

并在最终报告中说明差异。

---

# 23. 本轮具体工作

完成：

```text
M0
+
M1
+
M2 minimal baseline
```

即：

### A. 创建最小项目骨架

包括：

```text
Python project setup
VectorBT dependency
RQAlpha dependency
minimal tests
documentation
```

---

### B. 建立最小 multi-asset universe

优先使用能够方便取得且适合 baseline 的 instruments。

如果某些真实全球资产数据源当前不可访问：

可以使用明确标注的研究 proxy，

但必须在文档中说明：

```text
research proxy != production instrument
```

不要因为一个 instrument 数据困难阻塞整个 bootstrap。

---

### C. 实现 Global Dual Momentum baseline

第一版保持简单。

例如：

```text
lookback:
12 months

absolute filter:
momentum > 0

relative rank:
top 1~3

rebalance:
monthly

fallback:
cash / bond proxy
```

具体参数应进入 config，而不是散落在代码。

---

### D. 实现 VectorBT baseline research

至少输出：

```text
CAGR
Max Drawdown
Sharpe
Calmar
Turnover
Trade Count
Average Holding Period
```

---

### E. 建立 RQAlpha validation path

尽最大可能让 baseline 可以在 RQAlpha 中表达。

如果数据 bundle 是现实 blocker：

允许暂时只完成：

```text
strategy adapter
config
documented execution path
tests
```

但不得伪造已经跑通。

---

### F. 创建第一版研究结果说明

不要追求策略立即达到：

```text
10% CAGR
```

本轮目标只是证明：

```text
research loop works
```

即：

```text
idea
→ VectorBT
→ metrics
→ RQAlpha validation path
→ research conclusion
```

---

# 24. 本轮明确禁止

不要实现：

```text
S2 Multi-Asset Trend Following
S3 China Sector Rotation
live broker
VeighNa
web UI
database
scheduler platform
notification platform
generic workflow DAG
generic artifact framework
generic provider system
ML
AI strategy generation
optimization service
cloud deployment
```

---

# 25. Stop Conditions

当以下条件满足后立即停止：

```text
repository bootstrapped

minimal multi-asset universe exists

Global Dual Momentum baseline exists

VectorBT research path works

RQAlpha validation path is implemented or its exact external blocker is bounded

tests pass

documentation matches reality

CURRENT_STATE updated
```

不要顺手扩展下一阶段。

---

# 26. 验收标准

最终必须能够清楚回答：

### Architecture

```text
TactiCore 是否仍然是 strategy-first？
```

### Research

```text
是否已经可以运行最简单 Global Dual Momentum？
```

### Engine

```text
VectorBT 和 RQAlpha 是否职责清晰？
```

### Complexity

```text
是否避免创建第三套 backtester？
```

### User Effort

```text
策略是否仍保持低频？
```

### Documentation

```text
用户能否只阅读 docs/CURRENT_STATE.md
就理解当前系统做到哪里、为什么、下一步是什么？
```

---

# 27. Final Verification

完成后运行仓库实际适用的：

```text
tests
lint
format
type checks
basic research smoke test
```

不要声称执行了没有真正执行的测试。

如果存在 skip / failure：

必须明确报告。

---

# 28. Git Requirement

所有工作完成并验证后：

```text
git status
git diff
```

确认没有：

```text
secret
token
large accidental dataset
cache
temporary files
```

然后：

```text
git add
git commit
git push
```

提交信息应简洁描述经济/研究价值，例如：

```text
bootstrap low-frequency multi-asset research loop
```

---

# 29. 最终报告格式

最终回答必须使用以下结构：

```text
1. Executive Summary

2. What Was Implemented

3. Why This Work Matters

4. Architecture After This Goal

5. Global Dual Momentum Baseline

6. VectorBT Role and Current Result

7. RQAlpha Role and Current Result

8. Research Findings So Far

9. What We Explicitly Did NOT Build

10. Complexity / Infrastructure Drift Audit

11. Tests and Verification

12. Documentation Updated

13. Known Limitations

14. Current Repository State

15. Recommended Next Goal
```

其中：

```text
Recommended Next Goal
```

只能给：

```text
ONE primary direction
```

不要生成十几个并列 TODO。

最后附：

```text
commit SHA
branch
push status
```

---

# 30. 长期不变的项目准则

以下内容应写入：

```text
docs/RESEARCH_RULES.md
```

并视为后续所有 Goal 的长期约束：

```text
1. Strategy first.
2. Low turnover by default.
3. VectorBT for exploration.
4. RQAlpha for authoritative validation.
5. Never build a third backtest engine.
6. Tradable instruments first.
7. Infrastructure only when blocked by a real strategy need.
8. Prefer robust parameter regions over best parameters.
9. Out-of-sample evidence matters more than in-sample CAGR.
10. Every Goal must update CURRENT_STATE.
11. Every Goal must explain what changed, why, effect, limitations and next decision.
12. Always check whether we are accidentally rebuilding DailyETF.
13. Stop when the Goal is complete.
14. Commit and push only after verification.
```

---

开始工作。

先读取 repository 当前真实状态。

如果是空仓：

从 M0 开始。

如果仓库已经存在内容：

以 repository 为准，在不破坏已有正确工作的前提下完成本 Goal。

# Goal: S3C China Sector Sleeve Trend Filter — Transparent Baseline V1

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Strategy Research Reviewer
+
Repository Architecture Maintainer
```

---

# 0. Why This Work Exists

TactiCore 当前已经得到三类重要证据：

```text
S2
Multi-Asset Trend Following
→ Research Candidate R1
→ FROZEN / PROSPECTIVE_SHADOW_ACTIVE
```

```text
S3A
Cross-sectional top-3 sector winner picking
→ REJECTED
```

```text
S3B
Aggregate sector breadth binary risk switch
→ REJECTED
```

S3A 表明：

```text
集中选择相对动量 winner
```

没有优于 broad sector exposure。

S3B 表明：

```text
行业趋势信息
```

确实包含一定风险价值：

```text
Max Drawdown improvement = 8.52pp
```

但：

```text
whole-portfolio RISK_ON / RISK_OFF
```

过于粗糙，造成：

```text
CAGR sacrifice = 2.64pp
Sharpe ↓
Calmar ↓
```

因此下一步不应该：

```text
调 S3A top_k
调 S3A lookback
调 S3B breadth threshold
调 S3B lookback
```

而应该提出一个新的、独立经济假设：

> 行业趋势的价值可能存在于“逐行业局部风险过滤”，而不是横截面选赢家，也不是整个行业组合统一开关。给每个行业一个固定风险预算 sleeve；行业自身趋势为正时持有该行业，趋势为负或不可用时，仅将该行业自己的 sleeve 转向防御资产，可能在保持广泛行业参与度的同时降低尾部风险，并减少 S3B 全局 risk-off 对长期复利的损害。

定义新策略：

```text
S3C China Sector Sleeve Trend Filter V1
```

---

# 1. Repository First

从最新 remote `main` 开始。

不要把本 Prompt 中的状态视为仓库真相。

首先读取：

```text
AGENTS.md
```

然后至少读取：

```text
README.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/LESSONS_FROM_DAILYETF.md
docs/goal.md

config/s3_sector_rotation.toml
config/s3_sector_breadth.toml
config/s3_sector_universe.csv

data/canonical/s3_sector_rotation_v1/provenance.json

tacticore/strategies/china_sector_rotation.py
tacticore/strategies/china_sector_breadth.py
tacticore/strategies/multi_asset_trend.py
tacticore/engines/vectorbt_adapter.py

research/experiments/run_s3_sector_baseline.py
research/experiments/run_s3b_sector_breadth_baseline.py

research/results/S3_SECTOR_BASELINE_V1.md
research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md
research/results/s3_sector_benchmark_comparison_v1.csv
research/results/s3b_sector_breadth_comparison_v1.csv

research/shadow/s2_r1/candidate_manifest.json
research/shadow/s2_r1/README.md
```

检查相关 tests。

记录：

```text
starting HEAD
recent commits
working tree
dependency versions

S2 R1 integrity
RL-018 state
RL-019 state
S3A decision
S3B decision

S3 universe hash
S3 price/calendar/provenance hashes
```

如果 repository evidence 与本 Goal 冲突：

```text
repository evidence wins
```

---

# 2. Protect S2 R1

在任何代码修改前运行：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须通过。

本 Goal 不得修改任何 S2 R1 frozen input：

```text
config/strategy.toml
config/universe.csv

data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json

tacticore/strategies/multi_asset_trend.py
tacticore/engines/rqalpha_adapter.py

research/shadow/s2_r1/candidate_manifest.json
```

禁止更新 manifest hash 来掩盖修改。

---

# 3. Closed Questions Stay Closed

确认：

```text
RL-018 S3A
= REJECTED

RL-019 S3B
= REJECTED
```

不得重新运行或修改以下问题：

```text
S3A top-k winner selection
S3A 120/top-3 baseline
S3B 50% majority breadth
S3B binary RISK_ON / RISK_OFF
```

禁止尝试：

```text
S3A top_k = 2/4
S3A lookback = 100/140
S3B threshold = 40/45/55/60%
S3B lookback = 100/140/160
```

S3C 必须作为新的：

```text
economic mechanism
strategy identity
config
research artifact
ledger entry
```

出现。

---

# 4. S3C Is a New Economic Hypothesis

明确记录 hypothesis provenance：

```text
S3C was proposed after observing:

S3A:
winner picking failed

S3B:
aggregate breadth reduced drawdown
but sacrificed too much return
```

因此 S3C：

```text
IS historical follow-up research
```

不是：

```text
untouched OOS
prospective
independent confirmation
```

即使 S3C 表现很好，也只能称为：

```text
historical hypothesis screen
```

---

# 5. Core Isolation

S3A：

```text
relative ranking
→ top 3 sectors
→ concentrated selection
```

S3B：

```text
aggregate breadth
→ whole portfolio risk-on/off
```

S3C：

```text
each sector
→ independent absolute trend
→ own fixed sleeve
→ sector OR fallback
```

因此：

```text
NO ranking
NO top_k
NO global breadth threshold
NO binary whole-portfolio regime
```

---

# 6. Reuse Frozen S3 Universe

继续使用：

```text
config/s3_sector_universe.csv
```

不得重新选择 ETF。

保持现有 11 个行业：

```text
消费
医药
证券
军工
银行
有色
房地产
传媒
钢铁
煤炭
电子
```

以及：

```text
511010.SS
```

作为 fallback。

不要根据：

```text
S3A performance
S3B performance
selection frequency
current market narrative
```

删除或增加行业。

---

# 7. Reuse Exactly the Same Historical Data

直接使用：

```text
data/canonical/s3_sector_rotation_v1/
```

不要重新下载。

不要建立新的 identical dataset。

要求验证并记录：

```text
prices SHA-256
calendar SHA-256
provenance SHA-256
universe SHA-256
```

这样 S3A / S3B / S3C 的主要区别只来自：

```text
economic semantics
```

而不是数据变化。

---

# 8. Independent S3C Config

新增：

```text
config/s3_sector_sleeve_trend.toml
```

不要修改：

```text
config/s3_sector_rotation.toml
config/s3_sector_breadth.toml
```

预声明唯一 V1：

```toml
[china_sector_sleeve_trend]
trend_window = 120
absolute_momentum_threshold = 0.0
rebalance_frequency = "monthly"
execution_policy = "SIGNAL_CHANGE_ONLY"
fallback_symbol = "511010.SS"
fees = 0.001
slippage = 0.0005
initial_cash = 1000000.0
```

不包含：

```text
top_k
breadth_threshold
ranking
```

---

# 9. Why Keep 120 Observations

继续使用：

```text
120 valid observations
```

不是因为它被证明最优。

原因是：

> S3A、S3B、S3C 首轮实验保持相同趋势 horizon，使 S3C 尽量只改变 portfolio construction mechanism。

本 Goal 禁止：

```text
lookback optimization
```

---

# 10. Exact Sector Trend Semantics

对于每个行业 ETF，在每个月最后一个 canonical observation：

要求：

```text
signal-date price exists
```

且至少存在足够有效 observation。

使用现有：

```text
valid_observation_momentum(...)
```

如果其语义已经正确。

定义：

```text
momentum =
current adjusted close
/
120 valid observations ago adjusted close
- 1
```

分类：

```text
momentum > 0
→ POSITIVE

momentum <= 0
→ NEGATIVE_SIGNAL

cannot calculate
→ UNAVAILABLE
```

必须保持：

```text
UNAVAILABLE != NEGATIVE_SIGNAL
```

---

# 11. Fixed Sleeve Architecture

Universe 有：

```text
N = 11 sectors
```

每个行业永久拥有：

```text
sector_sleeve = 1 / N
```

即当前约：

```text
1 / 11
```

这是固定风险预算。

不得因为某月只有 8 个 eligible sector 就把其余 8 个重新归一化到：

```text
1 / 8
```

每个行业的 sleeve 不因其他行业状态变化而改变。

---

# 12. Exact Portfolio Rule

对行业 `i`：

## POSITIVE

```text
weight(sector_i) = 1 / N
```

## NEGATIVE_SIGNAL

```text
weight(sector_i) = 0
```

该行业的：

```text
1 / N
```

转给：

```text
fallback
```

## UNAVAILABLE

同样：

```text
weight(sector_i) = 0
```

其 sleeve 暂时放入 fallback。

但 diagnostics 中必须保持：

```text
UNAVAILABLE
```

与：

```text
NEGATIVE_SIGNAL
```

分离。

最终：

```text
fallback weight =
(number_negative + number_unavailable) / N
```

---

# 13. Example

假设 11 个行业：

```text
7 positive
3 negative
1 unavailable
```

则：

```text
7 sectors:
each = 1/11

fallback:
4/11
```

总和：

```text
1.0
```

没有：

```text
top-k
ranking
renormalization
```

---

# 14. Why Fixed Sleeves Matter

固定 sleeve 避免：

```text
winner concentration
```

同时避免 S3B 的：

```text
all sectors on
OR
all sectors off
```

策略风险敞口可以逐步变化：

```text
0/11
1/11
2/11
...
11/11
```

而不是：

```text
0%
or
100%
```

这正是 S3C 要验证的经济机制。

---

# 15. New Strategy Implementation

新增：

```text
tacticore/strategies/china_sector_sleeve_trend.py
```

保持很小。

建议只包含：

```text
ChinaSectorSleeveTrendConfig

load_sector_sleeve_trend_config

sector_trend_states

build_month_end_targets

build_execution_weights
```

优先复用现有：

```text
valid_observation_momentum
```

以及可以无语义变化复用的 timing helper。

不要创建：

```text
AllocationFramework
TrendFramework
SleeveEngine
SectorEngine
StrategyBase
```

---

# 16. Do Not Refactor Historical S3 Implementations

正常情况下保持不变：

```text
tacticore/strategies/china_sector_rotation.py
tacticore/strategies/china_sector_breadth.py
```

它们属于已经完成的 historical evidence。

不要为了 DRY：

```text
move everything into common_strategy.py
```

如果只有一两个纯函数真正可安全复用：

```text
direct import
```

即可。

---

# 17. Timing

严格：

```text
month-end canonical close
        ↓
calculate each sector trend
        ↓
generate target
        ↓
next canonical observation
        ↓
execution
```

禁止：

```text
same-close execution
```

---

# 18. SIGNAL_CHANGE_ONLY

只有目标权重改变时提交新 target。

例如：

如果：

```text
7 positive sectors
```

且下个月仍然是完全相同的 7 个：

```text
NO new target
```

不要机械恢复实际持仓到理论 `1/11`。

这继续保持：

```text
low maintenance
```

---

# 19. Primary Comparator

必须创建：

```text
UNGATED_FIXED_SLEEVE_BASKET
```

其目的仅是隔离：

```text
per-sector trend filter
```

本身的经济价值。

Comparator 使用同样：

```text
same 11 sleeves
same data
same timing
same SIGNAL_CHANGE_ONLY
same fees/slippage
same initial cash
```

但忽略趋势正负。

规则：

对于每个 sector：

```text
if AVAILABLE:
    sector = 1/N
else:
    fallback receives that 1/N sleeve
```

因此 comparator 不把剩余 eligible sector 重新归一化。

---

# 20. Why Not Use Old Equal-Weight as Primary Comparator

S3A 的行业等权 comparator 和 S3B ungated basket 都可以作为：

```text
contextual historical benchmarks
```

但 S3C 的 primary comparator 必须具有相同：

```text
fixed-sleeve mechanics
```

否则无法准确隔离：

```text
trend filtering
```

的增量。

---

# 21. Other Contextual Benchmarks

最终报告同时引用：

```text
510300.SS buy-and-hold

S3A V1

S3B V1

S3A historical sector equal-weight
```

但它们不是 primary decision comparator。

---

# 22. Evaluation Range

继续采用已有 S3 coverage discipline。

评价期起点：

> 首个至少 8 个行业已经具备完整 120-observation trend history，并且下一 canonical observation 可执行的日期。

不要根据 S3C performance 调整起点。

如果 evaluation start 与 S3A/S3B 不一致：

必须解释原因。

---

# 23. Required State Artifact

生成：

```text
research/results/s3c_sector_sleeve_states_v1.csv
```

每个月至少记录：

```text
signal_date

eligible_sector_count
positive_sector_count
negative_sector_count
unavailable_sector_count

risk_asset_weight
fallback_weight

target_changed
execution_date
```

可以增加逐行业：

```text
POSITIVE
NEGATIVE_SIGNAL
UNAVAILABLE
```

但不要建设 feature store。

---

# 24. Performance Metrics

S3C 与 primary comparator 至少报告：

```text
CAGR
Max Drawdown
Sharpe
Calmar
worst year

turnover
trade count
average holding days

target-change months
annualized target-change months
```

另外报告：

```text
average risk-asset allocation
median risk-asset allocation
minimum risk-asset allocation
maximum risk-asset allocation

average fallback weight

months with:
0–25% risk
25–50% risk
50–75% risk
75–100% risk
```

---

# 25. Sector-Level Diagnostics

至少回答：

```text
每个行业多少个月 POSITIVE？
多少个月 NEGATIVE？
多少个月 UNAVAILABLE？

每个行业发生多少次趋势状态切换？

是否存在某几个行业几乎永远 positive？

防御 allocation 是否主要由某一行业贡献？
```

仅做 diagnostics。

不要因此加入新 signal。

---

# 26. No Parameter Search

本 Goal 只能运行：

```text
trend_window = 120
threshold = 0
fixed sleeve = 1/11
```

禁止：

```text
80 / 100 / 120 / 160 / 200
```

比较。

禁止：

```text
different fallback ratios
partial sleeve
volatility-scaled sleeve
```

禁止 optimizer。

---

# 27. Predeclare Decision Gate Before Running Results

在读取 S3C performance 之前把 decision function 写死。

本策略的目标：

> 相比同机制 ungated fixed-sleeve basket，通过逐行业局部趋势过滤显著改善风险调整收益，同时避免 S3B 那种过大的长期收益牺牲。

---

# 28. Coverage Gate

要求：

```text
>= 8 eligible sectors
```

至少出现在：

```text
80%
```

的 evaluated month-end observations。

否则：

```text
BLOCK_S3C_COVERAGE
```

---

# 29. Absolute Economic Floor

要求：

```text
after-cost CAGR > 0

Sharpe >= 0.45

Max Drawdown > -35%

annualized target-change months <= 10
```

所有门槛必须预先写入代码和报告。

---

# 30. Primary Relative Gate

与：

```text
UNGATED_FIXED_SLEEVE_BASKET
```

比较。

必须满足全部：

## Drawdown

```text
S3C max drawdown
至少改善 5 percentage points
```

## Return preservation

```text
S3C CAGR
>=
UNGATED CAGR - 1.5 percentage points
```

## Sharpe

```text
S3C Sharpe
>
UNGATED Sharpe
```

## Calmar

```text
S3C Calmar
>
UNGATED Calmar
```

即：

> 这一次不能只靠降低回撤通过；必须真正提高风险调整效率。

---

# 31. Low-Maintenance Gate

要求：

```text
annualized target-change months <= 10
```

并报告：

```text
trade_count
average_holding_days
```

不要构造复合 maintenance score。

---

# 32. No Degenerate Exposure

必须报告 risk exposure distribution。

如果：

```text
average risk allocation < 30%
```

则标记：

```text
REJECT_S3C_DEFENSIVE_DEGENERATION
```

因为该策略基本退化成 bond allocation。

如果：

```text
average risk allocation > 95%
```

且趋势过滤几乎从不工作：

```text
REJECT_S3C_FILTER_DEGENERATION
```

不要通过修改 threshold 救援。

---

# 33. Final Decisions

只能输出以下之一。

## ADVANCE_S3C_TO_ROBUSTNESS

条件：

```text
coverage PASS

absolute floor PASS

drawdown improvement PASS

CAGR preservation PASS

Sharpe improvement PASS

Calmar improvement PASS

maintenance PASS

non-degenerate PASS
```

含义仅为：

```text
S3C historical baseline
worth further robustness research
```

不是：

```text
production candidate
OOS validated
```

---

## REJECT_S3C_BASELINE

经济 floor 或 primary relative gate 未通过。

停止该 hypothesis。

---

## REJECT_S3C_DEFENSIVE_DEGENERATION

风险资产暴露过低。

---

## REJECT_S3C_FILTER_DEGENERATION

趋势过滤几乎不产生风险差异。

---

## BLOCK_S3C_COVERAGE

数据覆盖不满足要求。

---

## REVISE_S3C_SEMANTICS

仅当发现明确：

```text
lookahead bug
availability bug
incorrect sleeve accounting
target sum error
timing error
benchmark error
```

时允许。

收益不好不能触发 REVISE。

---

# 34. Expected Implementation Scope

预计新增：

```text
config/s3_sector_sleeve_trend.toml

tacticore/strategies/china_sector_sleeve_trend.py

research/experiments/run_s3c_sector_sleeve_baseline.py

research/results/S3C_SECTOR_SLEEVE_BASELINE_V1.md
research/results/s3c_sector_sleeve_comparison_v1.csv
research/results/s3c_sector_sleeve_states_v1.csv

tests/test_china_sector_sleeve_trend.py
tests/test_s3c_sector_sleeve_baseline.py
```

不要机械增加无实际价值 artifact。

---

# 35. Existing Files Normally Unchanged

正常情况下：

```text
AGENTS.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/LESSONS_FROM_DAILYETF.md

config/strategy.toml
config/universe.csv

config/s3_sector_rotation.toml
config/s3_sector_breadth.toml
config/s3_sector_universe.csv

data/canonical/*

tacticore/strategies/multi_asset_trend.py
tacticore/strategies/china_sector_rotation.py
tacticore/strategies/china_sector_breadth.py

tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/results/S3_SECTOR_BASELINE_V1.md
research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md

research/shadow/s2_r1/candidate_manifest.json
```

---

# 36. Reuse VectorBT

使用：

```text
tacticore.engines.vectorbt_adapter.run_target_weights
```

禁止新增：

```text
sleeve_backtester
sector_backtester
portfolio_engine
reference_engine
```

VectorBT 继续负责：

```text
portfolio simulation
accounting
orders
trades
records
```

---

# 37. No RQAlpha Yet

本 Goal：

```text
NO S3C RQAlpha validation
```

顺序：

```text
transparent economic screen
        ↓
robustness
        ↓
execution validation
```

如果 baseline 被拒绝，就不做 RQAlpha。

---

# 38. No Theme Rotation Yet

Theme Rotation 继续保持：

```text
NOT STARTED
```

本轮不要增加：

```text
半导体
AI
创新药
机器人
算力
新能源主题
```

等 theme universe。

先关闭 S3C hypothesis。

---

# 39. No Additional Signals

禁止加入：

```text
breadth filter
market index trend
volatility targeting
valuation
fund flow
macro
northbound flow
news
sentiment
RSI
MACD
AI scoring
```

S3C 只有：

```text
per-sector absolute trend
+
fixed sleeve
+
fallback
```

---

# 40. Tests

至少覆盖：

## Fixed sleeves

```text
N sectors
→ each sleeve = 1/N
```

无论其他行业状态如何，单个 sector sleeve 不变化。

## Positive

```text
POSITIVE
→ own sleeve allocated to sector
```

## Negative

```text
NEGATIVE_SIGNAL
→ own sleeve allocated to fallback
```

## Unavailable

```text
UNAVAILABLE
→ own sleeve allocated to fallback
```

但 state 仍保持 UNAVAILABLE。

## Portfolio invariant

```text
weights >= 0
sum(weights) == 1
sector weight <= 1/N
```

## No ranking

输入 momentum 排名改变、但正负集合不变时：

```text
target unchanged
```

这是一个非常重要的测试。

## Timing

```text
month-end signal
next observation execution
no same-close
```

## SIGNAL_CHANGE_ONLY

如果正负状态集合不变：

```text
no new target
```

## No lookahead

signal_date 之后的数据不能影响 target。

---

# 41. Regression Protection

完成后必须确认：

```text
S3A artifacts unchanged
S3B artifacts unchanged
S3 universe unchanged
S3 historical canonical unchanged
S2 frozen inputs unchanged
```

并再次运行：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

---

# 42. Main Research Report

生成：

```text
research/results/S3C_SECTOR_SLEEVE_BASELINE_V1.md
```

至少包含：

```text
1. Research Question
2. Hypothesis Provenance
3. Why S3C Is Not S3A/S3B Tuning
4. Frozen Universe
5. Frozen Data
6. Exact Trend Definition
7. Availability Semantics
8. Fixed Sleeve Definition
9. Portfolio Construction
10. Timing
11. SIGNAL_CHANGE_ONLY
12. Primary Comparator
13. Predeclared Decision Gate
14. Full-Sample Results
15. Drawdown Comparison
16. Return Preservation
17. Sharpe / Calmar Comparison
18. Risk Exposure Distribution
19. Sector-Level Diagnostics
20. Turnover / Maintenance
21. Biases / Limitations
22. Decision
23. What This Does NOT Prove
24. Next ONE Direction
```

---

# 43. Bias Disclosure

必须明确：

```text
S3C hypothesis was proposed
after observing S3A and S3B.
```

因此结果存在：

```text
researcher degrees of freedom
hypothesis-generation bias
same-sample reuse
current-universe bias
survivorship bias
fund-launch bias
```

如果 PASS：

不能称：

```text
OOS confirmed
```

只能称：

```text
historically promising follow-up hypothesis
```

---

# 44. Research Ledger

在：

```text
docs/RESEARCH_LEDGER.md
```

追加：

```text
RL-020 S3C Sector Sleeve Trend Filter Baseline
```

包括：

```text
strategy
question
status
hypothesis provenance
scope
frozen universe/data
exact semantics
decision
evidence
framework version
reopen condition
```

完成后：

如果 PASS：

```text
CLOSED
```

表示 baseline screen 问题已经关闭，下一问题是 robustness。

如果 FAIL：

```text
REJECTED
```

禁止参数救援。

---

# 45. STRATEGY_CATALOG

保持：

```text
S2 R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE

S3A
REJECTED

S3B
REJECTED
```

新增：

```text
S3C Sector Sleeve Trend Filter V1
```

记录：

```text
hypothesis
signal
portfolio
economic screen
decision
remaining unproven questions
```

Theme Rotation 仍：

```text
NOT STARTED
```

---

# 46. CURRENT_STATE

完成后只记录当前前沿。

如果 S3C PASS：

```text
S2 R1:
PROSPECTIVE_SHADOW_ACTIVE

S3A:
REJECTED

S3B:
REJECTED

S3C:
ADVANCE_S3C_TO_ROBUSTNESS

next unique active direction:
S3C robustness
```

如果 S3C FAIL：

```text
S2 R1:
PROSPECTIVE_SHADOW_ACTIVE

S3A:
REJECTED

S3B:
REJECTED

S3C:
REJECTED

next unique direction:
select a new independent hypothesis
```

不要在同一 Goal 自动实现下一个 hypothesis。

---

# 47. Document Ownership

正常：

```text
AGENTS.md
UNCHANGED
```

正常：

```text
docs/ARCHITECTURE.md
UNCHANGED
```

正常：

```text
docs/RESEARCH_RULES.md
UNCHANGED
```

因为：

```text
120-day trend
1/11 sleeve
S3C decision gate
```

都是 strategy-specific research semantics，不是永久架构或方法论。

必须更新：

```text
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/CURRENT_STATE.md
docs/goal.md
```

---

# 48. Replace docs/goal.md

当前 S3B Goal 已完成。

用本 Goal 替换：

```text
docs/goal.md
```

不要继续堆积历史 Goal。

完成时可以写：

```text
Status: completed
Decision: <actual decision>
```

永久事实必须已经进入：

```text
RESEARCH_LEDGER
STRATEGY_CATALOG
CURRENT_STATE
research/results
```

---

# 49. Validation

运行当前 repository 正式验证：

```bash
uv sync --extra dev

uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

运行 S3C：

```bash
uv run python \
  research/experiments/run_s3c_sector_sleeve_baseline.py
```

然后再次：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

不要声称未执行命令为 PASS。

---

# 50. No CI Work

如果最新 HEAD 仍无 active commit-status / workflow gate：

```text
do not add CI
```

本 Goal 不做：

```text
GitHub Actions
branch protection
release automation
```

研究工作优先。

---

# 51. Diff Audit

提交前执行：

```bash
git status
git diff
```

重点确认：

```text
S2 frozen files unchanged
S2 manifest unchanged

S3A files unchanged
S3B files unchanged

S3 universe unchanged
S3 canonical unchanged
```

不得出现：

```text
TUSHARE_TOKEN
credentials
temporary data
cache
environment artifacts
```

---

# 52. Architecture Drift Audit

逐项回答：

```text
Did we reopen RL-018?
Did we reopen RL-019?

Did we tune S3A?
Did we tune S3B?

Did we test multiple S3C lookbacks?
Did we use top-k?
Did we use ranking?
Did we use breadth threshold?

Did we change the S3 universe?
Did we redownload historical data?

Did we add another backtester?
Did we duplicate VectorBT?

Did we prematurely run RQAlpha?
Did we start Theme Rotation?

Did we modify S2 frozen inputs?
Did we update the S2 manifest?

Did we add DailyETF-style factor complexity?

Did we modify AGENTS.md unnecessarily?
Did we modify ARCHITECTURE.md unnecessarily?
Did we put S3-specific settings into RESEARCH_RULES?

Did we claim S3C is OOS?
Did we claim S3C is production-ready?
```

正常全部：

```text
NO
```

---

# 53. Commit and Push

所有验证完成后创建一个 coherent commit。

建议 intent：

```text
evaluate S3C sector sleeve trend baseline
```

随后：

```bash
git push
```

不要混入无关 refactor。

---

# 54. Final Completion Report

最终回复必须报告：

```text
starting HEAD
ending HEAD
commit SHA

S2 integrity before
S2 integrity after

S3A state
S3B state

S3C hypothesis
trend_window
sector count
fixed sleeve size

data hashes
universe hash
config hash

evaluation start
evaluation end

S3C:
CAGR
Max Drawdown
Sharpe
Calmar
worst year
turnover
trade count
average holding days
target-change months/year

average risk allocation
average fallback allocation

primary comparator:
CAGR
Max Drawdown
Sharpe
Calmar

drawdown improvement
CAGR sacrifice
Sharpe delta
Calmar delta

final decision
```

同时明确回答：

```text
Was S3A reopened?
NO

Was S3B reopened?
NO

Was parameter optimization performed?
NO

Was cross-sectional ranking used?
NO

Was a breadth threshold used?
NO

Was S3 universe changed?
NO

Was historical S3 data changed?
NO

Was S2 R1 modified?
NO

Does S2 candidate verification pass?
YES

Was RQAlpha used for S3C?
NO

Was Theme Rotation started?
NO

Is S3C OOS validated?
NO

Is S3C production-ready?
NO
```

---

# 55. If S3C Passes

如果：

```text
ADVANCE_S3C_TO_ROBUSTNESS
```

下一 Goal 才进入：

```text
S3C Robustness Gate
```

优先检验：

```text
coarse trend-window plateau
fixed-period stability
rolling stability
cost sensitivity
universe robustness
sector contribution concentration
```

仍然不要立即增加：

```text
macro
fund flow
valuation
news
AI
```

也不要立即 RQAlpha。

---

# 56. If S3C Fails

如果：

```text
REJECT_S3C_BASELINE
```

或 degeneration rejection：

停止。

不要尝试：

```text
100-day
140-day
200-day
partial sleeve
different threshold
```

来救结果。

至此 S3 已经依次测试：

```text
S3A:
pick winners

S3B:
global breadth switch

S3C:
local sleeve trend filtering
```

如果三者全部失败：

下一轮应暂停继续围绕同一 sector-momentum family 改造，重新比较真正不同的 economic hypothesis，包括是否值得进入 Theme Rotation，而不是继续微调价格趋势。

---

# 57. Final Principle

```text
S3A asked:
Which sectors are the winners?

Rejected.

S3B asked:
Is the whole sector complex healthy?

Rejected.

S3C asks:
Which individual sector sleeves deserve risk exposure?

One sector.
One fixed sleeve.
One trend decision.

No ranking.
No winner concentration.
No all-in/all-out regime.

Local risk control instead of global timing.

One hypothesis.
One baseline.
One decision.

Negative evidence stays closed.

VectorBT before RQAlpha.
Robustness before execution.
Execution before production.

S2 remains frozen while S3 research continues.

Strategy evidence > infrastructure.
```

---

## 完成状态

Status: completed

Decision: `REJECT_S3C_BASELINE`

权威结果：[S3C 行业固定 Sleeve 趋势过滤基线 V1](../research/results/S3C_SECTOR_SLEEVE_BASELINE_V1.md)。

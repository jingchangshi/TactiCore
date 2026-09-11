# Goal: S3B China Sector Breadth Regime Filter — Transparent Baseline V1

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

TactiCore 当前已经形成两条明确研究线：

```text
S2 Research Candidate R1
    ↓
FROZEN
    ↓
PROSPECTIVE_SHADOW_ACTIVE
    ↓
等待真实未来数据
```

以及：

```text
S3A China Sector Rotation V1
    ↓
transparent baseline
    ↓
REJECT_S3A_BASELINE
```

S3A 的失败不能通过参数微调重开。

已有证据表明：

```text
top-3 winner picking
<
broad sector equal-weight exposure
```

因此下一研究问题不是：

```text
哪个 lookback 更好？
top-2 还是 top-4？
```

而是一个新的经济假设：

> S3A 的主要问题可能不是行业资产本身缺乏长期配置价值，而是横截面集中选择 winner 带来的不稳定性。行业整体趋势广度可能比个别行业排名更适合作为风险状态信号：当大多数行业处于中期正趋势时持有广泛行业篮子，当行业趋势广泛恶化时转入防御资产，可能在保留 sector beta 的同时降低大回撤。

该策略定义为：

```text
S3B China Sector Breadth Regime Filter V1
```

这是新的 hypothesis。

它不是：

```text
S3A V2
S3A tuning
S3A rescue
```

---

# 1. Repository First

开始实现前必须重新读取最新 remote `main`。

不要信任：

```text
本 Prompt 中的预期 HEAD
上一轮 Codex 报告
旧对话
单独 CURRENT_STATE
记忆
```

第一步读取：

```text
AGENTS.md
```

然后按其 routing contract 阅读至少：

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
config/s3_sector_universe.csv

data/canonical/s3_sector_rotation_v1/provenance.json

tacticore/strategies/china_sector_rotation.py
tacticore/engines/vectorbt_adapter.py

research/experiments/run_s3_sector_baseline.py

research/results/S3_SECTOR_BASELINE_V1.md
research/results/s3_sector_benchmark_comparison_v1.csv
research/results/s3_sector_universe_v1.csv

research/shadow/s2_r1/candidate_manifest.json
research/shadow/s2_r1/README.md
```

并检查所有相关 tests。

记录：

```text
starting HEAD
recent commits
working tree
dependency versions

S2 R1 integrity state
S3A final decision
S3A data hashes
S3A universe hash
S3A config hash
```

如果仓库事实和本 Goal 冲突：

```text
repository evidence wins
```

---

# 2. Preserve S2 R1 First

运行：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须通过。

S3B 不得修改任何 S2 R1 frozen input。

尤其禁止修改：

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

不要通过更新 manifest hash 隐藏 regression。

---

# 3. RL-018 Must Stay Closed

读取：

```text
docs/RESEARCH_LEDGER.md
```

确认：

```text
RL-018 S3A Transparent Sector Rotation Baseline
=
REJECTED
```

禁止重新测试：

```text
S3A lookback 100 / 140 / 160
S3A top_k 2 / 4 / 5
different absolute momentum threshold
different S3A sleeve weights
```

也禁止：

```text
“只改一个小参数看看”
```

S3B 必须拥有不同的：

```text
economic mechanism
strategy identity
config
research decision
ledger entry
```

---

# 4. Evidence That Motivates S3B

S3A historical screen 已显示：

```text
S3A V1
CAGR          5.81%
Max Drawdown -52.43%
Sharpe        0.363
Calmar        0.111
```

而 availability-aware sector equal-weight comparator：

```text
CAGR          8.40%
Max Drawdown -34.59%
Sharpe        0.513
Calmar        0.243
```

因此：

```text
winner selection
```

没有增加历史经济价值。

S3B 要回答的问题是：

> 如果不再选择 top winners，而把 cross-sectional sector momentum 压缩为一个 aggregate breadth / regime 信号，能否改善 broad sector basket 的风险收益？

不要把 S3B 写成“修复 S3A”。

它是：

```text
new hypothesis generated from prior negative evidence
```

因此即使使用同一历史样本：

```text
S3B result != OOS evidence
```

必须明确称为：

```text
historical hypothesis screen
```

---

# 5. Reuse S3A Universe and Historical Snapshot

不要重新选择 ETF universe。

继续使用：

```text
config/s3_sector_universe.csv
```

原因：

该 universe 已经通过非收益 metadata 规则建立：

```text
11 个行业 ETF
+
511010.SS fallback
```

且 universe selection 没有使用历史收益。

不要重新根据：

```text
S3A selection frequency
S3A contribution
S3A return
2026 current market narrative
```

剔除或加入行业。

---

# 6. Reuse Existing S3 Historical Canonical

直接复用：

```text
data/canonical/s3_sector_rotation_v1/
```

不要重新下载。

不要建立：

```text
data/canonical/s3_sector_breadth_v1/
```

除非当前已有数据确实无法支持 S3B。

因为：

```text
same universe
same historical cutoff
same price semantics
same hypothesis generation dataset
```

使用完全相同 snapshot 能更好隔离：

```text
strategy hypothesis change
```

而不是数据变化。

记录并验证：

```text
price SHA-256
calendar SHA-256
provenance SHA-256
```

必须与 S3A artifact 对应。

---

# 7. New Independent Config

新增：

```text
config/s3_sector_breadth.toml
```

不要修改：

```text
config/s3_sector_rotation.toml
```

S3A historical config 保持不可改写。

预声明：

```toml
[china_sector_breadth]
momentum_lookback = 120
breadth_threshold = 0.50
min_eligible_sectors = 8
rebalance_frequency = "monthly"
execution_policy = "SIGNAL_CHANGE_ONLY"
fallback_symbol = "511010.SS"
fees = 0.001
slippage = 0.0005
initial_cash = 1000000.0
```

---

# 8. Why Keep 120 Observations

S3B 使用：

```text
120 valid observations
```

不是因为 120 已证明最优。

原因是：

> 保持 S3A 已预声明的中期趋势定义不变，从而把本实验的主要变量限制为“cross-sectional winner ranking → aggregate breadth regime”。

这样能够回答：

```text
是不是 winner picking 本身的问题？
```

而不是同时改变：

```text
signal horizon
+
portfolio selection
+
risk regime
```

本 Goal：

```text
NO lookback search
```

---

# 9. Why Breadth Threshold = 50%

只测试：

```text
breadth_threshold = 0.50
```

经济解释：

> 至少严格超过一半的可用行业保持正中期趋势，才认为行业风险环境处于 RISK_ON。

定义：

```text
breadth =
positive_momentum_sector_count
/
eligible_sector_count
```

风险状态：

```text
if eligible_sector_count < 8:
    UNAVAILABLE

elif breadth > 0.50:
    RISK_ON

else:
    RISK_OFF
```

使用严格：

```text
>
```

而不是：

```text
>=
```

因此要求真正多数行业为正。

不要测试：

```text
0.30
0.40
0.45
0.55
0.60
0.70
```

本轮只测试一个透明 majority rule。

---

# 10. S3B Is NOT Cross-Sectional Ranking

S3B 禁止：

```text
sort sectors by momentum
top_k selection
winner ranking
rank-weighting
```

行业动量只用于：

```text
positive / negative
```

分类并形成：

```text
aggregate breadth
```

最终策略不知道：

```text
谁排名第 1
谁排名第 2
```

这是 S3B 与 S3A 的核心经济差异。

---

# 11. Availability Semantics

继续使用已经验证的 valid-observation semantics。

每个行业 ETF：

```text
signal day 必须有真实价格
```

并拥有至少：

```text
120 个滞后有效 observation
```

才能参与 breadth denominator。

否则：

```text
UNAVAILABLE
```

不得：

```text
填零
forward fill
当作 negative momentum
```

---

# 12. Exact Momentum Definition

复用 S3A 的：

```text
valid_observation_momentum(...)
```

如果它完全满足 S3B semantics。

不要复制实现。

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

no valid value
→ UNAVAILABLE
```

---

# 13. Do Not Refactor S3A Just for Cleanliness

已有：

```text
tacticore/strategies/china_sector_rotation.py
```

属于已关闭的 S3A evidence。

如果其中：

```text
valid_observation_momentum
build_execution_weights
```

已经可以原样复用：

直接 import。

不要因为“代码更漂亮”而：

```text
rename S3A modules
move functions
rewrite historical S3A implementation
```

除非存在实际 correctness blocker。

---

# 14. New Strategy Implementation

新增：

```text
tacticore/strategies/china_sector_breadth.py
```

建议只包含：

```text
ChinaSectorBreadthConfig
load_sector_breadth_config

sector_breadth_state
build_month_end_targets
```

以及真正 S3B-specific 的逻辑。

不要新增：

```text
RegimeEngine
BreadthFramework
SignalFramework
AllocationEngine
```

---

# 15. Exact S3B Portfolio Semantics

## RISK_ON

当：

```text
eligible >= 8
AND
breadth > 0.50
```

目标：

```text
所有当前 eligible sector ETF
等权
```

如果有 N 个 eligible sectors：

```text
each weight = 1 / N
fallback = 0
```

注意：

不是只持有：

```text
positive sectors
```

而是持有：

```text
all eligible sectors
```

因为本 hypothesis 测试的是：

```text
aggregate risk regime timing
```

而不是第二种 sector selection。

---

# 16. RISK_OFF

当：

```text
eligible >= 8
AND
breadth <= 0.50
```

目标：

```text
511010.SS = 100%
```

所有 sector：

```text
0%
```

---

# 17. UNAVAILABLE Regime

如果：

```text
eligible sectors < 8
```

则：

```text
state = UNAVAILABLE
```

策略不得推断 sector regime。

目标：

```text
fallback = 100%
```

但：

```text
UNAVAILABLE
!=
RISK_OFF
```

必须在 diagnostics 中分开统计。

---

# 18. Monthly Signal Timing

继续：

```text
month-end canonical observation close
        ↓
calculate sector momentum
        ↓
calculate breadth
        ↓
determine regime
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

# 19. SIGNAL_CHANGE_ONLY

使用：

```text
SIGNAL_CHANGE_ONLY
```

target vector 没有变化时：

```text
no new execution target
```

例如：

```text
RISK_ON
11 eligible sectors
```

连续多月未改变：

不要为了恢复严格等权而月月机械 rebalance。

这是有意设计：

```text
low maintenance
```

---

# 20. Why This Is an Important Isolation

S3A 同时做了：

```text
momentum
+
absolute filter
+
relative ranking
+
top-3 concentration
```

S3B 则只做：

```text
sector-wide momentum breadth
+
binary risk regime
+
broad basket
```

因此它能直接回答：

> 历史行业数据中，真正有价值的是否不是“赢家是谁”，而是“多数行业是否处在正趋势”？

---

# 21. Same-Mechanics Ungated Comparator

必须建立一个 experiment-local comparator：

```text
UNGATED_SECTOR_BASKET
```

语义：

在所有有：

```text
eligible sectors >= 8
```

的月份：

```text
equal-weight all eligible sector ETFs
```

并使用与 S3B 相同：

```text
SIGNAL_CHANGE_ONLY
next-observation execution
fees
slippage
initial cash
```

如果 eligible set 未变化：

```text
do not mechanically rebalance
```

这是最重要 comparator。

因为它隔离：

```text
breadth risk gate
```

本身是否增加价值。

---

# 22. Existing S3A Equal-Weight Benchmark

已有 S3A 报告中的：

```text
availability-aware monthly sector equal-weight
```

可以在最终报告作为：

```text
historical context
```

引用。

但不要把它作为唯一 primary comparator，因为它的机械 monthly rebalance semantics 与 S3B 不完全一致。

Primary comparator 必须是：

```text
same-mechanics ungated sector basket
```

---

# 23. Broad Market Comparator

继续使用：

```text
510300.SS buy-and-hold
```

作为 contextual benchmark。

不要把：

```text
必须跑赢沪深300 CAGR
```

作为唯一通过条件。

S3B 的 hypothesis 主要针对：

```text
drawdown / risk-adjusted allocation
```

---

# 24. Evaluation Range

使用与 S3A 相同的 coverage rule。

evaluation start：

首个满足：

```text
>= 8 eligible sectors
```

且能够在下一 canonical observation 执行的时点。

不要重新挑一个对 S3B 更有利的起点。

期望与 S3A 的 evaluation start 一致。

如果不同：

必须解释为什么。

---

# 25. Required Diagnostics

每个月末至少记录：

```text
signal_date
eligible_sector_count
positive_sector_count
negative_sector_count
unavailable_sector_count
breadth
regime
target_changed
execution_date
```

不要输出复杂 feature store。

一个 CSV 即可。

建议：

```text
research/results/s3b_sector_breadth_states_v1.csv
```

---

# 26. Required Performance Metrics

S3B 至少报告：

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

并报告：

```text
RISK_ON months
RISK_OFF months
UNAVAILABLE months

risk_on_share
risk_off_share

regime transitions
average RISK_ON duration
average RISK_OFF duration
```

---

# 27. No Parameter Search

本 Goal 严禁：

```text
lookback search
breadth threshold search
minimum eligible search
rebalance-frequency search
fallback search
```

只运行：

```text
lookback = 120
threshold = 0.50
min eligible = 8
```

一次。

---

# 28. No Multi-Signal Variant

禁止加入：

```text
index trend confirmation
volatility filter
market MA
credit signal
fund flow
valuation
macro
breadth slope
breadth moving average
two-stage confirmation
hysteresis
```

如果 baseline 值得继续：

这些只能是未来新的研究问题。

---

# 29. Predeclare the Advance Gate Before Running Results

S3B 的设计目标不是最大化 CAGR。

设计目标是：

> 相比同机制 broad sector exposure，明显降低尾部风险，同时不严重牺牲长期复利，并保持低触达。

必须在查看 S3B performance 前实现以下 gate。

---

# 30. Coverage Gate

要求：

```text
>= 8 eligible sectors
```

至少覆盖：

```text
80% evaluated month-end observations
```

否则：

```text
BLOCK_S3B_COVERAGE
```

---

# 31. Absolute Economic Floor

要求：

```text
after-cost CAGR > 0

Sharpe >= 0.40

Max Drawdown > -40%

annualized target-change months <= 10
```

这些只是进入下一阶段的基础门槛。

---

# 32. Primary Relative Gate

相对于：

```text
UNGATED_SECTOR_BASKET
```

必须满足：

## Drawdown improvement

```text
S3B Max Drawdown
至少改善 5 个百分点
```

例如：

```text
ungated = -35%
S3B >= -30%
```

---

## Return preservation

要求：

```text
S3B CAGR
>=
ungated CAGR - 2 percentage points
```

不允许用严重牺牲长期复利来换取表面低回撤。

---

## Risk-adjusted improvement

以下至少一项严格优于 ungated comparator：

```text
Sharpe
Calmar
```

并且：

```text
Max Drawdown
```

必须严格优于 comparator。

---

# 33. Regime Must Be Non-Degenerate

如果：

```text
RISK_OFF share < 5%
```

则 breadth rule 基本等价于永远持有行业篮子。

这种情况下：

```text
REJECT_S3B_DEGENERATE_REGIME
```

不要把几次偶然状态变化包装成 regime strategy。

同样，如果：

```text
RISK_ON share < 20%
```

说明它几乎退化为 bond strategy。

也：

```text
REJECT_S3B_DEGENERATE_REGIME
```

---

# 34. Final Decision Outcomes

最终只能给出一个主决策。

## A. ADVANCE_S3B_BREADTH_TO_ROBUSTNESS

要求：

```text
coverage gate PASS
absolute economic floor PASS
drawdown improvement PASS
return preservation PASS
risk-adjusted improvement PASS
regime non-degenerate PASS
```

含义：

> sector breadth risk regime 在历史样本上具有足够经济价值，值得进入稳健性研究。

不代表：

```text
production candidate
OOS validated
```

---

## B. REJECT_S3B_BREADTH_BASELINE

如果：

```text
breadth timing
没有明显改善 broad sector exposure
```

或者经济 floor 不通过：

```text
REJECT
```

然后停止。

禁止接着：

```text
threshold 0.45
threshold 0.55
lookback 100
lookback 140
```

救结果。

---

## C. REJECT_S3B_DEGENERATE_REGIME

如果策略几乎：

```text
always risk-on
```

或：

```text
always risk-off
```

说明 majority breadth 没有足够 regime information。

不要调 threshold。

---

## D. BLOCK_S3B_COVERAGE

数据覆盖不足。

这属于：

```text
data blocker
```

不是 strategy rejection。

---

## E. REVISE_S3B_SEMANTICS

只有发现明确：

```text
lookahead
availability bug
incorrect denominator
target sum bug
same-close execution
benchmark bug
```

时使用。

不能因为收益不好使用。

---

# 35. Expected Implementation

建议新增：

```text
config/s3_sector_breadth.toml

tacticore/strategies/china_sector_breadth.py

research/experiments/run_s3b_sector_breadth_baseline.py

research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md
research/results/s3b_sector_breadth_states_v1.csv
research/results/s3b_sector_breadth_comparison_v1.csv

tests/test_china_sector_breadth.py
tests/test_s3b_sector_breadth_baseline.py
```

不要机械创建没有价值的 artifact。

---

# 36. Files That Should Normally Remain Unchanged

正常情况下：

```text
AGENTS.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/LESSONS_FROM_DAILYETF.md

config/strategy.toml
config/universe.csv

config/s3_sector_rotation.toml
config/s3_sector_universe.csv

data/canonical/s3_sector_rotation_v1/*

tacticore/strategies/china_sector_rotation.py
tacticore/strategies/multi_asset_trend.py

tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/results/S3_SECTOR_BASELINE_V1.md
```

不得重写 S3A evidence。

---

# 37. Reuse VectorBT

继续使用：

```text
tacticore.engines.vectorbt_adapter.run_target_weights
```

禁止新建：

```text
breadth_backtester
regime_backtester
portfolio_engine
reference_engine
```

VectorBT 继续拥有：

```text
execution simulation
portfolio accounting
orders
trades
records
```

---

# 38. No RQAlpha Yet

本 Goal：

```text
NO RQAlpha S3B validation
```

顺序必须是：

```text
economic hypothesis
       ↓
VectorBT economic screen
       ↓
robustness
       ↓
only then RQAlpha
```

如果 S3B baseline 被拒绝：

没有理由做 execution engineering。

---

# 39. No Theme Rotation Yet

本 Goal 不启动：

```text
S3 Theme Rotation
```

不要加入：

```text
半导体
AI
机器人
创新药
算力
新能源主题
```

等主题 ETF。

行业 breadth hypothesis 必须先独立关闭。

---

# 40. No DailyETF Complexity

禁止加入：

```text
资金流
北向
融资
估值
宏观
政策
新闻
情绪
技术指标打分
多因子评分
AI judgment
```

这不是 DailyETF V2。

S3B 只有：

```text
price
→ sector momentum sign
→ breadth
→ binary risk state
→ broad basket / fallback
```

---

# 41. Tests

至少测试：

## Breadth

```text
positive_count correct
eligible_count correct
UNAVAILABLE not denominator
negative != unavailable
breadth correct
```

---

## Majority rule

```text
breadth > 0.50
→ RISK_ON

breadth == 0.50
→ RISK_OFF
```

---

## Coverage

```text
eligible < 8
→ UNAVAILABLE
→ fallback 100%
```

---

## Risk-on target

```text
all eligible sectors included
equal weights
no ranking
no top-k
fallback = 0
sum = 1
```

---

## Risk-off target

```text
sectors = 0
fallback = 1
```

---

## Timing

```text
month-end signal
next observation execution
no same-close
```

---

## Signal change

unchanged target:

```text
no new target submission
```

---

## S3A immutability

测试或 diff audit 确保：

```text
S3A historical artifacts
remain unchanged
```

---

## S2 integrity

最终：

```text
S2 candidate verification still passes
```

---

# 42. Do Not Test Framework Internals

不要测试：

```text
VectorBT accounting internals
RQAlpha internals
Tushare internals
```

只测试 TactiCore 自有：

```text
breadth semantics
state transition
target formation
timing
experiment gate
```

---

# 43. Research Report

生成：

```text
research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md
```

至少包括：

```text
1. Research Question
2. Why S3B Is Not S3A Tuning
3. Prior Negative Evidence
4. Predeclared Economic Hypothesis
5. Frozen Universe / Data Snapshot
6. Exact Breadth Definition
7. Availability Semantics
8. Regime Definition
9. Portfolio Construction
10. Execution Timing
11. Primary Comparator
12. Contextual Benchmarks
13. Predeclared Advance Gate
14. Full-Sample Results
15. Drawdown Comparison
16. Risk-Adjusted Comparison
17. Regime Occupancy
18. Regime Transitions
19. Turnover / Maintenance
20. Known Biases
21. Decision
22. What This Does NOT Prove
23. Next ONE Research Direction
```

---

# 44. Explicit Data-Mining Disclosure

报告必须明确：

> S3B hypothesis was generated after observing S3A's failure and the stronger sector equal-weight comparator.

因此 S3B 即使表现很好：

```text
NOT untouched OOS
NOT prospective
```

只能称为：

```text
historical follow-up hypothesis screen
```

这是研究诚信的重要部分。

---

# 45. Research Ledger

向：

```text
docs/RESEARCH_LEDGER.md
```

只追加：

```text
RL-019 S3B Sector Breadth Regime Baseline
```

记录：

```text
strategy
question
status
scope
hypothesis provenance
frozen universe/data
breadth rule
decision
evidence
framework version
reopen condition
```

如果完成：

```text
ADVANCE
或
REJECT
```

该 baseline 问题都应：

```text
CLOSED
```

或若失败：

```text
REJECTED
```

不要保持模糊 ACTIVE。

---

# 46. STRATEGY_CATALOG

保留：

```text
S2 R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
```

保留：

```text
S3A
REJECTED
```

新增：

```text
S3B Sector Breadth Regime Filter V1
```

记录：

```text
hypothesis
signal
portfolio
historical screen
decision
remaining unproven questions
```

不要覆盖 S3A。

---

# 47. CURRENT_STATE

完成后只保留当前前沿。

若 S3B PASS：

```text
S2:
R1 prospective shadow active

S3A:
rejected

S3B:
ADVANCE_S3B_BREADTH_TO_ROBUSTNESS

next unique direction:
S3B robustness
```

若 S3B REJECT：

```text
S2:
R1 prospective shadow active

S3A:
rejected

S3B:
rejected

next unique direction:
choose a new independent hypothesis
```

不要马上自动选择下一个 hypothesis。

---

# 48. ARCHITECTURE

正常：

```text
UNCHANGED
```

没有新的 ownership boundary。

---

# 49. AGENTS.md

正常：

```text
UNCHANGED
```

不需要新增 S3B-specific routing。

---

# 50. RESEARCH_RULES.md

正常：

```text
UNCHANGED
```

S3B：

```text
120 days
50% breadth
8 sectors
```

都是 strategy-specific hypothesis。

不得写入永久规则。

---

# 51. docs/goal.md

用本 Goal 替换已完成的 S3A Goal。

不要无限累积历史 Goal。

完成时允许在文末写：

```text
Status: completed
Decision: <actual decision>
```

永久事实进入：

```text
RESEARCH_LEDGER
STRATEGY_CATALOG
CURRENT_STATE
research/results
```

---

# 52. S2 Regression Gate

完成所有 S3B 工作之后再次运行：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须：

```text
PASS
```

如果失败：

```text
STOP
```

不得更新 S2 manifest。

---

# 53. Validation

执行：

```text
uv sync --extra dev

uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

运行：

```text
uv run python research/experiments/run_s3b_sector_breadth_baseline.py
```

结果必须可复现。

不要从未运行的命令声称 PASS。

---

# 54. CI Scope

如果当前 GitHub commit status / Actions 仍为空：

本 Goal 不新增 CI。

不要从策略研究漂移到：

```text
GitHub Actions
branch protection
release automation
```

除非它实际阻塞本 Goal。

---

# 55. Diff Audit

提交前：

```text
git status
git diff
```

明确检查：

```text
S2 frozen inputs unchanged
S2 manifest unchanged

S3A config unchanged
S3A universe unchanged
S3A dataset unchanged
S3A report unchanged
```

确保没有：

```text
parameter sweep
temporary files
credentials
TUSHARE_TOKEN
cache
generated environment files
```

---

# 56. Architecture Drift Audit

逐项回答：

```text
Did we reopen RL-018?

Did we tune S3A parameters?

Did we modify S3A historical evidence?

Did we change the S3 universe based on returns?

Did we redownload data unnecessarily?

Did we test multiple breadth thresholds?

Did we test multiple lookbacks?

Did we use cross-sectional ranking?

Did we add another backtesting engine?

Did we duplicate VectorBT?

Did we run RQAlpha prematurely?

Did we modify S2 frozen inputs?

Did we update S2 manifest to hide a change?

Did we add theme ETFs?

Did we add DailyETF multi-factor complexity?

Did we modify ARCHITECTURE without a boundary change?

Did we modify RESEARCH_RULES merely to record strategy parameters?

Did we describe S3B as OOS?
```

正常答案全部应为：

```text
NO
```

---

# 57. Commit and Push

所有验证完成后：

```text
git status
git diff
```

创建一个 coherent commit。

建议 intent：

```text
evaluate S3B sector breadth regime baseline
```

随后：

```text
git push
```

不要混入无关重构。

---

# 58. Final Report

最终回复必须报告：

```text
starting HEAD
ending HEAD
commit SHA

S2 integrity before
S2 integrity after

S3A state

S3B hypothesis
lookback
breadth threshold
minimum eligible sectors

historical dataset hashes
universe hash

evaluation start/end

CAGR
Max Drawdown
Sharpe
Calmar
worst year

turnover
trade count
average holding days
target-change months

risk-on share
risk-off share
unavailable share
regime transitions

UNGATED_SECTOR_BASKET metrics
510300 metrics

drawdown improvement
CAGR sacrifice
Sharpe / Calmar change

final decision
```

并明确：

```text
Was S3A reopened?
NO

Was S3A parameter tuning performed?
NO

Were multiple S3B thresholds tested?
NO

Was the S3 universe changed?
NO

Was S2 R1 modified?
NO

Does S2 candidate verification still pass?
YES

Was RQAlpha S3B validation performed?
NO

Was Theme Rotation started?
NO

Is S3B OOS validated?
NO

Is S3B production-ready?
NO
```

---

# 59. Expected Next Step If PASS

如果：

```text
ADVANCE_S3B_BREADTH_TO_ROBUSTNESS
```

下一 Goal 才允许研究：

```text
S3B robustness
```

优先问题：

```text
breadth regime 是否跨时期稳定？

50% 是否处于宽泛 threshold plateau？

120 日是否处于宽泛 horizon plateau？

风险改善是否只来自少数 crisis period？

不同 universe availability 是否改变结论？

成本提高是否破坏价值？
```

不得立即加入：

```text
fund flow
valuation
macro
news
AI
```

---

# 60. Expected Next Step If REJECT

如果：

```text
REJECT_S3B_BREADTH_BASELINE
```

或者：

```text
REJECT_S3B_DEGENERATE_REGIME
```

停止该 hypothesis。

不要：

```text
45% threshold
55% threshold
100-day lookback
140-day lookback
```

救结果。

下一 Goal 应重新选择新的独立 economic hypothesis。

Theme Rotation 可以成为候选之一，但必须重新进行：

```text
hypothesis
→ universe
→ simple baseline
```

而不是自动进入。

---

# 61. Final Principle

```text
Negative evidence is useful evidence.

Do not optimize a rejected strategy.

S3A tested:
who are the winners?

It failed.

S3B tests:
is the sector complex broadly healthy?

That is a different economic question.

One hypothesis.
One transparent rule.
One historical screen.

Breadth before complexity.

Risk-adjusted value before infrastructure.

VectorBT before RQAlpha.

Robustness before production.

S2 remains frozen while S3 research continues.
```

---

## 完成状态

Status: completed

Decision: `REJECT_S3B_BREADTH_BASELINE`

权威结果：[S3B 行业趋势广度状态过滤基线 V1](../research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md)。

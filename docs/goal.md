# Goal: TactiCore Batch 01 — Diverse Transparent Strategy Screens

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Research Integrity Reviewer
+
Repository Architecture Maintainer
```

---

# 0. Mission

不要继续采用：

```text
实现一个策略
→ 等人工检查
→ 再设计一个策略
→ 再运行
```

本 Goal 改为：

```text
一次性冻结一批相互独立的 economic hypotheses
                ↓
一次性实现
                ↓
先提交 immutable protocol
                ↓
统一运行 historical screens
                ↓
统一生成结果矩阵
                ↓
一次提交完整证据
                ↓
由后续人工 / Principal Reviewer
决定下一批研究方向
```

本批次编号：

```text
BATCH_01_DIVERSE_TRANSPARENT_BASELINES
```

一次研究以下五个对象：

```text
S3C  Sector Sleeve Trend Filter
S4A  Multi-Asset Inverse-Vol Allocation
S8A  Equity/Bond Trend Allocation
S27A Trend + Inverse-Vol Allocation
S30  Static Strategic Allocation Benchmark
```

其中：

```text
S30 = reference benchmark
```

不是待优化策略。

其他四个：

```text
S3C
S4A
S8A
S27A
```

各自独立 PASS / REJECT。

---

# 1. Core Research Principle

整个 Batch 必须遵守：

```text
freeze all hypotheses
BEFORE
seeing any new performance result
```

严禁：

```text
跑 S3C
→ 看结果
→ 修改 S4A

跑 S4A
→ 看结果
→ 修改 S27A
```

因此本 Goal 强制采用：

```text
Commit A
=
Protocol Freeze

then

run all experiments

then

Commit B
=
Results
```

---

# 2. Repository First

从最新 remote `main` 开始。

不要相信本 Prompt 中写死的 SHA。

第一步：

```bash
git fetch origin
git status
git log --oneline -15
```

读取：

```text
AGENTS.md
```

并按其 routing contract 阅读至少：

```text
README.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/LESSONS_FROM_DAILYETF.md
docs/goal.md

config/strategy.toml
config/universe.csv
config/s3_sector_universe.csv
config/s3_sector_rotation.toml
config/s3_sector_breadth.toml

data/canonical/provenance.json
data/canonical/s3_sector_rotation_v1/provenance.json

tacticore/strategies/global_dual_momentum.py
tacticore/strategies/multi_asset_trend.py
tacticore/strategies/china_sector_rotation.py
tacticore/strategies/china_sector_breadth.py

tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/results/S2_PARAMETER_PLATEAU_V1.md
research/results/S3_SECTOR_BASELINE_V1.md
research/results/S3B_SECTOR_BREADTH_BASELINE_V1.md

research/shadow/s2_r1/candidate_manifest.json
```

记录：

```text
starting HEAD
recent commits
working tree

Python version
VectorBT version
Pandas version
NumPy version

canonical hashes
sector canonical hashes

S2 R1 state
S3A state
S3B state
```

Repository evidence 永远优先。

---

# 3. Preserve All Closed Evidence

必须确认：

```text
S2 R1
=
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
```

```text
RL-018 S3A
=
REJECTED
```

```text
RL-019 S3B
=
REJECTED
```

不得重新打开：

```text
S3A top-k winner picking
S3B 50% breadth binary switch
S2 parameter plateau
```

---

# 4. S2 Candidate Integrity Gate

任何修改前：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

不得修改：

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

这些文件允许：

```text
READ
```

但不得：

```text
WRITE
```

---

# 5. No New Historical Data Download

本 Batch 不重新下载历史行情。

使用两份已经存在的 canonical：

## Multi-asset strategies

```text
data/canonical/
```

供：

```text
S4A
S8A
S27A
S30
```

使用。

## Sector strategy

```text
data/canonical/s3_sector_rotation_v1/
```

供：

```text
S3C
```

使用。

这样保证本 Batch 的差异来自：

```text
strategy semantics
```

而不是：

```text
new data vintage
```

---

# 6. Batch Protocol Artifact

在运行任何 performance experiment 前新增：

```text
research/batches/batch_01/PROTOCOL.md
```

它必须冻结：

```text
batch id

starting HEAD

dataset hashes

五个 strategy IDs

五个 exact semantics

所有参数

所有 primary comparators

所有 PASS / REJECT gates

evaluation-start rules

known hypothesis provenance

prohibited searches
```

不要记录任何 performance result。

---

# 7. Strategy 1 — S3C Sector Sleeve Trend Filter

ID:

```text
S3C_V1
```

Research question：

> 行业趋势是否更适合作为逐行业局部风险过滤，而不是 S3A 的 winner picking 或 S3B 的全局 risk switch？

---

## S3C Universe

使用：

```text
config/s3_sector_universe.csv
```

禁止修改。

11 个 sector ETF。

N：

```text
11
```

每个 sector 固定拥有：

```text
1 / 11
```

风险 sleeve。

---

## S3C Signal

```text
trend_window = 120 valid observations
threshold = 0
```

对于 sector i：

```text
momentum_i > 0
→ POSITIVE

momentum_i <= 0
→ NEGATIVE_SIGNAL

insufficient data / missing signal-day price
→ UNAVAILABLE
```

---

## S3C Allocation

POSITIVE：

```text
sector i = 1/N
```

NEGATIVE：

```text
sector i = 0
fallback += 1/N
```

UNAVAILABLE：

```text
sector i = 0
fallback += 1/N
```

但：

```text
UNAVAILABLE != NEGATIVE
```

必须保留不同诊断状态。

---

## S3C Important Invariant

不能：

```text
renormalize remaining positive sectors
```

例如：

```text
7 positive
3 negative
1 unavailable
```

则：

```text
7 sectors × 1/11
fallback = 4/11
```

---

## S3C Timing

```text
month-end close
→ signal
→ next canonical observation
→ execution
```

使用：

```text
SIGNAL_CHANGE_ONLY
```

---

## S3C Primary Comparator

```text
UNGATED_FIXED_SLEEVE_SECTOR_BASKET
```

相同：

```text
11 sleeves
availability
timing
costs
```

区别仅为：

```text
不使用 trend filter
```

---

## S3C Gate

Coverage：

```text
>= 8 eligible sectors
in >= 80% evaluated month-ends
```

Absolute：

```text
CAGR > 0
Sharpe >= 0.45
MaxDD > -35%
target-change months/year <= 10
```

Relative to ungated：

```text
MaxDD improvement >= 5pp

CAGR >= comparator CAGR - 1.5pp

Sharpe > comparator Sharpe

Calmar > comparator Calmar
```

Degeneration：

```text
average risk allocation >= 30%
average risk allocation <= 95%
```

Possible result：

```text
ADVANCE_S3C_TO_ROBUSTNESS

REJECT_S3C_BASELINE

REJECT_S3C_DEFENSIVE_DEGENERATION

REJECT_S3C_FILTER_DEGENERATION

BLOCK_S3C_COVERAGE
```

---

# 8. Strategy 2 — S30 Static Strategic Allocation

ID:

```text
S30_REFERENCE_V1
```

This is a CONTROL.

不是 alpha hypothesis。

目的：

> TactiCore 的动态策略必须证明自己比非常简单的长期分散配置值得维护。

---

## S30 Assets

固定：

```text
510300.SS  China Equity   25%
513500.SS  US Equity      25%
518880.SS  Gold           25%
511010.SS  China Bond     25%
```

不得根据 historical return 改权重。

---

## S30 Execution

初始：

```text
first common valid evaluation date
→ establish 25/25/25/25
```

之后：

```text
annual rebalance only
```

year-end close 后：

```text
next canonical observation
```

执行。

---

## S30 Costs

```text
fees = 10 bps
slippage = 5 bps
initial_cash = 1,000,000
```

---

## S30 Metrics

至少：

```text
CAGR
MaxDD
Sharpe
Calmar
worst year

turnover
trades
average holding days
```

以及：

```text
annual returns
```

S30 不输出：

```text
PASS
FAIL
```

只输出：

```text
REFERENCE_BASELINE
```

---

# 9. Strategy 3 — S4A Multi-Asset Inverse Volatility

ID:

```text
S4A_INVERSE_VOL_V1
```

这是 Risk Allocation family 的透明 baseline。

注意：

```text
S4A != full covariance Equal Risk Contribution
```

本轮不实现复杂 ERC solver。

使用：

```text
inverse volatility
```

作为最透明的 risk-allocation baseline。

---

## S4A Universe

读取现有：

```text
config/strategy.toml
```

中的 multi-asset risk universe。

只读。

不要修改。

fallback：

```text
511010.SS
```

不参与 inverse-vol risk asset ranking。

---

## S4A Volatility

唯一预声明：

```text
vol_window = 60 valid daily returns
```

定义：

```text
vol_i = std(last 60 valid daily returns)
```

月末计算。

---

## S4A Eligibility

asset 必须：

```text
signal-day price exists
AND
60 valid return observations exist
```

否则：

```text
UNAVAILABLE
```

要求至少：

```text
min_eligible_assets = 6
```

否则：

```text
fallback = 100%
```

---

## S4A Weight

对于 eligible assets：

```text
raw_i = 1 / vol_i

weight_i =
raw_i / sum(raw)
```

fallback：

```text
0
```

若不足 6 个 eligible：

```text
fallback = 1
```

不要：

```text
weight cap
covariance
correlation
optimizer
risk-budget solver
```

---

## S4A Timing

```text
monthly
month-end signal
next observation execution
```

由于 volatility 本身每月变化：

```text
monthly target
```

是实际新信号。

不需要伪装成 SIGNAL_CHANGE_ONLY。

完全相同 target 才可省略。

---

## S4A Primary Comparator

```text
ELIGIBLE_EQUAL_WEIGHT_MULTI_ASSET
```

使用完全相同：

```text
eligible set
minimum coverage
timing
fees
slippage
```

区别只有：

```text
equal weight
vs
inverse volatility
```

---

## S4A Advance Gate

Coverage：

```text
>=6 eligible
in >=80% evaluated month-ends
```

Absolute：

```text
CAGR > 0
Sharpe >= 0.45
MaxDD > -35%
```

Relative：

```text
MaxDD improvement >= 3pp

CAGR >= equal-weight CAGR - 1.5pp

Sharpe >= equal-weight Sharpe + 0.03
```

Concentration diagnostic：

报告：

```text
max target weight
median max target weight
95th percentile max target weight
```

若：

```text
max asset weight > 50%
in > 5% evaluated months
```

输出额外警告：

```text
CONCENTRATION_RISK
```

但不要偷偷加入 cap。

Possible result：

```text
ADVANCE_S4A_TO_ROBUSTNESS

REJECT_S4A_BASELINE

BLOCK_S4A_COVERAGE
```

---

# 10. Strategy 4 — S8A Equity/Bond Trend Allocation

ID:

```text
S8A_EQUITY_BOND_TREND_V1
```

Research question：

> 一个极简单的股债趋势切换，是否已经能够显著降低股票回撤，同时保留大部分长期复利？

---

## Assets

仅：

```text
510300.SS
511010.SS
```

不要加入其他 ETF。

---

## Signal

对：

```text
510300.SS
```

使用：

```text
trend_window = 200 valid observations
```

月末：

```text
equity momentum > 0
→ EQUITY

equity momentum <= 0
→ BOND

unavailable
→ BOND
```

---

## Allocation

EQUITY：

```text
510300 = 100%
```

BOND：

```text
511010 = 100%
```

---

## Timing

```text
month-end close
→ signal
→ next canonical observation
→ trade
```

仅 regime 改变时产生 target。

---

## S8A Primary Comparators

Comparator 1：

```text
510300 BUY_AND_HOLD
```

Comparator 2：

```text
50/50 EQUITY_BOND
```

50/50 comparator：

```text
annual rebalance
```

不要 monthly rebalance。

---

## S8A Gate

Absolute：

```text
CAGR > 0
Sharpe >= 0.45
MaxDD > -35%
target changes/year <= 6
```

Against 510300：

```text
MaxDD improvement >= 10pp

CAGR >= 510300 CAGR - 2pp

Sharpe > 510300 Sharpe

Calmar > 510300 Calmar
```

Against static 50/50：

在以下四项：

```text
CAGR
MaxDD
Sharpe
Calmar
```

至少：

```text
2 / 4
```

严格更优，

且：

```text
MaxDD cannot be worse than 50/50
```

Possible result：

```text
ADVANCE_S8A_TO_ROBUSTNESS

REJECT_S8A_BASELINE
```

---

# 11. Strategy 5 — S27A Trend + Inverse Volatility

ID:

```text
S27A_TREND_INVERSE_VOL_V1
```

Research question：

> S2 已证明 fixed-sleeve time-series trend 值得继续观察，那么在保持 S2 总风险暴露逻辑不变的情况下，用 inverse volatility 在 active risk assets 内重新分配风险，是否可以进一步提高风险调整效率？

这是：

```text
historical follow-up hypothesis
```

不是新的 OOS evidence。

---

# 12. S27A Trend Signal

使用和 S2 相同的：

```text
200 valid observations
```

趋势定义。

但不要修改 S2 source。

如现有 S2 helper 可以只读复用：

```text
import
```

即可。

不要复制后再改变语义。

---

# 13. S27A Risk Budget

假设：

```text
N = total risk assets
P = number of positive-trend eligible assets
```

总 risk budget：

```text
P / N
```

fallback budget：

```text
1 - P/N
```

这保持 S2 的核心风险暴露结构。

---

# 14. S27A Active Asset Weighting

对 positive-trend assets：

计算：

```text
60 valid daily return volatility
```

然后：

```text
raw_i = 1 / vol_i

active_weight_i =
(P/N) × raw_i / sum(raw)
```

fallback：

```text
1 - P/N
```

因此：

```text
sum(weights) = 1
```

---

# 15. Important S27A Isolation

S2：

```text
positive sector/asset
→ fixed equal sleeve
```

S27A：

```text
same trend state
same total risk budget
→ inverse-vol distribution within active risk budget
```

所以主要实验变量只有：

```text
active risk allocation method
```

而不是同时更换：

```text
trend window
risk exposure
universe
fallback
```

---

# 16. S27A Timing

```text
month-end signal
next observation execution
```

由于 volatility sizing 每月改变：

允许：

```text
monthly target
```

---

# 17. S27A Primary Comparator

Primary：

```text
S2 V2B
```

但禁止重新进行：

```text
parameter plateau
robustness research
execution research
```

Comparator 优先读取已有 frozen research artifacts。

如果现有 artifact 缺少某个必要指标：

允许做：

```text
read-only reproduction
```

但必须明确标记：

```text
COMPARATOR_REPRODUCTION_ONLY
```

不得产生任何新的 S2 decision。

---

# 18. S27A Gate

Absolute：

```text
CAGR >= 5%
Sharpe >= 0.60
MaxDD > -30%
```

Relative to S2：

```text
CAGR >= S2 CAGR - 1pp

MaxDD >= S2 MaxDD - 2pp

Sharpe > S2 Sharpe

Calmar >= S2 Calmar

turnover <= 1.5 × S2 turnover
```

Possible result：

```text
ADVANCE_S27A_TO_ROBUSTNESS

REJECT_S27A_BASELINE
```

---

# 19. Strategies Explicitly NOT in Batch 01

不要实现：

```text
S5 Trend + full Risk Parity
S9 Tri-Asset dynamic allocation
S23 Minimum Variance
S24 Maximum Diversification
S14 Theme Rotation
```

原因：

```text
S5 partially overlaps S27A

S9 currently overlaps information
already tested by S30/S4A/S8A

S23/S24 require covariance estimation
and optimizer choices

Theme rotation requires a new universe
and introduces selection bias
```

这些留给：

```text
Batch 02 candidate selection
```

在 Batch 01 审计后决定。

---

# 20. Implement All Five BEFORE Performance Runs

在 Protocol Freeze 阶段实现：

```text
configs
strategy semantics
experiment runners
unit tests
decision functions
comparators
```

但是：

```text
DO NOT run historical performance yet
```

可以运行：

```text
unit tests
lint
type check
synthetic-data tests
```

确保逻辑正确。

---

# 21. Expected New Config Files

建议：

```text
config/s3_sector_sleeve_trend.toml
config/s4_inverse_vol.toml
config/s8_equity_bond_trend.toml
config/s27_trend_inverse_vol.toml
config/s30_static_allocation.toml
```

不要把它们塞进：

```text
config/strategy.toml
```

因为该文件属于 S2 R1 frozen identity。

---

# 22. Expected Strategy Modules

合理新增：

```text
tacticore/strategies/china_sector_sleeve_trend.py
tacticore/strategies/inverse_vol_allocation.py
tacticore/strategies/equity_bond_trend.py
tacticore/strategies/trend_inverse_vol.py
tacticore/strategies/static_strategic_allocation.py
```

如果 static benchmark 很简单，也可以仅存在 experiment 层，不必强行做 production-style strategy class。

---

# 23. Do Not Build a Strategy Framework

禁止因为一次实现五个策略就创建：

```text
BaseStrategy
StrategyRegistry
StrategyFactory
GenericSignalEngine
GenericAllocationEngine
ExperimentDatabase
BacktestManager
ResearchOrchestrator
```

除非当前 repository 已有明确能力需要复用。

允许抽取：

```text
非常小的 pure helper
```

仅当至少三个策略真正需要完全相同语义。

但：

```text
prefer duplication of 5 clear lines
over premature framework abstraction
```

---

# 24. Use Existing VectorBT Adapter

统一复用：

```text
tacticore.engines.vectorbt_adapter.run_target_weights
```

不要新建任何：

```text
custom backtester
reference portfolio engine
accounting engine
```

---

# 25. Common Metrics

四个 candidate strategies + S30 + comparators 必须尽量统一输出：

```text
CAGR
MaxDD
Sharpe
Calmar
worst year

turnover
trade_count
average_holding_days

target_change_count
annualized_target_change_count
```

根据策略再补：

```text
risk exposure
fallback allocation
concentration
regime count
sector states
```

---

# 26. Common Historical Interpretation

所有 Batch 01 结果必须称为：

```text
historical economic screen
```

不得称：

```text
prospective
untouched OOS
future validation
production validation
```

尤其：

```text
S3C
S27A
```

都是在已有 S3/S2 evidence 后设计的 follow-up hypotheses。

---

# 27. Protocol Freeze Commit

确认五个策略：

```text
semantics
parameters
comparators
decision gates
```

全部完成。

执行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

以及：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

全部通过后：

```bash
git status
git diff
```

确认尚未生成任何真实 performance outputs。

创建：

```text
Commit A
```

建议：

```text
freeze batch 1 transparent strategy screen protocol
```

然后：

```bash
git push
```

记录：

```text
PROTOCOL_FREEZE_SHA
```

---

# 28. Critical Rule After Protocol Freeze

一旦：

```text
PROTOCOL_FREEZE_SHA
```

存在：

禁止修改：

```text
all five configs

all five strategy semantics

all decision gates

primary comparator definitions
```

然后才运行 performance。

---

# 29. If a Correctness Bug Is Found After Freeze

如果运行时发现：

```text
implementation bug
lookahead bug
target-sum bug
incorrect eligibility
incorrect comparator
```

不得看到收益后直接修复并继续。

必须：

1. 标记当前受影响结果：

```text
INVALID_RUN
```

2. 删除/隔离无效 result artifact；
3. 修复 correctness；
4. 更新 protocol revision；
5. 创建新的：

```text
PROTOCOL_FREEZE_SHA_V2
```

6. 才允许重新运行。

最终报告必须披露：

```text
protocol revision occurred
why
whether performance had already been observed
```

不得静默修改。

---

# 30. Batch Execution

Protocol freeze 后才统一运行五项。

建议：

```bash
uv run python research/experiments/run_s3c_sector_sleeve_baseline.py

uv run python research/experiments/run_s4_inverse_vol_baseline.py

uv run python research/experiments/run_s8_equity_bond_trend_baseline.py

uv run python research/experiments/run_s27_trend_inverse_vol_baseline.py

uv run python research/experiments/run_s30_static_allocation.py
```

不要根据某一个结果：

```text
stop batch early
```

除非出现：

```text
correctness blocker
data corruption
S2 candidate integrity failure
```

即使前三个 REJECT：

也完成整批五项。

---

# 31. Individual Result Artifacts

生成：

```text
research/results/S3C_SECTOR_SLEEVE_BASELINE_V1.md

research/results/S4A_INVERSE_VOL_BASELINE_V1.md

research/results/S8A_EQUITY_BOND_TREND_BASELINE_V1.md

research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md

research/results/S30_STATIC_STRATEGIC_ALLOCATION_V1.md
```

可以生成必要 CSV。

不要生成大量日志型 artifact。

---

# 32. Batch Summary

额外生成：

```text
research/results/BATCH_01_TRANSPARENT_STRATEGY_SCREEN.md
```

必须有统一 comparison matrix。

例如：

| Strategy | Mechanism           | CAGR | MaxDD | Sharpe | Calmar | Turnover | Decision  |
| -------- | ------------------- | ---: | ----: | -----: | -----: | -------: | --------- |
| S3C      | local sector trend  |      |       |        |        |          |           |
| S4A      | inverse volatility  |      |       |        |        |          |           |
| S8A      | equity/bond timing  |      |       |        |        |          |           |
| S27A     | trend + inverse vol |      |       |        |        |          |           |
| S30      | static allocation   |      |       |        |        |          | REFERENCE |

但不要基于：

```text
highest CAGR wins
```

宣布 winner。

---

# 33. Batch-Level Classification

Batch summary 只分类：

```text
ADVANCE
REJECT
REFERENCE
BLOCKED
```

不要创建综合：

```text
strategy score
```

不要人为：

```text
CAGR 30%
Sharpe 30%
MaxDD 20%
...
```

组合成一个分数。

这会重新引入任意权重。

---

# 34. Cross-Strategy Interpretation

报告必须回答：

### Return prediction

```text
S3C
S8A
S27A
```

趋势类策略是否真正增加 value？

### Risk allocation

```text
S4A
```

仅通过 risk sizing 是否已经足够？

### Complexity hurdle

```text
S30
```

简单静态配置有多强？

### Incremental complexity

复杂策略相比 S30：

```text
what exactly is gained?
```

---

# 35. Important Comparison With S2

S2 R1 是当前唯一 prospective candidate。

Batch 01 中任何策略即使 historical screen 很强：

也不得直接替代：

```text
S2 R1
```

更不能修改它。

需要后续：

```text
robustness
execution
prospective candidate freeze
```

完整链路。

---

# 36. Research Ledger Updates

Batch 完成后追加：

```text
RL-020 S3C
RL-021 S4A
RL-022 S8A
RL-023 S27A
RL-024 S30 Reference Baseline
```

每项记录：

```text
question
hypothesis provenance
scope
data
exact semantics
decision
evidence
framework
reopen condition
```

对于 candidate：

```text
PASS baseline
→ CLOSED
```

因为：

```text
baseline question closed
next question = robustness
```

如果 FAIL：

```text
REJECTED
```

S30：

```text
CLOSED / REFERENCE
```

按现有 ledger status vocabulary 适配。

不要新增 ledger software。

---

# 37. STRATEGY_CATALOG Update

必须保持：

```text
S2 R1
FROZEN / PROSPECTIVE_SHADOW_ACTIVE

S3A
REJECTED

S3B
REJECTED
```

增加 Batch 01 各策略的简短生命周期状态：

```text
S3C
S4A
S8A
S27A
S30
```

不要把全部数字复制进去。

详细数字指向：

```text
research/results/*
```

---

# 38. CURRENT_STATE Update

完成后不要写五页历史。

只写：

```text
S2:
current prospective candidate

Batch 01:
which strategies advanced
which were rejected

current research frontier:
await Principal Review before Batch 02
```

非常重要：

Batch 结束后：

```text
DO NOT automatically choose Batch 02
```

状态写：

```text
AWAIT_BATCH_01_ARCHITECT_REVIEW
```

或仓库现有风格中的等价自然语言。

---

# 39. docs/goal.md

用本 Batch Goal 替换此前完成的单策略 Goal。

完成后：

```text
Status: completed

Batch:
BATCH_01_DIVERSE_TRANSPARENT_BASELINES

Protocol Freeze SHA:
<sha>

Results SHA:
<sha>
```

以及各策略 decision。

---

# 40. ARCHITECTURE / RULES / AGENTS

正常：

```text
AGENTS.md
UNCHANGED

docs/ARCHITECTURE.md
UNCHANGED

docs/RESEARCH_RULES.md
UNCHANGED

docs/LESSONS_FROM_DAILYETF.md
UNCHANGED
```

除非发现真正新的：

```text
permanent architectural boundary
```

本 Batch 不应产生这种变化。

---

# 41. Test Requirements — S3C

至少测试：

```text
fixed 1/N sleeves

positive → sector
negative → fallback
unavailable → fallback

unavailable != negative

ranking changes do not matter

sum(weights) == 1

no same-close execution
```

---

# 42. Test Requirements — S4A

至少测试：

```text
60 valid return volatility

missing asset excluded

inverse-vol weights correct

weights sum to 1

<6 eligible → fallback 100%

no future data usage

next-observation execution
```

使用 synthetic prices 验证：

```text
lower volatility
→ higher weight
```

---

# 43. Test Requirements — S8A

至少测试：

```text
200 valid observation equity trend

positive → equity 100%

non-positive → bond 100%

unavailable → bond

month-end signal

next observation execution

unchanged regime
→ no unnecessary trade
```

---

# 44. Test Requirements — S27A

至少测试：

```text
same 200-observation trend classification as intended

P positive / N
→ total risk allocation = P/N

fallback = 1 - P/N

active assets weighted inverse-vol

sum weights = 1

no ranking

negative assets receive zero

no lookahead
```

Synthetic example：

```text
N = 4
P = 2

risk budget = 0.5
fallback = 0.5

if vol A < vol B:
weight A > weight B

A + B = 0.5
```

---

# 45. Test Requirements — S30

至少测试：

```text
four exact symbols

25% each

weights sum = 1

annual rebalance only

no hidden return-dependent weights
```

---

# 46. Decision-Function Tests

每个 strategy decision function 必须用 synthetic metric rows 测试：

```text
clear PASS case

clear FAIL case

boundary case
```

例如：

```text
Sharpe == threshold
```

必须行为确定。

不要让判断留在人脑中。

---

# 47. Reproducibility

每个 experiment result 必须记录：

```text
protocol freeze SHA
data hashes
config hash
strategy source hash
universe hash
framework versions
evaluation period
```

这样下一次 audit 可以验证：

```text
result
came from
the frozen protocol
```

---

# 48. No Parameter Optimization

整个 Batch 禁止：

```text
grid search
random search
Bayesian optimization
parameter sweep
best-performing configuration
```

严格只有：

```text
one parameterization per hypothesis
```

---

# 49. No Robustness Yet

即使某策略 PASS：

不要在本 Batch 做：

```text
parameter plateau
rolling robustness
walk-forward
cost sensitivity matrix
universe sensitivity
RQAlpha
```

原因：

本 Batch 只负责：

```text
economic hypothesis screening
```

下一轮由 Principal Reviewer 根据整批结果决定：

```text
which candidates deserve robustness
```

---

# 50. No RQAlpha

整个 Batch：

```text
NO new RQAlpha strategy validation
```

RQAlpha 只有在：

```text
economic screen PASS
+
future robustness PASS
```

后才值得投入。

---

# 51. No Theme Rotation

继续：

```text
Theme Rotation
=
NOT STARTED
```

不要加入主题 ETF。

---

# 52. No New Infrastructure

禁止：

```text
strategy framework
experiment platform
data platform
provider abstraction
workflow DAG
scheduler
dashboard
database
registry service
broker integration
notification
production runner
```

Batch 只是研究批次。

---

# 53. Batch 01 Expected Diff Shape

合理新增大致：

```text
research/batches/batch_01/PROTOCOL.md

config/<4-5 small independent configs>

tacticore/strategies/<small strategy modules>

research/experiments/<batch strategy runners>

research/results/<individual reports>
research/results/BATCH_01_TRANSPARENT_STRATEGY_SCREEN.md

tests/<focused tests>

docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/CURRENT_STATE.md
docs/goal.md
```

如果出现：

```text
hundreds of generic framework classes
```

说明 architecture drift。

---

# 54. Protocol-to-Result Integrity Check

最终运行：

```bash
git diff <PROTOCOL_FREEZE_SHA>..HEAD
```

结果阶段正常只应修改：

```text
research/results/*
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/CURRENT_STATE.md
docs/goal.md
```

以及确有必要的 generated artifacts。

原则上不应该在结果阶段再次修改：

```text
configs
strategy source
decision gates
protocol semantics
```

---

# 55. Full Validation

Protocol Freeze 前：

```bash
uv sync --extra dev

uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

Results 后再次完整执行。

---

# 56. Final S2 Integrity Verification

所有 Batch 结果完成后再次：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

否则：

```text
BATCH INVALID
```

不要更新 S2 manifest。

---

# 57. Final Architecture-Drift Audit

逐项回答 YES / NO：

```text
Did we modify S2 frozen inputs?

Did we reopen S3A?

Did we reopen S3B?

Did we tune any rejected strategy?

Did we run parameter sweeps?

Did one strategy's outcome influence another strategy's frozen design?

Did we modify protocol after performance observation?

Did we redownload historical data?

Did we build a generic strategy framework?

Did we add a new backtester?

Did we duplicate VectorBT?

Did we run new RQAlpha validations?

Did we start Theme Rotation?

Did we build production infrastructure?

Did we modify ARCHITECTURE unnecessarily?

Did we modify RESEARCH_RULES for strategy-specific parameters?

Did we call historical results OOS/prospective?
```

正常全部：

```text
NO
```

---

# 58. Commit B

完成所有结果、文档和验证后：

```bash
git status
git diff
```

创建：

```text
Commit B
```

建议：

```text
evaluate batch 1 transparent strategy screens
```

然后：

```bash
git push
```

---

# 59. Final Batch Report to User

最终回复必须首先给：

```text
Starting HEAD
Protocol Freeze SHA
Results SHA
Ending HEAD
```

然后给统一表：

| Strategy | Hypothesis                  | CAGR | MaxDD | Sharpe | Calmar | Turnover | Decision  |
| -------- | --------------------------- | ---: | ----: | -----: | -----: | -------: | --------- |
| S3C      | sector local trend          |      |       |        |        |          |           |
| S4A      | inverse-vol risk allocation |      |       |        |        |          |           |
| S8A      | equity/bond trend           |      |       |        |        |          |           |
| S27A     | trend + inverse vol         |      |       |        |        |          |           |
| S30      | static diversification      |      |       |        |        |          | REFERENCE |

---

# 60. Final Interpretation Questions

必须回答：

```text
1. Which strategies passed their own
   predeclared economic gates?

2. Which were rejected?

3. Which mechanism appears strongest:
   - return prediction
   - risk allocation
   - diversification
   - timing?

4. How strong is S30 simple static allocation?

5. Did any dynamic strategy clearly justify
   its extra complexity over S30?

6. Did any strategy outperform S2 historically
   on risk-adjusted metrics?

7. Which results are genuinely orthogonal
   to S2?

8. Were any outcomes borderline?

9. Are any PASSes likely driven by
   only lower risk exposure?

10. What remains unproven?
```

---

# 61. Do NOT Start Batch 02

这是非常重要的停止条件。

即使某策略看起来非常优秀：

```text
DO NOT
```

在同一 Goal 内开始：

```text
robustness
parameter plateau
RQAlpha
new strategy
Batch 02
```

完成状态必须停在：

```text
BATCH_01_COMPLETE
AWAIT_PRINCIPAL_REVIEW
```

然后由下一轮 repository-first 审计决定：

```text
哪些策略进入 robustness

哪些直接永久拒绝

是否需要 Batch 02

Batch 02 应测试哪些真正独立的 hypotheses
```

---

# 62. Candidate Pool for Future Batch 02

只记录为：

```text
not implemented
```

候选包括：

```text
S5  Trend + true Risk Parity

S9  Equity / Gold / Bond Allocation

S23 Minimum Variance

S24 Maximum Diversification

S7  Defensive Asset Rotation

S13 Asset-Class Breadth

S14 Theme Rotation
```

Batch 01 不允许偷偷实现它们。

---

# 63. Final Research Principle

```text
Do not serially overfit one idea.

Freeze a diverse hypothesis batch.
Then let evidence eliminate most of it.

S3C:
local trend filtering

S4A:
risk allocation

S8A:
simple timing

S27A:
trend + risk sizing

S30:
complexity hurdle

One frozen protocol.
Five independent screens.
No tuning.
No mid-batch redesign.

Most strategies SHOULD fail.

A failure is useful
if it closes an economic hypothesis.

Only surviving strategies earn
robustness work.

Only robust strategies earn
execution work.

Only execution-validated strategies earn
prospective candidacy.

S2 R1 remains frozen.

Strategy research
>
infrastructure engineering.

---

Status: completed

Batch: BATCH_01_DIVERSE_TRANSPARENT_BASELINES

Protocol Freeze SHA: ae218d70b73adac1922a0c761cd74ab6e02bf955 (V2; R1 S27 comparator correction disclosed)

Results SHA: pending Commit B

Decisions: S3C REJECT_S3C_BASELINE; S4A REJECT_S4A_BASELINE; S8A REJECT_S8A_BASELINE; S27A ADVANCE_S27A_TO_ROBUSTNESS; S30 REFERENCE_BASELINE.
```

# Goal: TactiCore Batch 03 — Earned Stage Advancement

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Execution Validation Reviewer
+
External Evidence Reviewer
+
Repository Architecture Maintainer
```

---

# 0. Why This Work Exists

TactiCore 当前不缺 strategy ideas。

它已经形成明确的生命周期：

```text
External Evidence Gate
        ↓
Historical Baseline
        ↓
Robustness
        ↓
Execution Validation
        ↓
Candidate Freeze
        ↓
Prospective Shadow
```

截至最新 repository state：

```text
S2 R1
→ FROZEN / PROSPECTIVE_SHADOW_ACTIVE

S27A
→ baseline PASS
→ robustness PASS
→ ADVANCE_TO_EXECUTION_REVIEW

S10A
→ baseline PASS
→ ADVANCE_TO_ROBUSTNESS

S4B
→ no economic result
→ BLOCK_UPSTREAM_DEPENDENCY

S30
→ REFERENCE_BASELINE
```

因此下一步必须推进：

```text
already-earned stages
```

而不是继续横向增加 strategy count。

本批定义为：

```text
BATCH_03_EARNED_STAGE_ADVANCEMENT
```

包含三个彼此独立的 track：

```text
Track A
S27A authoritative execution review

Track B
S10A robustness

Track C
Canonical ERC transfer through newly available
mature upstream implementation
```

不增加第四个策略。

---

# 1. Repository First

开始前重新读取 remote `main`。

执行：

```bash
git fetch origin
git status
git log --oneline -20
```

不要相信本 Prompt 中预期 HEAD。

依次阅读：

```text
AGENTS.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/STRATEGY_RESEARCH_MAP.md
docs/CURRENT_STATE.md
docs/goal.md

research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml

research/results/BATCH_02_EVIDENCE_INFORMED_VALIDATION.md
research/results/S27A_ROBUSTNESS_V1.md
research/results/S10A_VOL_TARGETING_V1.md
research/results/S4B_ERC_TRANSFER_V1.md

research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md

research/batches/batch_02/PROTOCOL.md
research/batches/batch_02/PROTOCOL_V2.md

config/s27_trend_inverse_vol.toml
config/s10a_vol_targeting.toml
config/strategy.toml
config/universe.csv

tacticore/strategies/trend_inverse_vol.py
tacticore/strategies/volatility_targeting.py
tacticore/strategies/multi_asset_trend.py

tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/experiments/run_s2_rqalpha_validation.py
research/experiments/run_s27a_robustness.py
research/experiments/run_s10a_vol_targeting.py

research/shadow/s2_r1/candidate_manifest.json
```

记录：

```text
starting HEAD
working tree
recent commits

S2 candidate integrity

S27 baseline hashes
S27 robustness hashes

S10 baseline hashes
S10 Protocol V2 hashes

canonical data hashes

RQAlpha installed version

external evidence snapshot date
```

Repository evidence wins.

---

# 2. Protect S2 R1

第一条命令之一必须是：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

禁止修改：

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

S2 R1 继续独立积累真正前瞻 evidence。

Batch 03 不得把 S27/S10 的结果回填到 S2。

---

# 3. External Evidence Gate First

本 Goal 仍必须首先执行 External Evidence Gate。

但不要重新做整个 Batch 00。

只检查：

```text
VOL_SCALED_TREND
VOL_TARGETING
ERC_RISK_PARITY
```

以及真正需要的 upstream implementation evidence。

---

# 4. Important New Upstream Evidence — skfolio

当前 registry 主要记录：

```text
Riskfolio-Lib
PyPortfolioOpt
```

但在开始本 Goal 时必须实际重新检查：

```text
skfolio official documentation
skfolio PyPI
skfolio current stable release
skfolio RiskBudgeting API
```

重点确认：

```text
Python compatibility

long-only support

RiskBudgeting

equal risk budget semantics

variance risk measure

current stable API
```

如果当前官方 stable skfolio 仍具备：

```text
Python >= 3.10
RiskBudgeting
long-only
equal risk budgeting / risk parity
```

则这是新的：

```text
mature upstream implementation evidence
```

它改变的是：

```text
S4B implementation-path assumption
```

而不是：

```text
ERC economic evidence tier
```

ERC 仍然：

```text
E2_ESTABLISHED_METHOD
```

---

# 5. Do NOT Rewrite S4B History

S4B：

```text
BLOCK_S4B_UPSTREAM_DEPENDENCY
```

必须永久保留。

因为它准确记录：

```text
Riskfolio-Lib 7.3.0 route
was blocked
```

不要改成：

```text
S4B passed
```

也不要删除其报告。

新的 upstream route 定义为：

```text
S4C_CANONICAL_ERC_SKFOLIO_TRANSFER_V1
```

S4C 不是新金融策略。

它是：

```text
same canonical ERC question
+
new mature upstream implementation path
```

---

# 6. Update External Evidence Before Coding

如果 skfolio evidence 成立，在：

```text
research/strategy_evidence/
STRATEGY_EVIDENCE_REGISTRY.yaml
```

更新：

```text
ERC_RISK_PARITY
```

增加：

```text
skfolio
```

implementation prior。

记录：

```text
version
evidence_as_of
official docs
RiskBudgeting API
Python support
```

同时最小更新：

```text
docs/STRATEGY_RESEARCH_MAP.md
```

但：

```text
external tier stays E2
```

不要因为软件出现改变经济 evidence tier。

---

# 7. Batch 03 Protocol

新增：

```text
research/batches/batch_03/
  EVIDENCE_GATE.md
  PROTOCOL.md
```

必须在任何真实 performance result 出现前冻结。

PROTOCOL 至少包含：

```text
canonical data hashes

S2 manifest hash

S27 frozen strategy hashes

S10 frozen strategy hashes

RQAlpha version

skfolio version if Track C is available

all Track A decision gates

all Track B parameter neighborhoods

all Track B decision gates

all Track C semantics

all Track C comparators

all Track C decision gates
```

---

# 8. Two-Commit Discipline

继续沿用 Batch 01 / 02 已证明有效的模式：

```text
Commit A
=
protocol freeze
+
implementation
+
synthetic tests
+
NO new historical result

then

historical / execution runs

then

Commit B
=
results
+
ledger/catalog/state updates
```

如果出现 correctness bug：

```text
INVALID_RUN
→ disclose
→ protocol V2
→ freeze
→ rerun affected track
```

不得静默修改。

---

# ============================================================

# TRACK A — S27A AUTHORITATIVE EXECUTION REVIEW

# ============================================================

# 9. Research Question

唯一问题：

> S27A 已通过 historical baseline 与 robustness。将完全冻结的 S27A target schedule 交给 RQAlpha 原生市场执行与账户语义后，经济证据和目标实现质量是否仍然成立？

不重新研究：

```text
trend existence
trend windows
volatility windows
cost robustness
parameter plateau
```

这些已关闭。

---

# 10. Frozen S27A Identity

保持：

```text
trend_window = 200
vol_window = 60

same S2 risk universe

same fallback = 511010.SS

same 10 bps fees
same 5 bps slippage

monthly signal
next-observation execution
```

禁止修改：

```text
config/s27_trend_inverse_vol.toml

tacticore/strategies/trend_inverse_vol.py
```

---

# 11. Freeze Exact S27 Target Schedule

在 RQAlpha run 前生成：

```text
research/results/
s27a_v1_frozen_targets.csv
```

来源必须是：

```text
existing canonical data
+
frozen S27 config
+
frozen S27 strategy implementation
```

流程：

```text
build_month_end_targets
        ↓
build_execution_weights
        ↓
drop rows without execution target
        ↓
freeze exact target schedule
```

非常重要：

S27A 当前 baseline 使用：

```text
monthly targets
```

不是 S2 的：

```text
SIGNAL_CHANGE_ONLY
```

不得错误复用 S2 target-submission policy。

---

# 12. Frozen Target Artifact

记录：

```text
number of target dates

first execution date
last execution date

symbols

SHA-256

source config hash

strategy source hash

canonical data hash
```

目标：

```text
weights >= 0

sum(weights) == 1

dates unique

dates strictly increasing
```

---

# 13. Frozen-Schedule Reproduction Gate

在任何 RQAlpha execution 前：

把：

```text
s27a_v1_frozen_targets.csv
```

重新交给 VectorBT。

它必须精确 reproduce frozen S27A 200/60 baseline：

```text
CAGR ~= 7.7867%
MaxDD ~= -12.5034%
Sharpe ~= 1.015
```

数值以 repository authoritative artifacts 为准。

使用严格 machine tolerance。

如果失败：

```text
BLOCK_S27A_EXECUTION_REPRODUCTION
```

停止 Track A。

不要运行 RQAlpha。

---

# 14. RQAlpha Upstream Check

执行前重新检查：

```text
current PyPI stable RQAlpha
current changelog
current project dependency
```

如果现有：

```text
rqalpha>=6.3,<6.4
```

仍对应当前仓库已验证的 stable path：

继续使用。

如果出现新稳定版本：

不要自动升级。

只有当前 6.3 出现执行 blocker 时才做有界 compatibility investigation。

---

# 15. Reuse Existing S2 Execution Infrastructure

最大化复用：

```text
research/experiments/run_s2_rqalpha_validation.py

tacticore/engines/rqalpha_adapter.py
```

但不要复制一个完整 execution framework。

建议新增：

```text
research/experiments/
run_s27a_rqalpha_execution_review.py
```

可以抽取极小、显然通用的：

```text
frozen-target replay helper
native result parser
target tracking helper
```

但只有在无需改变 S2 行为的情况下。

不要大规模重构 S2 已关闭 evidence code。

---

# 16. RQAlpha Must NOT Recompute Signals

RQAlpha 内部只能读取：

```text
frozen target schedule
```

禁止重新计算：

```text
200-day trend
60-day vol
risk budget
inverse-vol weights
```

执行验证必须严格回答：

```text
Can native execution implement
the frozen economic decision?
```

而不是重新跑策略。

---

# 17. RQAlpha Execution Semantics

复用已经通过 S2 closure 的：

```text
order_target_portfolio

partial_fill_on_insufficient_cash = true

native matching

native fees

native slippage

native account

native position

native analyser
```

不要：

```text
local cash reserve
manual order sizing
retry engine
custom lot handling
custom matching
```

---

# 18. S27 Execution Evidence

至少输出：

```text
RQAlpha CAGR
RQAlpha MaxDD
RQAlpha native Sharpe
turnover
trade count
transaction cost

native order count

failed order events
cash rejection events
cash residual cancellations
volume limited events

ending cash
minimum cash
average cash ratio
```

目标 tracking：

```text
each execution date

monthly reviews

total absolute weight deviation

maximum asset deviation

cash residual

materially off-target flag
```

material threshold 延续：

```text
5 percentage points
```

避免重新定义。

---

# 19. Explain Every Material Difference

每个显著 execution deviation 必须关联：

```text
native order status

fill evidence

cash constraint

volume constraint

market availability

other RQAlpha-native reason
```

不能留下：

```text
UNEXPLAINED_EXECUTION_DIFFERENCE
```

然后仍宣布 PASS。

---

# 20. S27 Execution Advance Gate

预注册：

### Integrity

```text
all frozen execution dates replayed
NO missing schedule dates
NO extra signal dates
```

### Cash

```text
cash rejection events = 0
```

原生：

```text
partial-fill residual cancellation
```

允许存在，但必须解释。

### Target tracking

要求：

```text
average execution-date
total absolute weight deviation
<= 3%
```

且：

```text
materially off-target execution dates
<= 10% of frozen execution dates
```

### Cash drag

要求：

```text
average cash ratio <= 2%
```

### Economics

相对 frozen VectorBT：

```text
RQAlpha CAGR > 0

RQAlpha CAGR
>= VectorBT CAGR - 2 percentage points

RQAlpha MaxDD
must not worsen by more than
5 percentage points
```

不要使用：

```text
RQAlpha native Sharpe == VectorBT Sharpe
```

作为硬门槛。

两个框架 risk-free-rate / calendar 口径不同。

---

# 21. S27 Decision

只能输出：

```text
ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW

DO_NOT_ADVANCE_S27A_EXECUTION

BLOCK_S27A_EXECUTION_REPRODUCTION

BLOCK_S27A_EXECUTION_ENVIRONMENT
```

即使：

```text
ADVANCE
```

本 Goal 也禁止：

```text
freeze S27 Research Candidate R1

start S27 prospective shadow
replace S2 R1
```

这些属于下一次 Principal Review。

---

# ============================================================

# TRACK B — S10A ROBUSTNESS

# ============================================================

# 22. Research Question

唯一问题：

> S10A 20-day / 10% unlevered volatility-targeting result，是一个宽容的稳定机制，还是恰好依赖于单个 lookback / target-vol specification？

这是：

```text
E3 LOCAL_ADJUDICATION
```

不是：

```text
optimize S10A
```

---

# 23. Freeze Existing S10 Baseline

禁止修改：

```text
config/s10a_vol_targeting.toml

tacticore/strategies/volatility_targeting.py

research/results/S10A_VOL_TARGETING_V1.md
```

中心 baseline 永远：

```text
vol_window = 20

target_volatility = 10%

scale = [0,1]

NO leverage
```

无论邻域哪一个表现最好，都不改变中心。

---

# 24. Correctness Semantics Must Stay V2

必须继续使用：

```python
pct_change(fill_method=None)
```

aligned returns。

禁止重新引入：

```text
implicit forward fill
```

UNAVAILABLE / missing 必须真实保持。

---

# 25. Generalized Robustness Evaluator

新增：

```text
research/experiments/
run_s10a_robustness.py
```

参数变化只存在于 experiment layer。

不要修改 frozen strategy source。

首先要求：

```text
20-day / 10%
```

完全 reproduce：

```text
CAGR
MaxDD
Sharpe
Calmar
turnover
```

与合法 Protocol V2 baseline 一致。

否则：

```text
BLOCK_S10A_ROBUSTNESS_REPRODUCTION
```

---

# 26. One-Factor-at-a-Time Volatility Window

固定：

```text
target volatility = 10%
```

测试：

```text
10 valid aligned returns
20 valid aligned returns
40 valid aligned returns
```

经济含义约为：

```text
~2 weeks
~1 month
~2 months
```

不测试：

```text
10 / 20 / 40
×
8 / 10 / 12
```

Cartesian grid。

---

# 27. One-Factor-at-a-Time Target Volatility

固定：

```text
vol_window = 20
```

测试：

```text
8%
10%
12%
```

全部：

```text
max_scale = 1
NO leverage
```

---

# 28. Never Select the Best Parameter

本轮禁止：

```text
best target volatility
best lookback
```

20/10 永远保留为 baseline。

Robustness 只回答：

```text
Does the mechanism survive
reasonable nearby assumptions?
```

---

# 29. Timing-Matched Comparator

所有 S10 robustness case 都与：

```text
MONTHLY_STATIC_25_25_25_25
```

比较。

必须完全相同：

```text
signal dates
execution dates
fees
slippage
capital
canonical data
```

这样差异只来自：

```text
volatility scaling
```

S30 annual static：

```text
context only
```

---

# 30. Fixed Periods

复用 Batch 02 / S27 已冻结的 period boundaries：

```text
2013-03-29 → 2016-12-31

2017-01-01 → 2019-12-31

2020-01-01 → 2022-12-31

2023-01-01 → 2026-08-31
```

如果 S10 的实际 common-data start 晚于第一区间起点：

只按实际可用开始，

但不能重新选日期。

---

# 31. Rolling Evidence

复用已有：

```text
rolling 3Y
rolling 5Y
```

month-end methodology。

至少记录：

```text
positive CAGR share

Sharpe

MaxDD

relative Sharpe vs monthly static

relative MaxDD vs monthly static
```

不要发明新的 rolling windows。

---

# 32. S10 Cost Sensitivity

完全复用 S27/S2 定义：

```text
VectorBT per-side fees

slippage = 0

15 bps
30 bps
50 bps
```

只对中心：

```text
20 / 10%
```

运行。

不做 parameter × cost grid。

---

# 33. S10 Robustness Gate — Absolute

所有：

```text
10/10
20/10
40/10

20/8
20/12
```

必须：

```text
CAGR > 0

Sharpe > 0

MaxDD > -20%
```

---

# 34. S10 Robustness Gate — Parameter Neighborhood

对于：

```text
window dimension
10 / 20 / 40
```

至少：

```text
2 / 3
```

必须满足相对 monthly-static：

```text
CAGR >= comparator CAGR - 1.5pp

MaxDD strictly better

AND

Sharpe > comparator Sharpe
OR
Calmar > comparator Calmar
```

对于：

```text
target dimension
8 / 10 / 12
```

同样至少：

```text
2 / 3
```

满足上述 gate。

---

# 35. S10 Robustness Gate — Non-Degeneration

中心 20/10 必须继续：

```text
0.40 < average scale < 0.95
```

对于 target-vol dimension：

至少：

```text
2 / 3
```

variants 不能退化为：

```text
average scale >= 0.95
```

或：

```text
average scale <= 0.40
```

边缘 case 退化：

可以记录，

但不得偷偷改 target。

---

# 36. S10 Fixed-Period Gate

中心：

```text
20 / 10%
```

必须：

```text
positive CAGR
in all four fixed periods
```

并且至少：

```text
3 / 4 periods
```

满足：

```text
MaxDD <= monthly-static MaxDD
```

以及至少：

```text
3 / 4 periods
```

满足：

```text
Sharpe > comparator
OR
Calmar > comparator
```

---

# 37. S10 Rolling Gate

中心：

```text
rolling 3Y positive CAGR share >= 90%

rolling 5Y positive CAGR share >= 95%
```

并报告：

```text
share of rolling 3Y windows
where Sharpe > monthly-static

share of rolling 3Y windows
where MaxDD improves

same for rolling 5Y
```

要求至少：

```text
60%
```

rolling 3Y windows 满足：

```text
Sharpe improvement
OR
MaxDD improvement
```

不要通过挑选 crisis windows 证明价值。

---

# 38. S10 Cost Gate

50 bps per-side fee-only case：

```text
CAGR > 0

Sharpe >= 0.70
```

---

# 39. S10 Decision

只能：

```text
ADVANCE_S10A_TO_EXECUTION_REVIEW

REJECT_S10A_ROBUSTNESS

BLOCK_S10A_ROBUSTNESS_REPRODUCTION
```

即使 ADVANCE：

本 Goal 也：

```text
DO NOT run S10 RQAlpha
```

---

# ============================================================

# TRACK C — S4C CANONICAL ERC THROUGH SKFOLIO

# ============================================================

# 40. Why Track C Exists

S4B 的结论是：

```text
Riskfolio-Lib route blocked
```

不是：

```text
ERC rejected
```

如果当前 official skfolio：

```text
supports project Python versions
+
contains canonical RiskBudgeting
```

则这属于新的：

```text
upstream implementation evidence
```

允许建立新的 bounded local question。

---

# 41. S4C Identity

定义：

```text
S4C_CANONICAL_ERC_SKFOLIO_TRANSFER_V1
```

Canonical external mapping：

```text
Equal Risk Contribution
/
Risk Parity
```

Tier：

```text
E2_ESTABLISHED_METHOD
```

Action：

```text
UPSTREAM_COMPARE
```

---

# 42. Dependency Compatibility Gate

在任何 performance code 前：

使用隔离 resolver 检查：

```text
Python 3.10
Python 3.11
Python 3.12
```

与当前：

```text
TactiCore dependency set
+
current stable skfolio
```

是否可以可靠解析。

不要因为本机当前是单一 Python 版本就认为项目范围兼容。

如果失败：

```text
BLOCK_S4C_SKFOLIO_DEPENDENCY
```

不得：

```text
lower Python support
use old package
fork package
write local solver
```

---

# 43. Research-Only Dependency

如果 compatibility PASS：

增加：

```text
research optional dependency
```

而不是 core runtime dependency。

版本范围必须基于实际 verified current release。

记录：

```text
resolved skfolio version
Python versions tested
solver dependencies
lock state
```

---

# 44. skfolio Responsibility Boundary

skfolio 只负责：

```text
ERC target-weight optimization
```

VectorBT 继续负责：

```text
portfolio simulation
accounting
trades
returns
drawdown
```

禁止使用 skfolio portfolio simulation 替代 VectorBT。

这不是第三套 backtester。

---

# 45. Canonical S4C Universe

复用当前 multi-asset risk universe。

只读：

```text
config/strategy.toml
```

不要修改 S2 config。

fallback：

```text
511010.SS
```

不参与 risk-asset ERC optimization。

---

# 46. S4C Data Semantics

每个 month-end：

要求最近：

```text
61 common valid prices
```

产生：

```text
60 aligned daily returns
```

只有在所有该 eligible set 的共同日期上计算。

严禁：

```text
forward fill
zero fill
pairwise silent covariance
```

至少：

```text
6 eligible assets
```

否则：

```text
fallback = 100%
```

---

# 47. Canonical ERC Call

优先直接使用 official：

```text
skfolio.optimization.RiskBudgeting
```

明确配置：

```text
risk measure = variance

equal risk budget

long only

fully invested

no leverage

no expected-return objective

no minimum-return constraint

no custom risk budgets

no alternative risk measure
```

不要测试：

```text
CVaR risk parity
semi-variance risk parity
HERC
HRP
maximum diversification
```

---

# 48. Solver Failure Semantics

如果：

```text
eligible assets >= 6
```

但 upstream solver 无法产生：

```text
finite
nonnegative
sum-to-one
```

weights：

不得偷偷 fallback。

该 track 直接记录：

```text
BLOCK_S4C_UPSTREAM_EXECUTION
```

并保留错误证据。

这样不会让 solver failure 伪装成 defensive alpha。

---

# 49. S4C Primary Comparators

必须基于完全相同：

```text
aligned window
eligible set
signal date
execution date
costs
```

创建：

```text
SAME_ELIGIBLE_EQUAL_WEIGHT

SAME_ELIGIBLE_INVERSE_VOL
```

注意：

现有 S4A inverse-vol 使用：

```text
asset-own valid returns
```

而 S4C 公平 comparator 必须使用：

```text
same aligned returns
```

所以不要直接拿 S4A 历史结果当 primary comparator。

S4A 和 S30 仅 contextual。

---

# 50. S4C Timing

```text
month-end aligned return estimation
        ↓
skfolio ERC target
        ↓
next canonical observation
        ↓
VectorBT
```

使用：

```text
10bps fee
5bps slippage
1,000,000 initial cash
```

---

# 51. S4C Coverage Gate

要求：

```text
>= 6 eligible assets
```

在至少：

```text
80%
```

evaluated month-end observations 成立。

否则：

```text
BLOCK_S4C_DATA_COVERAGE
```

---

# 52. S4C Absolute Gate

要求：

```text
CAGR > 0

Sharpe >= 0.50

MaxDD > -35%
```

---

# 53. S4C Relative Gate

相对：

```text
SAME_ELIGIBLE_INVERSE_VOL
```

要求：

```text
CAGR >= comparator CAGR - 1.5pp

MaxDD cannot be worse by > 2pp
```

以及至少满足：

```text
Sharpe >= comparator Sharpe + 0.03
```

或：

```text
Calmar >= comparator Calmar + 0.05
```

并要求：

```text
turnover <= 1.5 × inverse-vol turnover
```

---

# 54. S4C Concentration Diagnostics

至少记录：

```text
maximum weight

median maximum weight

95th-percentile maximum weight

effective number of assets

months with any asset > 50%
```

不要事后添加：

```text
weight cap
```

救结果。

---

# 55. S4C Decision

只能：

```text
ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS

DO_NOT_ADVANCE_S4C_ERC_TRANSFER

BLOCK_S4C_SKFOLIO_DEPENDENCY

BLOCK_S4C_DATA_COVERAGE

BLOCK_S4C_UPSTREAM_EXECUTION
```

不得把 local failure 写成：

```text
risk parity does not work
```

---

# ============================================================

# COMMON FREEZE / EXECUTION

# ============================================================

# 56. No Other Strategies

本 Goal 禁止实现：

```text
MinVar
Shrinkage MinVar
HRP
HERC
Maximum Diversification
Black-Litterman

Theme Rotation
Asset-Class Breadth
Defensive Rotation
PIT Sector Rotation

new momentum variants
```

尤其不能因为 skfolio 已安装就：

```text
顺便测试库中其它 optimizer
```

---

# 57. Expected Files

合理新增：

```text
research/batches/batch_03/
  EVIDENCE_GATE.md
  PROTOCOL.md

research/experiments/
  run_s27a_rqalpha_execution_review.py
  run_s10a_robustness.py
  run_s4c_erc_skfolio_transfer.py

research/results/
  s27a_v1_frozen_targets.csv

  S27A_RQALPHA_EXECUTION_REVIEW_V1.md
  S10A_ROBUSTNESS_V1.md
  S4C_ERC_SKFOLIO_TRANSFER_V1.md

  BATCH_03_EARNED_STAGE_ADVANCEMENT.md

  focused small CSV artifacts
```

可能修改：

```text
pyproject.toml
uv.lock
```

仅当：

```text
skfolio compatibility gate passes
```

---

# 58. Files Normally Unchanged

正常保持：

```text
AGENTS.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md

data/**

config/strategy.toml
config/universe.csv

config/s27_trend_inverse_vol.toml
config/s10a_vol_targeting.toml

tacticore/strategies/multi_asset_trend.py
tacticore/strategies/trend_inverse_vol.py
tacticore/strategies/volatility_targeting.py

tacticore/engines/rqalpha_adapter.py

research/shadow/s2_r1/**
```

已有永久规则已经足够。

---

# 59. Synthetic / Unit Tests Before Freeze

至少测试：

## S27

```text
frozen schedule == existing S27 execution semantics

schedule sums to 1

next-observation timing

monthly target submission preserved

no signal calculation inside RQAlpha callback

replayed-date exactness

decision boundary tests
```

## S10

```text
20/10 generalized evaluator
exactly reproduces frozen strategy targets

fill_method=None preserved

10/20/40 are one-factor only

8/10/12 are one-factor only

no Cartesian generation

decision boundary tests
```

## S4C

```text
equal risk budget call

long-only weights

sum(weights) == 1

aligned-return semantics

missing rows not filled

<6 eligible → fallback

eligible solver failure → BLOCK

same-eligible comparators

next-observation timing

decision boundary tests
```

---

# 60. Commit A — Protocol Freeze

完成：

```text
evidence refresh

new upstream check

all code

all synthetic tests

all decision gates

PROTOCOL.md
```

但：

```text
NO S27 RQAlpha result

NO S10 robustness result

NO S4C historical result
```

时运行：

```bash
uv sync --extra dev
```

若 S4C dependency pass：

```bash
uv sync --extra dev --extra research
```

再：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

全部 PASS。

创建 Commit A。

建议：

```text
freeze batch 3 earned stage advancement protocol
```

push。

记录：

```text
BATCH_03_PROTOCOL_FREEZE_SHA
```

---

# 61. After Freeze — Run Track A

运行：

```bash
uv run python \
  research/experiments/run_s27a_rqalpha_execution_review.py
```

禁止结果出来后修改 gate。

---

# 62. After Freeze — Run Track B

运行：

```bash
uv run python \
  research/experiments/run_s10a_robustness.py
```

---

# 63. After Freeze — Run Track C

仅在 dependency gate PASS 时：

```bash
uv run python \
  research/experiments/run_s4c_erc_skfolio_transfer.py
```

若 blocked：

生成 block report 即可。

不要强行运行。

---

# 64. Invalid-Run Discipline

如果发现：

```text
wrong comparator

wrong timing

forward-fill

incorrect RQAlpha replay

wrong risk-budget call

lookahead

incorrect eligible set
```

必须：

```text
INVALID_RUN_BATCH_03_<N>.md
```

记录：

```text
what was wrong
what results became invalid
whether performance had been seen
what is allowed to change
```

然后：

```text
Protocol V2
freeze commit
rerun affected track
```

---

# 65. Batch Summary

生成：

```text
research/results/
BATCH_03_EARNED_STAGE_ADVANCEMENT.md
```

第一张表：

| Track | Stage Before      | Question     | Decision |
| ----- | ----------------- | ------------ | -------- |
| S27A  | robustness PASS   | execution    |          |
| S10A  | baseline PASS     | robustness   |          |
| S4C   | upstream reopened | ERC transfer |          |

第二张 performance 表按实际可比较数据填写。

不要创建：

```text
winner score
```

---

# 66. Cross-Track Interpretation

必须回答：

```text
1. Can S27A actually be implemented
   under authoritative RQAlpha semantics?

2. Are S27A execution deviations
   economic or merely framework accounting differences?

3. Does S10A survive nearby
   lookback and target-vol assumptions?

4. Is S10A's benefit spread across periods
   or concentrated in a few crises?

5. Does canonical ERC add anything
   beyond aligned inverse-vol?

6. Did skfolio solve an implementation blocker
   without forcing local optimizer code?

7. Which complexity is justified?

8. Which tracks deserve another stage?

9. Which tracks should stop?
```

---

# 67. Research Ledger

追加新的 local questions。

按最新编号顺延，例如：

```text
S27A execution review

S10A robustness

S4C skfolio ERC transfer
```

不要修改：

```text
RL-025
RL-026
RL-027
```

的历史事实。

S4C 必须明确引用：

```text
S4B remains blocked under Riskfolio route

S4C exists because a new mature upstream
implementation became available
```

---

# 68. External Registry

结果后更新对应：

```text
VOL_SCALED_TREND

VOL_TARGETING

ERC_RISK_PARITY
```

仅更新：

```text
implementation prior

local mapping

local status

local evidence refs

remaining gap
```

本地结果不得修改外部 tier。

---

# 69. STRATEGY_RESEARCH_MAP

更新：

```text
S27A lifecycle

S10A lifecycle

S4C mapping
```

例如：

```text
S27A:
EXECUTION_REVIEW_PASS / STOP

S10A:
ROBUSTNESS_PASS / REJECT

S4C:
TRANSFER_PASS / NO_ADVANCE / BLOCK
```

使用实际结果。

---

# 70. STRATEGY_CATALOG

仅记录：

```text
local strategy lifecycle
```

详细数字仍放：

```text
research/results/
```

---

# 71. CURRENT_STATE

完成后只记录真正当前前沿。

无论结果如何，状态先停：

```text
BATCH_03_COMPLETE

AWAIT_BATCH_03_ARCHITECT_REVIEW
```

如果 S27A execution PASS：

只写：

```text
candidate-freeze eligible
```

不要创建 candidate。

如果 S10 robustness PASS：

只写：

```text
execution-review eligible
```

不要运行 execution。

如果 S4C baseline PASS：

只写：

```text
robustness eligible
```

不要运行 robustness。

---

# 72. docs/goal.md

替换已完成 Batch 02 Goal。

完成后记录：

```text
Status: completed

Batch:
BATCH_03_EARNED_STAGE_ADVANCEMENT

Starting HEAD:
...

Protocol Freeze SHA:
...

Protocol revisions:
...

Results SHA:
...

S27A:
...

S10A:
...

S4C:
...

Next:
AWAIT_BATCH_03_ARCHITECT_REVIEW
```

---

# 73. Final S2 Integrity Gate

结束前：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

如果失败：

```text
BATCH_03_INVALID
```

不要更新 S2 manifest。

---

# 74. Full Validation

运行：

```bash
uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

如果启用 research extra：

从 clean dependency sync 再验证。

---

# 75. Architecture Drift Audit

最终逐项回答：

```text
Did we modify S2 R1?

Did we modify frozen S27 semantics?

Did we modify frozen S10 semantics?

Did we pick best S10 parameters?

Did we run a Cartesian S10 grid?

Did RQAlpha recompute S27 signals?

Did we implement a local execution engine?

Did we implement an ERC solver?

Did we silently replace Riskfolio history?

Did we test MinVar/HRP/HERC because skfolio exposes them?

Did we change external evidence tier
because of local returns?

Did we start Theme Rotation?

Did we create another generic framework?

Did we create a new candidate automatically?
```

正常全部：

```text
NO
```

---

# 76. Commit B

完成全部结果后：

```bash
git status
git diff
```

创建：

```text
evaluate batch 3 earned strategy stages
```

push。

如果需要最后修正：

```text
docs/goal.md
```

中的 Results SHA，

允许再做一个 metadata-only commit。

---

# 77. Final Completion Report

最终回复至少给：

```text
starting HEAD

protocol freeze SHA

protocol revision SHA if any

results SHA

ending HEAD
```

## S27A

```text
frozen target count

frozen target SHA

VectorBT reproduction

RQAlpha version

RQAlpha CAGR
MaxDD
Sharpe

transaction cost
turnover

cash rejection events
volume-limit events

average cash ratio

average execution-date deviation

materially off-target execution dates

decision
```

## S10A

```text
central reproduction

10/20/40 window results

8/10/12 target results

fixed-period evidence

rolling 3Y/5Y

50-bps cost result

average scale

decision
```

## S4C

```text
skfolio version

Python 3.10 resolution
Python 3.11 resolution
Python 3.12 resolution

RiskBudgeting API used

coverage

ERC metrics

aligned inverse-vol metrics

aligned equal-weight metrics

turnover

concentration

decision
```

最后明确：

```text
S2 R1 modified?
NO

S27 candidate created?
NO

S10 RQAlpha run?
NO

S4B historical result rewritten?
NO

Local ERC solver created?
NO

New unrelated strategies added?
NO
```

---

# 78. Stop Condition

Batch 03 完成后必须停止。

不要自动继续：

```text
S27 candidate freeze

S10 execution review

S4C robustness

Batch 04
```

等待下一次 repository-first Principal Review。

---

# 79. Final Principle

```text
Do not reward an idea
for merely surviving one backtest.

A strategy earns the next stage.

S27A earned execution review.
Test execution.

S10A earned robustness.
Test robustness.

ERC was blocked by one upstream path.
A new mature upstream path now exists.
Use it instead of writing a solver.

Do not skip stages.

Do not optimize after seeing results.

Do not confuse software availability
with economic evidence.

Do not confuse local failure
with global literature.

Freeze first.
Run second.
Record evidence.
Then stop.

Literature first.
Upstream first.
Local evidence next.
Execution before prospective candidacy.
Infrastructure last.
```

---

## Completion Metadata

```text
Status: completed

Batch:
BATCH_03_EARNED_STAGE_ADVANCEMENT

Starting HEAD:
cb4d05d

Protocol Freeze SHA:
fb25f4c0d15b2e4a4034ff0d770cb8f174068213

Protocol revisions:
48b04e587e58d7912e6967287d48aa271ce8b818 (S27A reproduction metric start)
08de5f88b36be4b19af3fdf01312d7d71e2c8761 (S10A rolling union)
cea33d6 (S10A complete 8/10/12 target dimension)

Results SHA:
debe373907ef5319995a829a2ce7e541d7486bb2

S27A:
BLOCK_S27A_EXECUTION_ENVIRONMENT

S10A:
REJECT_S10A_ROBUSTNESS

S4C:
ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS

Next:
AWAIT_BATCH_03_ARCHITECT_REVIEW
```

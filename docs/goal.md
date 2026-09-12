# Goal: TactiCore Batch 04 — Community-Backed PIT Tradability & Research Semantics Closure

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Architect
+
Research Correctness Reviewer
+
Execution Semantics Reviewer
+
Community Capability Integrator
```

---

# 0. Why This Work Exists

TactiCore 当前已经不缺 strategy ideas。

最新 repository state：

```text
S2 R1
→ FROZEN / PROSPECTIVE_SHADOW_ACTIVE

S27A
→ historical baseline PASS
→ robustness PASS
→ execution review BLOCKED

S10A
→ baseline PASS
→ robustness REJECTED

S4C
→ canonical ERC transfer PASS
→ robustness eligible

S30
→ reference baseline
```

但是 Batch 03 暴露了两个系统级 research-correctness 问题。

---

# 1. Correctness Problem A — PIT Tradability

S27A frozen schedule 第一笔执行日期早于 fallback ETF `511010` 的上市日期。

仓库自身：

```text
config/universe.csv
511010.SS
start_date = 2013-03-25
```

但 S27A frozen schedule 从更早日期就可能给：

```text
511010.SS > 0 target weight
```

RQAlpha 因此拒绝：

```text
511010.XSHG
invalid order_book_id / instrument
```

这说明问题不能简单归类为：

```text
RQAlpha bundle incomplete
```

更可能是：

```text
strategy target
→ positive weight assigned
→ asset not yet tradable
→ VectorBT silently tolerates / ignores
→ authoritative execution exposes violation
```

这是一个系统性 PIT / tradability contract 缺口。

---

# 2. Correctness Problem B — Signed MaxDD Semantics

TactiCore 的 MaxDD 定义为负值：

```text
-10% is better than -20%
```

因此：

```text
candidate MaxDD >= comparator MaxDD
```

表示：

```text
candidate drawdown is no worse
```

Batch 03 S10A fixed-period gate 中存在：

```text
candidate_max_drawdown <= comparator_max_drawdown
```

这与：

```text
negative MaxDD representation
```

的经济含义相反。

同一 decision function 其他位置又正确使用：

```text
candidate_max_drawdown > comparator_max_drawdown
```

因此这是明确的 metric-semantic inconsistency。

---

# 3. Batch 04 Mission

本 Goal 不开发新策略。

本 Goal 只完成：

```text
1. 社区能力审计
2. PIT tradability contract
3. signed metric semantics closure
4. existing evidence impact audit
5. corrected bounded replay
6. permanent architecture / rule update
```

定义：

```text
BATCH_04_COMMUNITY_BACKED_PIT_CORRECTNESS_CLOSURE
```

---

# 4. Core Principle

从本 Goal 开始：

```text
Community semantics first.

Do not build a PIT platform
if mature upstream systems already define
asset lifetime and tradability semantics.
```

参考社区能力：

```text
RQAlpha
→ Chinese instrument lifecycle authority

Zipline
→ AssetFinder.lifetimes() architectural pattern

LEAN
→ IsTradable / pre-trade validation semantics

Qlib
→ future financial-data PIT reference,
   NOT current ETF lifetime solution
```

TactiCore 只实现：

```text
thin local contract
```

不要实现：

```text
PITEngine
AssetLifecycleDatabase
SecurityMasterService
DynamicUniversePlatform
ResearchKnowledgeGraph
```

---

# 5. Repository First

开始前：

```bash
git fetch origin
git status
git log --oneline -20
```

重新读取最新 remote `main`。

不要相信本 Prompt 中硬编码 SHA。

必须阅读：

```text
AGENTS.md

README.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/STRATEGY_RESEARCH_MAP.md
docs/CURRENT_STATE.md
docs/goal.md

config/universe.csv
config/strategy.toml
config/s10a_vol_targeting.toml
config/s27_trend_inverse_vol.toml

tacticore/data/**
tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

tacticore/strategies/multi_asset_trend.py
tacticore/strategies/trend_inverse_vol.py
tacticore/strategies/volatility_targeting.py

research/results/S27A_RQALPHA_EXECUTION_REVIEW_V1.md
research/results/S10A_ROBUSTNESS_V1.md
research/results/S4C_ERC_SKFOLIO_TRANSFER_V1.md
research/results/BATCH_03_EARNED_STAGE_ADVANCEMENT.md

research/experiments/run_s27a_rqalpha_execution_review.py
research/experiments/run_s10a_robustness.py
research/experiments/run_s4c_erc_skfolio_transfer.py

research/shadow/s2_r1/candidate_manifest.json
```

记录：

```text
starting HEAD
working tree
recent commits
S2 candidate verification status
canonical data hashes
universe metadata hash
framework versions
```

---

# 6. Protect S2 R1

第一阶段必须运行：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

禁止修改：

```text
config/strategy.toml
config/universe.csv   # unless only evidence-backed metadata correction is absolutely required
data/canonical/**
tacticore/strategies/multi_asset_trend.py
tacticore/engines/rqalpha_adapter.py
research/shadow/s2_r1/candidate_manifest.json
```

如果未来发现 S2 frozen schedule 存在 tradability violation：

不要静默修改 S2。

必须：

```text
mark candidate integrity issue
stop
escalate
```

本 Goal 不得直接重建 S2 candidate。

---

# 7. Community Capability Audit

在写任何 PIT code 前，先核实当前官方社区能力。

至少检查：

```text
RQAlpha current Instrument API

listed_date
de_listed_date
listed_at()
de_listed_at()
active_at()
```

同时确认：

```text
RQAlpha current project version
instrument metadata access path
```

参考：

```text
Zipline Asset.start_date
Zipline Asset.end_date
Zipline AssetFinder.lifetimes()
```

仅用于架构语义参考。

参考：

```text
LEAN Security.IsTradable
dynamic universe
pre-trade validation
```

仅用于 execution-boundary semantics。

Qlib PIT：

```text
document as future financial-data PIT reference
```

不要引入 Qlib dependency。

---

# 8. Community Evidence Artifact

新增：

```text
research/batches/batch_04/COMMUNITY_PIT_AUDIT.md
```

记录：

```text
RQAlpha capability
Zipline lifetime pattern
LEAN tradability pattern
Qlib PIT scope

what TactiCore will reuse

what TactiCore will NOT implement
```

最终结论应类似：

```text
TactiCore does not need a PIT engine.

It needs:
1. asset lifecycle metadata
2. date × asset tradability predicate
3. target validation boundary
```

---

# 9. Define the PIT Tradability Contract

新增极薄模块：

```text
tacticore/data/tradability.py
```

不要放到：

```text
tacticore/engines/
```

因为它属于 data / semantic contract。

---

# 10. Required Primitive 1 — Asset Lifetime Metadata

设计轻量 representation，例如：

```python
@dataclass(frozen=True)
class AssetLifetime:
    symbol: str
    listed_date: pd.Timestamp
    delisted_date: pd.Timestamp | None
```

数据来源：

优先：

```text
existing universe metadata
+
RQAlpha cross-validation
```

不要建立数据库。

---

# 11. Required Primitive 2 — active_at()

语义：

```python
active_at(asset, date)
```

必须对应社区成熟定义：

```text
listed_date <= date
AND
(date <= delisted_date OR no delisted_date)
```

边界语义必须有测试。

---

# 12. Required Primitive 3 — price_available_at()

```python
price_available_at(prices, symbol, date)
```

要求：

```text
column exists
AND
row exists
AND
price finite
AND
price > 0
```

不要：

```text
forward-fill
interpolate
zero-fill
```

---

# 13. Required Primitive 4 — tradable_at()

MVP 语义：

```text
tradable_at(symbol, date)
=
active_at(symbol, date)
AND
price_available_at(symbol, date)
```

不要在本 Goal 增加：

```text
suspension database
limit-up logic
liquidity filters
broker eligibility
```

除非现有上游已经免费提供且是完成当前 correctness closure 的必要条件。

当前目标只解决：

```text
pre-listing
post-delisting
missing execution price
```

---

# 14. Required Primitive 5 — Tradability Mask

借鉴 Zipline `lifetimes()`：

```python
build_tradability_mask(
    dates,
    symbols,
    lifetimes,
    prices,
) -> DataFrame[bool]
```

结果：

```text
date × symbol
```

例如：

```text
                2012-06-01   2013-03-25
510300.SS          True          True
511010.SS          False         True
513500.SS          False         False
```

这是薄数据结构。

不要实现长期缓存平台。

---

# 15. Required Primitive 6 — Target Tradability Validator

核心 invariant：

```text
positive target weight
requires tradable_at == True
on execution date
```

实现类似：

```python
validate_execution_targets(
    execution_weights,
    prices,
    tradability_mask,
)
```

如果存在：

```text
weight > tolerance
AND
tradable == False
```

必须：

```text
raise explicit correctness error
```

例如：

```text
UntradableTargetError
```

错误中必须包含：

```text
execution_date
symbol
target_weight
listed_date
price_available
```

---

# 16. No Silent Simulator Semantics

永久禁止：

```text
VectorBT receives positive target
for NaN-priced / inactive asset
and decides what to do silently.
```

VectorBT 只允许收到：

```text
validated execution targets
```

---

# 17. Simulator Boundary

不要修改 VectorBT 内部。

在：

```text
run_target_weights()
```

之前增加 fail-fast validation。

设计优先：

```text
validation boundary
```

而不是：

```text
strategy-specific PIT logic
```

如果要修改：

```text
tacticore/engines/vectorbt_adapter.py
```

只增加：

```text
optional / mandatory validated-target check
```

不要让 adapter 生成 universe。

---

# 18. Instrument Metadata Authority Hierarchy

在规则中明确：

```text
1. authoritative upstream instrument metadata
2. canonical price availability
3. repository-local universe metadata cross-check
```

对于当前中国 ETF：

```text
RQAlpha instrument metadata
```

是重要 authority。

但是：

```text
RQAlpha bundle coverage
```

与：

```text
instrument historical existence
```

必须区分。

bundle 缺数据不等于资产历史不存在。

---

# 19. universe.csv Is Not the Sole Authority

`config/universe.csv:start_date` 保留：

```text
human-readable
version-controlled
research provenance
```

但必须验证：

```text
local start_date
vs
upstream listed_date
```

新增 bounded audit script，例如：

```text
research/experiments/
verify_asset_lifetimes.py
```

输出：

```text
symbol
local_start_date
rqalpha_listed_date
match
```

若不一致：

```text
do not silently overwrite
```

记录 discrepancy。

---

# 20. Do NOT Require RQAlpha at Every VectorBT Run

不要让研究层变成：

```text
every backtest
→ launch RQAlpha
```

更合理的是：

```text
RQAlpha lifecycle metadata
→ audit / extract / verify
→ lightweight local metadata
→ VectorBT research
```

保持：

```text
VectorBT fast research
RQAlpha authoritative execution
```

---

# 21. Permanent Rule — Strategy Inception

在：

```text
docs/RESEARCH_RULES.md
```

增加：

> Strategy inception is the first execution date on which the strategy's complete target can be legally formed and executed under the frozen strategy semantics.

禁止把：

```text
first dataframe date
first signal row
first non-NaN target row
```

自动当成 inception。

---

# 22. Complete Target Semantics

若 strategy target 是：

```text
risk assets
+
fallback asset
```

则：

```text
fallback asset
```

也是 complete target contract 的一部分。

如果 fallback 尚未可交易：

不得：

```text
assign positive fallback target
```

---

# 23. Missing Fallback Semantics

对于当前历史研究：

如果策略需要 fallback：

```text
fallback not tradable
```

时，默认：

```text
NO EXECUTABLE TARGET
```

而不是：

```text
pretend cash
renormalize risk assets
use another bond
skip silently
```

除非原始策略协议已经明确另一种行为。

---

# 24. Dynamic Universe Semantics

永久规则：

```text
U(t) =
assets active and eligible at time t
```

策略只能：

```text
select / rank / allocate
inside U(t)
```

禁止：

```text
today's ETF universe
backfilled into history
```

这条规则未来适用于：

```text
sector ETF
theme ETF
asset-class ETF
```

但本 Goal 不重新研究 Theme Rotation。

---

# 25. Signed Metric Semantics

新增一个非常小的统一 helper。

优先放：

```text
research/metrics.py
```

或现有 research common module。

不要创建：

```text
MetricsFramework
```

---

# 26. Required Drawdown Helpers

至少：

```python
drawdown_better(candidate, comparator)
```

语义：

```text
candidate > comparator
```

例如：

```text
-0.10 > -0.20
→ True
```

以及：

```python
drawdown_no_worse(candidate, comparator)
```

语义：

```text
candidate >= comparator
```

---

# 27. Required Metric Tests

必须有：

```python
assert drawdown_better(-0.10, -0.20)
assert not drawdown_better(-0.20, -0.10)

assert drawdown_no_worse(-0.10, -0.10)
assert drawdown_no_worse(-0.10, -0.20)
assert not drawdown_no_worse(-0.20, -0.10)
```

防止 signed semantics 再次漂移。

---

# 28. Permanent Rule — MaxDD Sign

更新：

```text
docs/RESEARCH_RULES.md
```

明确：

```text
MaxDD is stored as a negative number.

Less negative = better.

candidate >= comparator
means no worse drawdown.
```

以后所有 decision function 必须遵循。

---

# 29. Protocol Freeze Before Revalidation

新增：

```text
research/batches/batch_04/PROTOCOL.md
```

在任何 corrected performance run 前冻结：

```text
PIT contract
metric semantics
affected strategy list
allowed code changes
revalidation scope
decision policy
```

---

# 30. Batch 04 Is a Correctness Closure, Not New Research

非常重要：

不得借 PIT 修复：

```text
change parameters
change strategy family
change threshold
change comparator
change cost
change universe composition
```

只允许修正：

```text
execution legality
evaluation start
signed metric comparison
```

---

# 31. Impact Audit Before Rerun

先扫描 repository 中所有：

```text
execution target > 0
```

但执行日：

```text
asset inactive
OR price missing
```

的情况。

至少审计：

```text
S2
S27A
S10A
S4C
S30
S3 family
S4A
S8A
```

输出：

```text
research/results/
PIT_TRADABILITY_IMPACT_AUDIT_V1.md
```

以及：

```text
pit_tradability_violations_v1.csv
```

字段：

```text
strategy
execution_date
symbol
target_weight
listed_date
price_available
violation_type
```

---

# 32. Impact Classification

每个策略分类：

```text
UNAFFECTED

AFFECTED_PRE_EVALUATION_ONLY

AFFECTED_METRICS

AFFECTED_DECISION
```

不要自动重跑所有历史实验。

只重跑：

```text
AFFECTED_METRICS
or
AFFECTED_DECISION
```

---

# 33. S2 Control Audit

首先验证 S2 R1 frozen schedule：

```text
all positive target weights
must be tradable
```

如果：

```text
0 violations
```

记录：

```text
S2_R1_PIT_INTEGRITY_PASS
```

然后再次：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

如果 S2 有 violation：

```text
STOP
```

不要继续其他 corrected research。

状态：

```text
BATCH_04_BLOCKED_BY_S2_CANDIDATE_INTEGRITY
```

等待 Principal Review。

---

# 34. S30 Control Audit

S30 是重要复杂度 reference。

确认：

```text
first allocation date
```

是否发生在：

```text
510300
513500
518880
511010
```

全部 active + valid price 之后。

如果本来正确：

只记录 PASS。

不要重新研究。

---

# 35. S27A Correctness Revalidation

当前 frozen schedule 不能直接保留为权威 schedule，因为已包含 pre-listing fallback target。

不要简单：

```text
delete first rows
```

而是使用：

```text
same frozen strategy semantics
+
PIT tradability contract
```

重新形成：

```text
corrected executable schedule
```

---

# 36. S27A Rule Before Fallback Listing

如果：

```text
strategy wants positive fallback weight
AND
fallback not tradable
```

则该月：

```text
NO EXECUTABLE TARGET
```

不得：

```text
replace with cash
replace with 511880
replace with another bond
renormalize uptrend assets
```

因为这些都改变策略。

---

# 37. S27A Corrected Inception

由 contract 自动得到：

```text
first executable complete target
```

不要 hard-code：

```text
2013-03-25
```

或任何人工日期。

---

# 38. S27A Corrected Baseline

在 corrected inception 后，

使用完全相同：

```text
trend_window = 200
vol_window = 60
fees = 10bps
slippage = 5bps
monthly target submission
```

重新计算 baseline。

产生：

```text
S27A_PIT_CORRECTED_BASELINE_V1.md
```

---

# 39. S27A Corrected Robustness

只有 corrected baseline 仍达到原 baseline gate 才继续。

参数保持：

```text
trend:
160
180
200
220
240

vol:
40
60
80
```

仍然：

```text
one-factor-at-a-time
```

不改任何 threshold。

使用原先：

```text
fixed periods
rolling
costs
```

但 period metrics 应从：

```text
max(period start, corrected inception)
```

开始。

---

# 40. S27A Decision

只能：

```text
RESTORE_S27A_EXECUTION_REVIEW_ELIGIBILITY

REJECT_S27A_AFTER_PIT_CORRECTION

BLOCK_S27A_PIT_REPRODUCTION
```

本 Goal：

```text
DO NOT run RQAlpha execution
```

即使 restore eligibility。

---

# 41. S10A Correctness Revalidation

S10A 有两个 independent corrections：

```text
A. tradability / inception
B. signed MaxDD semantics
```

不能只修一个。

---

# 42. S10A Base Asset PIT Rule

S10A base：

```text
510300
513500
518880
511010
```

固定：

```text
25 / 25 / 25 / 25
```

因此：

```text
MONTHLY_STATIC_25_25_25_25
```

只有在四个资产均 active + price available 后才存在。

---

# 43. S10A Inception

策略 inception：

```text
first executable monthly target
after all four base assets are tradable
```

之后如果：

```text
20-day vol history unavailable
```

则原策略定义仍允许：

```text
scale = 0
→ fallback bond allocation
```

前提：

```text
bond itself tradable
```

---

# 44. S10A MaxDD Gate Correction

原 fixed-period gate 的经济意图：

```text
candidate MaxDD no worse than comparator
```

必须使用：

```text
drawdown_no_worse(candidate, comparator)
```

即：

```text
candidate >= comparator
```

不要直接写裸比较符。

---

# 45. S10A Historical Run Treatment

当前 Batch 03 S10A robustness：

```text
REJECT_S10A_ROBUSTNESS
```

必须标：

```text
SUPERSEDED_BY_CORRECTNESS_REVIEW
```

不是删除。

保留：

```text
INVALID_RUN history
Protocol V2/V3/V4
```

---

# 46. S10A Corrected Replay

完全保留：

```text
20 / 10 center

window:
10
20
40

target:
8%
10%
12%

monthly static comparator

same costs

same rolling definitions
```

不改其他 gate。

---

# 47. S10A Corrected Decision

只能：

```text
RESTORE_S10A_EXECUTION_REVIEW_ELIGIBILITY

REJECT_S10A_AFTER_CORRECTNESS_CLOSURE

BLOCK_S10A_CORRECTNESS_REPRODUCTION
```

本 Goal：

```text
DO NOT run RQAlpha
```

---

# 48. S4C Correctness Revalidation

S4C 当前：

```text
<6 eligible
→ fallback 100%
```

语义可以保留。

但前提：

```text
fallback tradable_at execution date
```

---

# 49. S4C Before Fallback Availability

如果：

```text
<6 eligible
AND
fallback inactive
```

则：

```text
NO EXECUTABLE TARGET
```

不是：

```text
100% pre-listing fallback
```

---

# 50. S4C Corrected Inception

由：

```text
first executable complete target
```

自动决定。

不要硬编码。

---

# 51. S4C Corrected Baseline Replay

完全保持：

```text
61 aligned prices
60 fill_method=None returns
min eligible = 6

skfolio RiskBudgeting
variance
equal risk budget
long-only
fully invested

same-eligible inverse-vol comparator
same-eligible equal-weight comparator

10bps fee
5bps slippage
```

不修改任何 gate。

---

# 52. S4C Corrected Decision

只能：

```text
RESTORE_S4C_ROBUSTNESS_ELIGIBILITY

DO_NOT_ADVANCE_S4C_AFTER_PIT_CORRECTION

BLOCK_S4C_PIT_REPRODUCTION
```

本 Goal：

```text
DO NOT run S4C robustness
```

---

# 53. Historical Artifacts Must Not Be Deleted

保留：

```text
S27A_RQALPHA_EXECUTION_REVIEW_V1.md
S10A_ROBUSTNESS_V1.md
S4C_ERC_SKFOLIO_TRANSFER_V1.md
BATCH_03_EARNED_STAGE_ADVANCEMENT.md
```

因为它们是真实历史证据。

新报告必须说明：

```text
why prior result was affected
what exact correctness issue was found
which parts remain valid
which decision is superseded
```

---

# 54. New Correctness Reports

至少生成：

```text
research/results/
PIT_TRADABILITY_IMPACT_AUDIT_V1.md

S27A_PIT_CORRECTNESS_REVALIDATION_V1.md

S10A_CORRECTNESS_REVALIDATION_V1.md

S4C_PIT_CORRECTNESS_REVALIDATION_V1.md

BATCH_04_COMMUNITY_BACKED_PIT_CORRECTNESS_CLOSURE.md
```

---

# 55. Machine-Readable Artifacts

至少：

```text
pit_tradability_violations_v1.csv

asset_lifetime_audit_v1.csv

s27a_pit_corrected_summary_v1.csv

s10a_corrected_robustness_summary_v1.csv

s4c_pit_corrected_comparison_v1.csv
```

只生成真正需要的 artifacts。

不要复制全部历史 CSV。

---

# 56. Update ARCHITECTURE.md

这次允许且要求修改。

新增：

```text
Asset Lifecycle / PIT Tradability
```

在策略执行之前。

架构应类似：

```text
External Evidence
        ↓
Canonical Data
+
Asset Lifecycle
        ↓
PIT Eligible Universe
        ↓
Strategy Semantics
        ↓
Target Portfolio
        ↓
Tradability Validation
        ↓
VectorBT Historical Research
        ↓
RQAlpha Authoritative Execution
```

---

# 57. Architecture Ownership

明确：

## Upstream

```text
instrument lifecycle semantics
```

优先借鉴/验证：

```text
RQAlpha
```

## TactiCore

只拥有：

```text
thin lifecycle metadata snapshot
tradability mask
target validation
local research contracts
```

## VectorBT

只负责：

```text
historical portfolio simulation
after target legality validation
```

## RQAlpha

负责：

```text
authoritative native execution
```

---

# 58. Update RESEARCH_RULES.md

增加永久规则：

## PIT Tradability Invariant

```text
A positive target weight is only valid
if the asset is active and price-observable
at the execution timestamp.
```

---

# 59. No Silent Missing-Price Rule

```text
NaN price
does not mean:
cash
zero
skip
hold
fallback
```

它表示：

```text
target cannot be executed
unless the frozen strategy explicitly defines
an alternative.
```

---

# 60. Dynamic Universe Rule

```text
The eligible universe must be date-aware.

Today's universe may not be backfilled
into historical periods.
```

---

# 61. Strategy Inception Rule

```text
Evaluation begins only when
the strategy can legally form and execute
its complete frozen target semantics.
```

---

# 62. Signed Metric Rule

```text
MaxDD is negative.

Less negative is better.

Use centralized helpers,
not ad-hoc comparison operators.
```

---

# 63. Update AGENTS.md

未来 Agent 提出任何 strategy experiment 前必须检查：

```text
PIT universe?
asset lifetime?
execution-date price?
fallback availability?
```

External Evidence Gate 后增加：

```text
PIT Tradability Gate
```

流程：

```text
External Evidence Gate
        ↓
PIT Tradability Gate
        ↓
Local Evidence Gap
        ↓
Experiment
```

---

# 64. AGENTS PIT Gate

未来每个 strategy Goal 至少回答：

```text
What is the date-aware universe?

What metadata defines asset lifetime?

What happens before fallback exists?

What happens if execution price is missing?

What defines strategy inception?

Can every positive target be executed?
```

回答不了：

```text
NO BACKTEST
```

---

# 65. Update STRATEGY_RESEARCH_MAP

增加：

```text
PIT ETF universe
launch/survivorship
```

从：

```text
open future concern
```

升级为：

```text
ACTIVE RESEARCH CORRECTNESS FOUNDATION
```

并映射当前 Batch 04。

---

# 66. Update RESEARCH_LEDGER

追加独立 local decisions，例如按实际编号：

```text
PIT tradability contract

signed MaxDD semantics

S27 PIT revalidation

S10 correctness revalidation

S4C PIT revalidation
```

不要改写原历史条目。

如旧 decision 被 supersede：

明确：

```text
SUPERSEDED
```

并链接新 entry。

---

# 67. Update STRATEGY_CATALOG

S27/S10/S4C 的 local lifecycle 必须反映：

```text
pre-correction decision
→ correctness revalidation
→ authoritative current decision
```

不要删除历史阶段。

---

# 68. Update CURRENT_STATE

最终只写：

```text
S2 R1 current state

Batch 04 correctness result

S27 current eligibility

S10 current eligibility

S4C current eligibility

remaining blockers
```

状态：

```text
BATCH_04_COMPLETE
AWAIT_BATCH_04_ARCHITECT_REVIEW
```

---

# 69. Do NOT Automatically Advance

即使：

```text
S27 restore execution eligibility
S10 restore execution eligibility
S4C restore robustness eligibility
```

本 Goal 也不得：

```text
run S27 RQAlpha
run S10 RQAlpha
run S4C robustness
```

先停下来审计。

---

# 70. Tests — Tradability

至少：

```text
asset before listing → inactive

asset on listing date → active

asset after delisting → inactive

NaN execution price → not tradable

finite positive execution price → price available
```

---

# 71. Tests — Positive Target Invariant

```text
positive target + inactive asset → fail

positive target + missing price → fail

zero target + inactive asset → allowed

positive target + active valid price → pass
```

---

# 72. Tests — Fallback

构造：

```text
risk asset signal negative
fallback not yet listed
```

必须：

```text
NO executable target
```

不能：

```text
100% fallback
```

---

# 73. Tests — Strategy Inception

构造：

```text
targets before full tradability
targets after full tradability
```

确认 inception：

```text
first fully executable target
```

---

# 74. Tests — Drawdown

必须：

```text
-10% better than -20%
-10% no worse than -10%
-20% worse than -10%
```

---

# 75. Tests — S10 Regression

必须针对 Batch 03 bug 写 regression test：

```text
candidate = -0.10
comparator = -0.13

period MaxDD gate
→ PASS
```

防止原：

```text
<=
```

再次出现。

---

# 76. Protocol Freeze Commit

在任何 corrected performance replay 前：

完成：

```text
community audit
tradability module
metric helpers
tests
impact scanner
PROTOCOL.md
```

运行：

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate
```

全部 PASS。

创建：

```text
Commit A
```

建议：

```text
freeze community backed PIT correctness protocol
```

push。

记录：

```text
BATCH_04_PROTOCOL_FREEZE_SHA
```

---

# 77. Run Impact Audit First

Protocol freeze 后第一步不是跑策略。

先运行：

```text
verify_asset_lifetimes.py

audit_pit_tradability.py
```

得到：

```text
all affected strategies
all invalid target dates
```

如果出现此前未预期的大面积问题：

仍然按 protocol 分类。

不要临时扩大策略改造范围。

---

# 78. Correctness Revision Discipline

如果 audit 又发现新的 correctness defect：

必须：

```text
INVALID_RUN_BATCH_04_R<N>.md
```

然后：

```text
Protocol V2
freeze
rerun affected scope
```

继续保持 Batch 01/02/03 已经建立的证据纪律。

---

# 79. Run Corrected Revalidations

顺序：

```text
1. S2 integrity check

2. S30 correctness check

3. S27 corrected baseline + robustness

4. S10 corrected robustness

5. S4C corrected baseline
```

每项独立。

某项 reject 不阻止其他项。

只有：

```text
shared PIT contract bug
S2 candidate integrity failure
canonical data corruption
```

才暂停整批。

---

# 80. No New Data Download

禁止：

```text
redownload historical prices
change canonical snapshot
```

本 Goal 只使用：

```text
existing canonical data
existing metadata
upstream lifecycle cross-check
```

若现有 metadata 无法验证：

记录 BLOCK。

不要偷偷修历史数据。

---

# 81. No New Strategy Semantics

禁止：

```text
cash fallback
alternate bond
fallback substitution
renormalization
no-trade bands
new weight caps
new cost assumptions
```

PIT correction 不能变成策略 redesign。

---

# 82. No New Generic Framework

禁止：

```text
SecurityMaster service
Tradability database
PIT platform
dynamic-universe framework
execution policy engine
generic strategy registry
```

目标：

```text
a few pure functions
+
tests
+
contracts
```

---

# 83. CI Is Still Secondary

如果当前 GitHub 仍无 CI status checks：

可以在 final report 记录。

但本 Goal：

```text
DO NOT add CI
```

除非现有 repo rule 已明确要求。

PIT correctness 优先于 CI engineering。

---

# 84. Batch Summary

生成：

```text
research/results/
BATCH_04_COMMUNITY_BACKED_PIT_CORRECTNESS_CLOSURE.md
```

至少表格：

| Strategy | Prior State         | PIT Issue | Metric Issue | Corrected Decision |
| -------- | ------------------- | --------- | ------------ | ------------------ |
| S2       | shadow candidate    |           |              |                    |
| S27A     | execution blocked   |           |              |                    |
| S10A     | robustness rejected |           |              |                    |
| S4C      | robustness eligible |           |              |                    |
| S30      | reference           |           |              |                    |

---

# 85. Must Answer These Questions

Batch report 必须回答：

```text
1. Did VectorBT previously receive
   positive targets for inactive assets?

2. Which strategies were affected?

3. Did the issue affect only pre-evaluation rows
   or published metrics?

4. Is S2 R1 still intact?

5. Was S27 actually an RQAlpha environment issue,
   or a PIT contract issue?

6. Does S10 remain rejected
   after correcting MaxDD semantics?

7. Does S4C still qualify for robustness
   after PIT correction?

8. Which historical decisions are superseded?

9. Which remain valid?

10. What future strategy classes now benefit
    from the new PIT contract?
```

---

# 86. Architecture Drift Audit

最终回答：

```text
Did we build our own PIT platform?

Did we replace RQAlpha lifecycle semantics?

Did we add Qlib unnecessarily?

Did we use Zipline as a new backtester?

Did we use LEAN as a new execution engine?

Did we modify S2 frozen candidate?

Did we tune S27?

Did we tune S10?

Did we tune S4C?

Did we substitute fallback assets?

Did we change historical parameters?

Did we delete prior negative evidence?

Did we start a new strategy family?

Did we start Theme Rotation?

Did we start S4C robustness?
```

正常全部：

```text
NO
```

---

# 87. Final Validation

运行：

```bash
uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy

uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

---

# 88. Commit B

完成 corrected evidence 后：

```bash
git status
git diff
```

创建：

```text
close PIT tradability and signed metric correctness
```

push。

若只需补：

```text
docs/goal.md completion metadata
```

允许再有一个 metadata-only commit。

---

# 89. Final Report

最终回复必须包括：

```text
Starting HEAD
Protocol Freeze SHA
Protocol Revision SHAs
Results SHA
Ending HEAD
```

## Community capability

```text
RQAlpha lifecycle API verified?
YES/NO

Zipline lifetime pattern reviewed?
YES/NO

LEAN tradability pattern reviewed?
YES/NO

Qlib scope reviewed?
YES/NO
```

## PIT audit

```text
assets audited
strategy targets audited
violations found

S2 violations
S27 violations
S10 violations
S4C violations
S30 violations
```

## Corrected decisions

```text
S2:
...

S27A:
...

S10A:
...

S4C:
...

S30:
...
```

## Permanent changes

```text
ARCHITECTURE updated?
RESEARCH_RULES updated?
AGENTS updated?
tradability contract added?
metric semantics helper added?
```

---

# 90. Mandatory Stop

完成后：

```text
BATCH_04_COMMUNITY_BACKED_PIT_CORRECTNESS_CLOSURE_COMPLETE

AWAIT_BATCH_04_ARCHITECT_REVIEW
```

不得自动执行：

```text
S27 RQAlpha retry

S10 execution

S4C robustness

Theme Rotation

Batch 05
```

---

# 91. Final Principle

```text
Do not let a simulator
decide silently whether
an impossible target is acceptable.

Asset existence is point-in-time.

Tradability is point-in-time.

Universe membership is point-in-time.

Fallback availability is point-in-time.

A positive target
requires a real tradable instrument.

NaN is not cash.

Pre-listing is not missing data.

Today's universe
must not leak backward into history.

Use community lifecycle semantics.

Use a thin local contract.

Fail fast before simulation.

Keep VectorBT for research.

Keep RQAlpha for authoritative execution.

MaxDD is signed:
less negative is better.

Correctness before robustness.

Correctness before execution.

Correctness before new strategies.

Community first.
Evidence first.
PIT first.
Then research.
```

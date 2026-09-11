# Goal: TactiCore Batch 02 — Evidence-Informed Validation

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
External Evidence Reviewer
+
Repository Architecture Maintainer
```

---

# 0. Mission

TactiCore 已完成：

```text
Batch 00
External Strategy Evidence Foundation
```

因此从现在开始，禁止：

```text
想到策略
→ 直接实现
→ 跑回测
```

本 Goal 必须遵循：

```text
External Evidence Gate
        ↓
Local Evidence Gap
        ↓
Predeclared Protocol
        ↓
Implementation
        ↓
Protocol Freeze Commit
        ↓
Historical Experiment
        ↓
Evidence + Decision
        ↓
STOP for Principal Review
```

本批次：

```text
BATCH_02_EVIDENCE_INFORMED_VALIDATION
```

只研究三条已由 registry 支持的高相关性 gap：

```text
Track A
S27A Robustness

Track B
S4B Canonical ERC / Risk Parity ETF Transfer

Track C
S10A Unlevered Volatility Targeting Adjudication
```

三个问题属于不同研究类型：

```text
S27A
E3 / LOCAL_ADJUDICATION
→ 已通过 baseline，现在检验 robustness

S4B ERC
E2 / UPSTREAM_COMPARE
→ 成熟方法，本地检验 transfer，不重新证明 risk parity

S10A Volatility Targeting
E3 / LOCAL_ADJUDICATION
→ 文献有支持和反证，本地做裁决
```

---

# 1. Repository First

重新读取最新 remote `main`。

执行：

```bash
git fetch origin
git status
git log --oneline -20
```

不要相信本 Prompt 写死的 SHA。

必须阅读：

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

research/results/BATCH_01_TRANSPARENT_STRATEGY_SCREEN.md
research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md
research/results/S30_STATIC_STRATEGIC_ALLOCATION_V1.md
research/results/S4A_INVERSE_VOL_BASELINE_V1.md

research/batches/batch_01/PROTOCOL.md
research/batches/batch_01/PROTOCOL_V2.md

config/s27_trend_inverse_vol.toml
config/s4_inverse_vol.toml

tacticore/strategies/trend_inverse_vol.py
tacticore/strategies/inverse_vol_allocation.py
tacticore/engines/vectorbt_adapter.py

research/shadow/s2_r1/candidate_manifest.json
```

记录：

```text
starting HEAD

S2 R1 status

S27A baseline state
S27A baseline hashes

S30 state

S4A state

External evidence entries:
VOL_SCALED_TREND
ERC_RISK_PARITY
VOL_TARGETING

canonical data hashes
framework versions
```

仓库事实覆盖本 Prompt。

---

# 2. Current Local State Must Remain Intact

确认：

```text
S2 R1
=
FROZEN / PROSPECTIVE_SHADOW_ACTIVE
```

确认：

```text
S27A
=
ADVANCE_TO_ROBUSTNESS
```

确认：

```text
S3A/S3B/S3C/S4A/S8A
=
closed/rejected
```

确认：

```text
S30
=
REFERENCE_BASELINE
```

不得重新打开这些 baseline。

---

# 3. Protect S2 R1

开始前：

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

尤其禁止为了 Batch 02：

```text
改变 S2 universe
改变 S2 trend_window
改变 S2 fallback
改变 S2 manifest hashes
```

---

# 4. Phase A — Targeted External Evidence Hardening

在任何新策略代码或 robustness experiment 前，只针对本 Batch 三条 entry 做有界 evidence refresh。

不要刷新整个 registry。

目标 entry：

```text
VOL_SCALED_TREND

ERC_RISK_PARITY

VOL_TARGETING
```

---

# 5. S27A External Evidence Gate

必须回答：

```text
Canonical mapping:
trend / time-series momentum
+
volatility-based sizing

External tier:
E3_MIXED_CONDITIONAL

What is externally mature?

What part remains conditional?

Does canonical TSMOM literature already use
volatility scaling?

Is inverse-vol allocation itself alpha?
NO.

What did TactiCore actually add?
A long-only ETF transfer with
S2 trend state + inverse-vol active sizing.

Remaining local gap:
parameter / period / cost stability.
```

不得把：

```text
S27A historical PASS
```

包装成：

```text
new anomaly discovery
```

---

# 6. ERC External Evidence Gate

至少重新核实：

```text
Maillard / Roncalli / Teiletche
Equal Risk Contribution

current Riskfolio-Lib official documentation

current supported Riskfolio-Lib version
```

必须确认 upstream 是否能直接支持：

```text
long-only
equal risk budget
variance-based ERC
fully invested portfolio
```

优先使用：

```text
Riskfolio-Lib
```

原生 risk-parity API。

禁止首先编写：

```text
erc_solver.py
risk_parity_optimizer.py
custom convex optimizer
```

如果 upstream 无法在当前 Python / dependency 环境可靠运行：

```text
BLOCK_S4B_UPSTREAM_DEPENDENCY
```

而不是自己补一套 solver。

---

# 7. Volatility-Targeting External Evidence Gate

必须至少核实：

```text
Moreira & Muir
Volatility-Managed Portfolios

Cederburg et al.
contradictory / qualification evidence

recent China-specific evidence
if directly relevant
```

必须明确：

```text
original factor / portfolio domain

leverage assumptions

normalization assumptions

previous-month realized variance semantics

difference from a long-only ETF implementation
```

不得：

```text
只引用 Moreira/Muir 的支持结论
```

而忽略反证。

---

# 8. Evidence Update

只有发现有意义的新信息时，才更新：

```text
research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml

docs/STRATEGY_RESEARCH_MAP.md
```

更新：

```text
canonical sources
contradictory sources
evidence_as_of
scope
limitations
remaining_gap
```

不要：

```text
改变 tier 来迎合后续结果
```

External evidence freeze 必须先于 performance。

---

# 9. Batch 02 Protocol

新增：

```text
research/batches/batch_02/PROTOCOL.md
```

在任何真实 performance run 前冻结：

```text
three research questions

source evidence snapshot

exact implementations

all parameter sets

all comparison rules

all decision gates

data hashes

baseline hashes

prohibited post-result changes
```

---

# 10. Protocol Freeze Discipline

顺序必须严格：

```text
Evidence review
        ↓
Implement semantics + synthetic tests
        ↓
Write complete decision functions
        ↓
Write PROTOCOL.md
        ↓
NO PERFORMANCE RESULTS YET
        ↓
Protocol Freeze Commit
        ↓
Only then run historical experiments
```

如果任意真实收益数字已经被看到：

不得再修改：

```text
strategy semantics
parameter neighborhood
decision thresholds
primary comparator
```

除 correctness bug。

---

# Track A — S27A Robustness

# 11. Do NOT Modify the Frozen S27A Baseline

以下保持不变：

```text
config/s27_trend_inverse_vol.toml

tacticore/strategies/trend_inverse_vol.py

research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md

Batch 01 artifacts
```

当前 baseline identity：

```text
trend_window = 200
vol_window = 60
monthly
fallback = 511010.SS
fees = 10bps
slippage = 5bps
```

---

# 12. S27A Robustness Must Be Experiment-Layer Only

新增：

```text
research/experiments/run_s27a_robustness.py
```

如需通用化 baseline evaluator：

放在：

```text
research/experiments/
```

不要为了 robustness 修改 frozen strategy implementation。

必须首先证明：

```text
generalized evaluator
@ trend=200, vol=60
```

能够 reproduce Batch 01 corrected baseline。

如果不能：

```text
BLOCK_S27A_ROBUSTNESS_REPRODUCTION
```

---

# 13. S27A One-Factor-at-a-Time Parameter Plateau

禁止二维 grid search。

只运行：

## Trend dimension

固定：

```text
vol_window = 60
```

测试：

```text
trend_window =
160
180
200
220
240
```

这些窗口与既有 S2 plateau 邻域一致。

---

## Volatility dimension

固定：

```text
trend_window = 200
```

测试：

```text
vol_window =
40
60
80
```

禁止：

```text
5 × 3 Cartesian grid
```

因为这会扩大研究自由度。

---

# 14. No Best Parameter Selection

本 Goal 绝对禁止：

```text
choose best trend_window
choose best vol_window
```

中心 baseline 永远：

```text
200 / 60
```

robustness 只回答：

```text
Does the surrounding neighborhood
support the same economic conclusion?
```

---

# 15. S27A Period Stability

复用既有 S2 robustness 的：

```text
fixed-period definitions
rolling 3Y methodology
rolling 5Y methodology
```

不得为了 S27A 新挑历史断点。

如果现有 artifact 中已有明确 period boundaries：

原样复用。

---

# 16. S27A Cost Sensitivity

复用现有 S2：

```text
15 bps
30 bps
50 bps
```

成本场景定义和实现方式。

不要设计新的 cost grid。

---

# 17. S27A Primary Comparator

Primary comparator：

```text
S2 fixed-sleeve trend
```

必须保持：

```text
same trend window
same risk universe
same data
same timing
same risk-budget semantics
```

差异只允许：

```text
active-sleeve weighting

S2:
equal fixed sleeves

S27A:
inverse-vol active sizing
```

---

# 18. S27A Contextual Comparator

必须同时报告：

```text
S30 static strategic allocation
```

但：

```text
S27A does NOT automatically fail
just because S30 has higher Sharpe.
```

因为 S30 不隔离同一机制。

必须回答：

> S27A 的复杂度究竟带来了什么，而 S30 没有？

例如：

```text
lower drawdown
different exposure path
different crisis behavior
```

仅报告事实，不创造综合分数。

---

# 19. S27A Robustness Gate

Protocol freeze 前实现 decision function。

至少要求：

### Baseline reproduction

```text
PASS
```

### Trend neighborhood

5 个 trend windows 中：

```text
all CAGR > 0
```

且至少 4/5：

```text
retain >= 70% of baseline CAGR
retain >= 70% of baseline Sharpe
MaxDD > -25%
```

### Volatility neighborhood

40 / 60 / 80 三个全部：

```text
CAGR > 0
Sharpe > 0
MaxDD > -25%
```

且至少 2/3：

```text
retain >= 80% of baseline Sharpe
```

### Fixed periods

不得由单一历史时期贡献全部正面结论。

至少要求所有既有固定 periods：

```text
CAGR > 0
```

除非现有 S2 robustness methodology 明确采用其他预声明标准，则优先复用已存在标准。

### Rolling

至少：

```text
rolling 3Y positive-CAGR share >= 90%

rolling 5Y positive-CAGR share >= 95%
```

### Cost

最高预声明成本场景：

```text
CAGR > 0
Sharpe >= 0.50
```

---

# 20. S27A Decision

只能输出：

```text
ADVANCE_S27A_TO_EXECUTION_REVIEW

REJECT_S27A_ROBUSTNESS

BLOCK_S27A_ROBUSTNESS_REPRODUCTION
```

即使 ADVANCE：

本 Goal 也：

```text
DO NOT run RQAlpha
```

只是获得：

```text
execution-review eligibility
```

---

# Track B — S4B ERC / Risk Parity Transfer

# 21. Research Identity

新增：

```text
S4B_ERC_RISK_PARITY_V1
```

Canonical mapping：

```text
Equal Risk Contribution
/
Vanilla Risk Parity
```

External tier：

```text
E2_ESTABLISHED_METHOD
```

Research action：

```text
UPSTREAM_COMPARE
```

问题不是：

```text
Does risk parity work?
```

而是：

> 在 TactiCore 当前无杠杆、多资产 ETF universe 中，correlation-aware ERC 是否相对简单 equal-weight / inverse-vol allocation 提供足够的本地增量价值？

---

# 22. S4B Upstream Dependency

优先调查当前：

```text
Riskfolio-Lib
```

稳定版本。

如果当前稳定官方版本与 Python 3.10–3.12 和项目环境兼容：

新增 research-only optional dependency，例如：

```toml
[project.optional-dependencies]
research = [
  "riskfolio-lib>=<verified-version>,<next-major>"
]
```

实际版本必须以执行时官方稳定版本为准。

不要盲目照抄本 Prompt。

不要把 Riskfolio 变成核心 runtime dependency。

---

# 23. S4B Exact Universe

复用 S4A 使用的：

```text
multi-asset risk universe
```

从 frozen repository config 只读获得。

不得修改：

```text
config/strategy.toml
config/universe.csv
```

fallback：

```text
511010.SS
```

---

# 24. S4B Observation Window

为了隔离：

```text
inverse-vol
vs
correlation-aware ERC
```

固定：

```text
risk estimation window = 60 daily returns
```

与 S4A 的 60-return horizon 对齐。

不测试其他 window。

---

# 25. S4B Aligned Covariance Semantics

ERC 需要 covariance，因此必须使用真实共同日期。

每个 month-end：

1. 取截至 signal date 的最近 61 个 canonical observations；
2. asset 在这 61 个 observation 中必须都有有效价格；
3. 得到 60 个 aligned daily returns；
4. 至少：

```text
6 assets
```

满足才进入 ERC；

否则：

```text
fallback = 100%
```

严禁：

```text
forward fill missing price
zero fill
pairwise covariance with silent PSD repair
```

如果 aligned data 不足：

保持不可用。

---

# 26. S4B Canonical ERC

使用 Riskfolio-Lib 官方：

```text
Classic
variance / MV risk
equal risk budgets
long-only
fully invested
```

等价官方 vanilla ERC / risk-parity 模式。

不要：

```text
expected-return optimization
shorting
leverage
custom risk budgets
CVaR risk parity
drawdown risk parity
```

本轮只测试最经典、最低自由度版本。

---

# 27. S4B Execution

```text
month-end estimation
        ↓
target weights
        ↓
next canonical observation
        ↓
VectorBT
```

月度 target 是真实新估计，因此允许月度 rebalance。

---

# 28. S4B Comparators

Primary 1：

```text
SAME_ELIGIBLE_SET_INVERSE_VOL
```

Primary 2：

```text
SAME_ELIGIBLE_SET_EQUAL_WEIGHT
```

必须：

```text
same dates
same eligible assets
same timing
same costs
same initial capital
```

这样唯一主要差异是：

```text
weighting algorithm
```

S4A historical result只作为 contextual evidence。

S30 也是 contextual reference。

---

# 29. S4B Gate

要求：

```text
CAGR > 0
Sharpe >= 0.50
MaxDD > -35%
```

相对 SAME_ELIGIBLE_SET_INVERSE_VOL：

```text
CAGR >= comparator CAGR - 1.5pp

MaxDD no worse by > 2pp

AND

Sharpe >= comparator Sharpe + 0.03
OR
Calmar >= comparator Calmar + 0.05
```

并要求：

```text
turnover <= 1.5 × inverse-vol turnover
```

报告：

```text
max weight
median max weight
95th-percentile max weight
effective number of assets
```

不要因为 concentration 不好就事后加 cap。

---

# 30. S4B Decision

只能：

```text
ADVANCE_S4B_ERC_TRANSFER_TO_ROBUSTNESS

DO_NOT_ADVANCE_S4B_ERC_TRANSFER

BLOCK_S4B_UPSTREAM_DEPENDENCY

BLOCK_S4B_DATA_COVERAGE
```

本地失败：

```text
!=
risk parity globally invalid
```

---

# Track C — S10A Unlevered Volatility Targeting

# 31. Research Identity

新增：

```text
S10A_UNLEVERED_VOL_TARGETING_V1
```

Canonical mapping：

```text
volatility targeting
/
volatility-managed portfolio family
```

External tier：

```text
E3_MIXED_CONDITIONAL
```

Research action：

```text
LOCAL_ADJUDICATION
```

---

# 32. Why Use S30 as the Base

不要同时发明新的 alpha portfolio。

直接使用最简单、已经存在的：

```text
S30
25% China equity
25% US equity
25% Gold
25% China bond
```

作为 base allocation。

问题只问：

> 对这个已经很强的简单组合加无杠杆 volatility scaling，是否能进一步改善风险调整表现？

这样能够隔离：

```text
volatility timing
```

而不是：

```text
asset-selection alpha
```

---

# 33. S10A Fixed Specification

本轮只运行一个透明 specification：

```text
base weights:
25 / 25 / 25 / 25

volatility lookback:
20 valid daily portfolio returns

annualized target volatility:
10%

max exposure scale:
1.0

min exposure scale:
0.0

leverage:
NO
```

如果 Phase A 文献核实发现这一 specification 与 canonical volatility-targeting 含义存在重大错误：

允许在第一次 protocol freeze 前修正。

修正必须：

```text
based on external evidence,
not TactiCore performance.
```

一旦 protocol freeze：

不可改。

---

# 34. S10A Realized Volatility

构造当前 base portfolio 的 daily return：

```text
r_base =
0.25 * China equity return
+
0.25 * US equity return
+
0.25 * Gold return
+
0.25 * China bond return
```

使用过去：

```text
20 valid aligned daily observations
```

计算 annualized realized volatility。

禁止：

```text
future data
full-sample volatility
```

---

# 35. S10A Exposure

月末：

```text
scale =
min(
    1.0,
    target_vol / realized_vol
)
```

若 volatility 不可用：

```text
scale = 0
```

然后：

```text
China equity = 0.25 * scale
US equity    = 0.25 * scale
Gold         = 0.25 * scale
Bond         = 0.25 * scale + (1 - scale)
```

因此：

```text
sum(weights) = 1
no leverage
```

---

# 36. S10A Primary Comparator

建立：

```text
MONTHLY_STATIC_25_25_25_25
```

必须和 S10A：

```text
same signal dates
same monthly execution dates
same costs
same initial capital
```

区别只有：

```text
volatility scaling
```

原始 annual-rebalance S30：

```text
REFERENCE CONTEXT ONLY
```

这样避免把：

```text
monthly rebalance effect
```

误认为 volatility-management alpha。

---

# 37. S10A Diagnostics

至少输出：

```text
realized_vol
scale
risk_reduction
bond_weight

average_scale
median_scale
min_scale
max_scale

months scale < 1

target-change months
turnover
```

---

# 38. S10A Non-Degeneration

如果：

```text
average scale >= 0.95
```

则：

```text
REJECT_S10A_FILTER_DEGENERATION
```

因为策略几乎没工作。

如果：

```text
average scale <= 0.40
```

则：

```text
REJECT_S10A_DEFENSIVE_DEGENERATION
```

因为几乎退化为 bond-heavy allocation。

---

# 39. S10A Economic Gate

绝对：

```text
CAGR > 0
Sharpe >= 0.80
MaxDD > -25%
```

相对 monthly static comparator：

```text
MaxDD improvement >= 2pp

CAGR >= comparator CAGR - 1.5pp

AND

Sharpe > comparator Sharpe
OR
Calmar > comparator Calmar
```

不要求它必须：

```text
beat annual S30 CAGR
```

但必须完整报告。

---

# 40. S10A Decision

只能：

```text
ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS

REJECT_S10A_VOL_TARGETING

REJECT_S10A_FILTER_DEGENERATION

REJECT_S10A_DEFENSIVE_DEGENERATION

BLOCK_S10A_DATA
```

不得在失败后尝试：

```text
8% target
12% target
15% target
40-day vol
60-day vol
```

救结果。

---

# 41. No Other Strategies in Batch 02

禁止实现：

```text
Minimum Variance
Shrinkage MinVar
HRP
HERC
Maximum Diversification
Black-Litterman

Theme Rotation
Asset-Class Breadth
Defensive Asset Rotation
PIT Sector Rotation
```

这些保留给未来 Principal Review。

尤其：

```text
S4B ERC pass/fail
```

不得在同一 Goal 触发：

```text
“顺手试试 MinVar”
```

---

# 42. Expected Implementation

合理新增：

```text
research/batches/batch_02/
  PROTOCOL.md
  EVIDENCE_GATE.md

research/experiments/
  run_s27a_robustness.py
  run_s4b_erc_transfer.py
  run_s10a_vol_targeting.py

tacticore/strategies/
  erc_risk_parity.py
  volatility_targeting.py

config/
  s4b_erc_risk_parity.toml
  s10a_vol_targeting.toml

research/results/
  S27A_ROBUSTNESS_V1.md
  S4B_ERC_TRANSFER_V1.md
  S10A_VOL_TARGETING_V1.md
  BATCH_02_EVIDENCE_INFORMED_VALIDATION.md

  relevant small CSV artifacts
```

S27A baseline代码保持冻结。

---

# 43. Dependency Rule

如果需要 Riskfolio-Lib：

只作为：

```text
research optional dependency
```

不得把整个 Riskfolio 逻辑复制进仓库。

需要记录：

```text
package version
official API used
why it is required
why VectorBT alone does not own ERC optimization
```

VectorBT 仍负责：

```text
portfolio simulation
```

Riskfolio 只负责：

```text
ERC target-weight optimization
```

---

# 44. No New Generic Framework

禁止创建：

```text
OptimizerEngine
AllocationFramework
StrategyRegistry
ResearchManager
BacktestFramework
RobustnessPlatform
EvidenceDatabase
```

如果三个 runner 共享少量 metric helpers：

可以继续复用：

```text
research/experiments/batch_01_common.py
```

或抽取一个很小的 experiment helper。

不要提升成平台。

---

# 45. Protocol Freeze Commit

完成：

```text
External Evidence Gate
+
configs
+
strategy semantics
+
runners
+
decision functions
+
synthetic tests
+
PROTOCOL.md
```

但还没有运行真实历史 performance 后：

运行：

```bash
uv sync --extra dev
```

如 S4B 使用 research extra：

```bash
uv sync --extra dev --extra research
```

然后：

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

全部通过。

创建：

```text
Commit A
```

建议：

```text
freeze batch 2 evidence informed validation protocol
```

push。

记录：

```text
BATCH_02_PROTOCOL_FREEZE_SHA
```

---

# 46. No Post-Freeze Design Changes

Protocol freeze 后：

禁止修改：

```text
S27 robustness neighborhoods

ERC semantics

ERC estimator/window

volatility target

volatility lookback

decision gates

primary comparators
```

---

# 47. Correctness-Bug Exception

如果 performance 后发现明确：

```text
lookahead
wrong comparator
incorrect execution timing
incorrect Riskfolio call
target-sum bug
incorrect eligibility
```

必须：

```text
mark run INVALID_RUN
```

然后：

```text
document bug
fix it
create Protocol V2
commit V2 freeze
rerun entire affected track
```

不得静默修复。

遵循 Batch 01 已经建立的良好 precedent。

---

# 48. Run Entire Batch

Protocol freeze 后统一执行：

```bash
uv run python research/experiments/run_s27a_robustness.py

uv run python research/experiments/run_s4b_erc_transfer.py

uv run python research/experiments/run_s10a_vol_targeting.py
```

单条失败不应提前结束其他独立 track。

只有：

```text
S2 integrity failure
canonical data corruption
shared correctness bug
```

才中断整批。

---

# 49. Batch Summary

生成：

```text
research/results/BATCH_02_EVIDENCE_INFORMED_VALIDATION.md
```

统一表：

| Track           | Evidence Tier | Research Action    | Local Question              | Decision |
| --------------- | ------------- | ------------------ | --------------------------- | -------- |
| S27A Robustness | E3            | LOCAL_ADJUDICATION | sizing 是否稳定                 |          |
| S4B ERC         | E2            | UPSTREAM_COMPARE   | correlation-aware ERC 是否有增量 |          |
| S10A Vol Target | E3            | LOCAL_ADJUDICATION | 无杠杆 ETF vol timing 是否有效     |          |

性能表至少：

| Strategy | CAGR | MaxDD | Sharpe | Calmar | Turnover | Decision |
| -------- | ---: | ----: | -----: | -----: | -------: | -------- |

不要做：

```text
overall strategy score
```

---

# 50. Cross-Track Questions

Batch summary 必须回答：

```text
1. Did S27A survive parameter,
   period and cost robustness?

2. Is S27A's inverse-vol improvement
   structural or narrow?

3. Did correlation-aware ERC improve
   on simple inverse-vol?

4. Did ERC justify its additional
   optimizer dependency?

5. Did unlevered volatility targeting
   add value after controlling
   monthly rebalance mechanics?

6. Did volatility targeting merely
   lower average risk exposure?

7. How do surviving dynamic strategies
   compare contextually with S30?

8. Which external claims transferred
   successfully?

9. Which did not?

10. What remains local and unproven?
```

---

# 51. Research Ledger

追加独立 local questions：

建议：

```text
RL-025 S27A Robustness

RL-026 S4B ERC ETF Transfer

RL-027 S10A Volatility Targeting Adjudication
```

实际编号以最新 ledger 为准。

只记录：

```text
question
external mapping
external tier
local gap
frozen protocol
decision
evidence
reopen condition
```

不要复制整篇文献综述。

---

# 52. External Registry After Results

结果完成后更新相关 entry 的：

```text
local_mapping
local_status
local_evidence_refs
remaining_gap
```

不得根据本地结果改变：

```text
external evidence tier
external consensus
```

除非本 Goal 的外部文献审计本身发现新的外部证据。

---

# 53. Strategy Research Map

更新：

```text
docs/STRATEGY_RESEARCH_MAP.md
```

反映：

```text
S27A robustness result

S4B local mapping/result

S10A local mapping/result
```

继续严格区分：

```text
external evidence
vs
local evidence
```

---

# 54. STRATEGY_CATALOG

更新：

```text
docs/STRATEGY_CATALOG.md
```

只记录本地生命周期。

例如：

```text
S27A:
baseline → robustness result

S4B:
ERC transfer baseline → result

S10A:
vol-target adjudication → result
```

不要把 external literature 全部塞进 catalog。

---

# 55. CURRENT_STATE

完成 Batch 02 后只保留当前前沿。

如果某些 track advance：

写：

```text
which tracks earned next-stage eligibility
```

如果全部 fail：

如实关闭。

最终状态必须：

```text
BATCH_02_COMPLETE
AWAIT_BATCH_02_ARCHITECT_REVIEW
```

不得自动开始下一阶段。

---

# 56. ARCHITECTURE / RESEARCH_RULES / AGENTS

正常：

```text
UNCHANGED
```

因为 Batch 00 已经完成永久规则升级。

不要把：

```text
ERC 60 days
S10 target vol 10%
S27 parameter neighborhood
```

写进永久规则。

这些属于 strategy-specific protocol。

---

# 57. docs/goal.md

用本 Goal 替换完成的 Batch 00 Goal。

结束写：

```text
Status: completed

Batch:
BATCH_02_EVIDENCE_INFORMED_VALIDATION

Starting HEAD:
...

Protocol Freeze SHA:
...

Results SHA:
...

S27A:
...

S4B:
...

S10A:
...

Next:
AWAIT_BATCH_02_ARCHITECT_REVIEW
```

---

# 58. S2 Final Integrity Gate

所有实验和文档完成后再次：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须：

```text
PASS
```

否则：

```text
BATCH_02_INVALID
```

不得更新 S2 manifest。

---

# 59. Full Validation

执行：

```bash
uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

如果新增 research dependency：

同时从 clean sync 验证：

```bash
uv sync --extra dev --extra research
```

---

# 60. Architecture Drift Audit

最终逐项回答：

```text
Did we modify S2 R1?

Did we reopen rejected S3/S4A/S8A?

Did we tune old failed strategies?

Did we run a Cartesian parameter search?

Did we pick best S27 parameters?

Did we write our own ERC solver?

Did we confuse Riskfolio implementation
with economic evidence?

Did we ignore contradictory
volatility-management evidence?

Did we add leverage?

Did we run RQAlpha?

Did we start MinVar/HRP/Theme?

Did one track's performance alter
another frozen track?

Did we change external tiers
because of local performance?

Did we add generic research infrastructure?
```

正常全部：

```text
NO
```

---

# 61. Commit B

完成结果、文档和 validation 后：

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
evaluate batch 2 evidence informed strategy gaps
```

push。

---

# 62. Final User Report

最终必须报告：

```text
Starting HEAD
Protocol Freeze SHA
Results SHA
Ending HEAD

S2 verification before/after

External sources added/updated

Riskfolio version
Riskfolio API used

S27A:
baseline reproduction
trend neighborhood
vol neighborhood
fixed periods
rolling 3Y/5Y
cost sensitivity
decision

S4B:
coverage
ERC metrics
inverse-vol comparator
equal-weight comparator
concentration
turnover
decision

S10A:
average scale
months scaled down
CAGR
MaxDD
Sharpe
Calmar
monthly-static comparator
annual S30 context
decision
```

---

# 63. Mandatory Stop

完成 Batch 02 后：

```text
STOP
```

禁止自动：

```text
run S27 RQAlpha
run ERC robustness
run vol-target robustness

implement MinVar
implement HRP
implement Theme Rotation

start Batch 03
```

等待 Principal Review。

---

# 64. Final Principle

```text
External evidence tells us
which question is worth asking.

It does not answer
the TactiCore local question.

S27A earned robustness.
Test robustness.

ERC is established.
Reuse upstream and test transfer.

Volatility targeting is contested.
Adjudicate locally.

Do not invent canonical methods.

Do not optimize rejected ideas.

Do not let one historical result
rewrite another experiment.

One frozen batch.
Three orthogonal gaps.
Then stop and review.

Literature first.
Upstream first.
Local evidence next.
Prospective evidence later.
Infrastructure last.
```

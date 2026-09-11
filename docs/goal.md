# Goal: S2 Multi-Asset Trend Following — Baseline Economic Screen V1

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Quant Systems Architect
+
Research Correctness Reviewer
```

---

# 0. Why This Goal Exists

TactiCore has completed the full evidence closure for:

```text
S1 Global Dual Momentum
```

The repository decision is:

```text
REJECT_S1
```

Do NOT reopen S1 parameter research.

Do NOT attempt to rescue S1 by:

```text
changing lookback
changing top_k
changing fallback
adding volatility filters
adding regime filters
adding extra indicators
```

S1 should remain a frozen rejected research artifact.

The next research direction is:

```text
S2 Multi-Asset Trend Following
```

This Goal exists to answer one question:

> Does a simple diversified multi-asset time-series trend strategy show enough economic value to justify deeper validation?

The Goal is NOT to build the complete S2 system.

It is an:

```text
Economic Screen
```

At the end of this Goal there must be exactly one decision:

```text
CONTINUE_S2
or
REJECT_S2
```

---

# 1. Repository-First Audit

Before making any change:

```bash
git status
git log --oneline -10
```

Read actual latest:

```text
README.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md

config/universe.csv
config/strategy.toml

tacticore/data/
tacticore/strategies/
tacticore/engines/

research/experiments/
research/results/

tests/
```

Record:

```text
HEAD SHA
latest commits
current S1 decision
current data snapshot
current VectorBT path
current RQAlpha path
```

Repository is source of truth.

Do not implement based only on this prompt.

---

# 2. First Fix One Known Documentation Drift

Current repository evidence indicates:

```text
docs/CURRENT_STATE.md:
S1 = REJECT_S1
S2 = next direction
RQAlpha bundle validation = completed
```

but `docs/ARCHITECTURE.md` may still contain a stale final "当前重点" section describing:

```text
continue S1 rolling/OOS/cost validation
RQAlpha bundle still blocked
```

Verify this against latest main.

If still stale:

fix it immediately.

Do NOT redesign the architecture.

This is documentation correctness only.

After correction, architecture should consistently state:

```text
S1
REJECTED / frozen

S2
current research direction

RQAlpha
official bundle path proven operational
```

---

# 3. Permanent Framework-First Rule

Before writing ANY implementation, reread:

```text
docs/RESEARCH_RULES.md
docs/ARCHITECTURE.md
```

The following is a HARD architecture invariant:

> TactiCore owns strategy hypotheses and target allocation logic.
> VectorBT and RQAlpha own generic quantitative infrastructure.

Before implementing anything involving:

```text
portfolio simulation
returns
drawdown
orders
trades
cash
positions
fees
slippage
matching
execution
transaction cost
benchmark portfolio
portfolio value
performance statistics
corporate actions
trading calendar
```

FIRST inspect:

```text
VectorBT native APIs
RQAlpha native APIs
existing TactiCore thin adapters
```

Decision order:

```text
1. framework native API
2. documented framework extension point
3. existing TactiCore thin adapter
4. smallest possible local implementation
```

A duplicate implementation is architecture drift.

---

# 3.1 Specifically For This Goal

Prefer VectorBT native:

```text
Portfolio.from_orders
Portfolio.value
returns accessor
drawdown records
orders records
trades records
stats where semantics match
fees
slippage
targetpercent
```

Do not create:

```text
custom portfolio simulator
custom drawdown calculator
custom turnover engine if existing records suffice
custom cost simulator
custom trade ledger
```

If existing TactiCore S1 evidence code contains useful bounded helpers:

reuse them where economically identical.

Now that S1 and S2 are two concrete research use cases, a VERY SMALL common extraction is allowed if it genuinely removes duplicated research plumbing.

But do NOT build:

```text
generic experiment framework
strategy plugin system
generic analytics framework
universal benchmark engine
```

Rule of 2 does not mean "build a platform".

It means only:

> extract the smallest common function when two actual callers already need exactly the same behavior.

---

# 4. S2 Economic Hypothesis

S1 used:

```text
absolute momentum filter
+
cross-sectional relative ranking
+
Top-2 concentration
```

and failed partly because the portfolio could remain concentrated in highly correlated assets during a large market reversal.

S2 tests a different hypothesis:

> Medium/long-term trends persist enough that independently filtering each asset by its own trend can reduce large drawdowns while preserving meaningful participation in rising markets.

S2 must NOT use:

```text
cross-sectional ranking
top-k selection
winner picking
```

Each asset is evaluated independently.

This is:

```text
time-series trend following
```

not:

```text
cross-sectional momentum
```

---

# 5. Freeze A Single Transparent S2 Baseline

Do NOT parameter mine.

Create one explicit baseline.

Recommended baseline:

```text
signal:
month-end adjusted close > 200-trading-day moving average

rebalance:
monthly

execution:
next trading day

risk universe:
reuse the existing S1 risk assets unless repository evidence gives a concrete reason otherwise

defensive asset:
reuse the existing defensive bond ETF
```

Do not introduce a new universe merely to improve results.

---

# 5.1 Sleeve Allocation Semantics

This part must be explicit.

At every signal date:

1. determine which risk assets have enough valid history to calculate the 200-day moving average;
2. those assets form the currently eligible universe;
3. every eligible asset owns one equal capital sleeve:

```text
sleeve_weight = 1 / eligible_asset_count
```

4. if an asset is above its moving average:

```text
its sleeve → that asset
```

5. if below its moving average:

```text
its sleeve → defensive asset
```

Example:

```text
4 eligible assets

A uptrend
B uptrend
C downtrend
D downtrend

Target:

A          25%
B          25%
Defensive  50%
```

NOT:

```text
A 50%
B 50%
```

and NOT:

```text
rank A/B and choose the strongest
```

If all eligible assets are below trend:

```text
100% defensive
```

If all are above trend:

```text
equal-weight all eligible assets
```

Assets without enough history:

```text
not eligible
```

Do not classify missing trend as negative trend.

Do not fill missing data with zero.

---

# 5.2 Why This Exact Baseline

The baseline deliberately isolates ONE economic idea:

```text
independent trend filter
```

It does NOT combine:

```text
inverse volatility weighting
risk parity
volatility targeting
dynamic leverage
macro regime
relative momentum
breadth
fund flow
valuation
machine learning
```

Those may become future hypotheses ONLY if the simple trend baseline first demonstrates economic value.

---

# 6. Configuration

Add a simple explicit section such as:

```toml
[multi_asset_trend]
trend_window = 200
rebalance_frequency = "monthly"
fallback_symbol = "..."
fees = ...
slippage = ...
initial_cash = ...
risk_symbols = [...]
```

Reuse existing values where appropriate.

Do NOT create a configuration framework.

Do NOT create a strategy registry.

---

# 7. Strategy Implementation

Add the smallest clear strategy module, for example:

```text
tacticore/strategies/multi_asset_trend.py
```

Responsibilities limited to:

```text
calculate trend eligibility
calculate trend state
build month-end target weights
shift targets to next trading day
```

It must NOT contain:

```text
portfolio accounting
returns calculation
trade simulation
fee calculation
slippage calculation
drawdown logic
```

Those belong to VectorBT/RQAlpha.

---

# 8. VectorBT Integration

Use existing VectorBT infrastructure.

Inspect the current `vectorbt_adapter.py`.

If it is unnecessarily tied to `GlobalDualMomentumConfig`, do not duplicate the whole adapter for S2.

Because there are now two concrete strategies, it is acceptable to minimally extract something equivalent to:

```text
run_target_weights(
    prices,
    execution_weights,
    fees,
    slippage,
    initial_cash,
    ...
)
```

ONLY if needed.

The common adapter should remain thin and directly delegate portfolio behavior to:

```text
vectorbt.Portfolio.from_orders(...)
```

Do NOT move strategy logic into the adapter.

Do NOT make a general strategy engine.

S1 must continue reproducing its frozen historical outputs after any refactor.

---

# 9. Do Not Implement RQAlpha S2 Yet

This is important.

VectorBT's job is:

```text
fast economic screening
```

RQAlpha's job is:

```text
authoritative validation of strategies worth validating
```

Therefore:

> Do not implement S2 RQAlpha callbacks in this Goal unless they already work almost trivially through an existing strategy-independent adapter.

Do not spend infrastructure work validating a strategy that may fail its first economic screen.

If S2 ends:

```text
CONTINUE_S2
```

then the NEXT Goal can perform RQAlpha differential validation.

If S2 ends:

```text
REJECT_S2
```

no RQAlpha implementation effort should have been wasted.

This separation is intentional architecture.

---

# 10. Baseline Benchmark Comparison

Use the same relevant simple benchmarks already established for S1 wherever economically comparable.

At minimum compare S2 against:

```text
S1 rejected baseline
B1 沪深300 buy-and-hold
B2 美国宽基 buy-and-hold
B3 current-risk-assets static equal weight
B4 simple 60/20/20 equity-bond-gold allocation
```

Do NOT recreate benchmark logic if current evidence code already provides it.

Reuse existing VectorBT-native portfolio construction.

Use matched evaluation intervals when required by listing dates.

Never backfill instruments before listing.

---

# 11. Core Metrics

At minimum report:

```text
CAGR
Max Drawdown
Sharpe
Calmar
Worst Year
Turnover
Trade Count
Average Holding Period
```

Prefer framework-native metrics and records where semantics match.

If an existing bounded local metric is retained:

document why.

Do not build a generic metric library.

---

# 12. Primary Question: Did Trend Filtering Improve The S1 Failure Mode?

S1's largest historical weakness was approximately:

```text
2015-06 → 2016-01

continued exposure to
510300 + 510500

high correlation
+
large joint decline
+
no defensive allocation
```

For S2 explicitly inspect this historical interval.

Answer:

```text
When did each China equity ETF fall below its trend?

When did S2 reduce exposure?

How much defensive allocation appeared?

What was S2 drawdown during the same episode?

Did trend following materially shorten or reduce the loss?
```

Use VectorBT records and target weights.

Do not implement a separate event simulator.

---

# 13. Temporal Robustness

A strategy that only fixes 2015 is not enough.

Evaluate the frozen 200-day S2 baseline over approximately:

```text
2013–2016
2017–2019
2020–2022
2023–2026
```

Use exact valid boundaries dictated by data.

Report:

```text
CAGR
MaxDD
Sharpe
Calmar
turnover
```

Also annual returns.

Do NOT optimize the trend window using these periods.

---

# 14. Rolling Stability

If existing S1 evidence code already has bounded rolling analysis that can be reused without building infrastructure, evaluate:

```text
rolling 3Y
rolling 5Y
```

At minimum:

```text
CAGR min / median / max
Sharpe min
worst rolling MaxDD
```

Use VectorBT returns accessors where available.

The question is:

> Does diversified trend following avoid long stretches of economically useless performance?

---

# 15. Cost Sensitivity

Because this is a low-frequency personal strategy, verify that it remains low maintenance.

Use VectorBT native:

```text
fees
slippage
```

No custom cost engine.

Test a small bounded set such as:

```text
15 bps baseline
30 bps
50 bps
```

Do not perform a giant grid.

Report whether transaction costs materially change the decision.

---

# 16. Turnover / User Effort Is A First-Class Metric

The user does not have time for frequent trading.

Explicitly report:

```text
annualized rebalance count
asset-level trade count
turnover
average holding period
months with no portfolio change
average number of changed positions per rebalance
maximum number of changed positions in one rebalance
```

Use framework order/trade/target records whenever available.

Do not create execution infrastructure.

Interpret results in human terms.

Example:

```text
Approximately X months per year require any action.
Typical rebalance changes Y instruments.
```

This matters as much as small CAGR differences.

---

# 17. Universe Bias

Do NOT build PIT ETF infrastructure.

Retain the existing honest status:

```text
BIAS_NOT_FULLY_RESOLVED
```

Reuse existing listing-date / availability logic.

Explain whether S2 benefits materially from late-added assets.

No historical ETF master database.

No survivorship platform.

---

# 18. No Parameter Sweep In This Goal

Do NOT search:

```text
100
120
150
180
190
200
210
220
250
...
```

for the best moving-average period.

The baseline is intentionally:

```text
200 trading days
```

or another single period only if repository evidence proves 200 is technically unsuitable.

Do not change it because the result is poor.

If S2 passes the economic screen:

a future Goal may examine a coarse robustness neighborhood such as:

```text
150 / 200 / 250
```

but not now.

---

# 19. Decision Gate

The Goal must end in exactly one decision.

## CONTINUE_S2

Choose this only if S2 shows a meaningful combination of:

```text
substantially better drawdown behavior than S1
+
competitive risk-adjusted performance against simple diversified benchmarks
+
positive long-run economic value
+
reasonable temporal stability
+
low enough turnover for the user's lifestyle
```

It does NOT need the highest CAGR.

For this project:

```text
9% CAGR / -18% DD
```

may be more valuable than:

```text
13% CAGR / -45% DD
```

---

## REJECT_S2

Choose this if evidence shows that:

```text
simple static diversification is as good or better
OR
trend filtering destroys too much return without enough drawdown benefit
OR
performance is strongly regime-dependent
OR
turnover is too high
OR
the strategy adds complexity without enough economic value
```

If rejected:

do NOT tune the MA until it works.

The next candidate would then be evaluated separately, potentially:

```text
S3 China Sector / Theme Rotation
```

or another economically distinct strategy approved by repository direction.

---

# 20. Very Important: Do Not Automatically Add Volatility Targeting

If the simple trend strategy produces:

```text
good return
but still excessive drawdown
```

do NOT immediately add:

```text
inverse-vol weighting
risk parity
volatility target
```

in this Goal.

Instead, if evidence strongly supports continuing S2:

record ONE potential next hypothesis.

Example:

```text
S2 baseline has persistent positive alpha/risk-adjusted value
but residual drawdown is driven by unequal asset volatility.

NEXT hypothesis:
volatility-aware sizing.
```

That becomes a future Goal.

Do not implement it now.

---

# 21. Required Research Artifact

Create a bounded report such as:

```text
research/results/S2_BASELINE_ECONOMIC_SCREEN_V1.md
```

and only a small number of useful machine-readable outputs, for example:

```text
s2_benchmark_comparison.csv
s2_period_performance.csv
s2_annual_returns.csv
s2_cost_sensitivity.csv
s2_rolling_performance.csv
```

Do not create dozens of:

```text
json manifests
status artifacts
promotion records
governance files
```

This is not DailyETF.

---

# 22. S1 Artifacts Are Frozen

Do not rewrite S1 research conclusions to make S2 look better.

S1 remains:

```text
REJECT_S1
```

Its evidence is historical research knowledge.

S2 should be compared to it, not overwrite it.

---

# 23. Documentation Must Be Updated After Implementation

Every Goal must refresh the user-facing understanding of the system.

At minimum review/update:

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
README.md
```

Only update `RESEARCH_RULES.md` if a genuinely new permanent rule is discovered.

Do not churn unchanged text.

---

# 23.1 CURRENT_STATE.md Must Explain

In plain language:

```text
What S2 is

How it differs from S1

Why it was chosen

What was implemented

What historical result it produced

How its drawdown compares with S1

How it compares with simple static portfolios

How often the user would actually need to trade

What remains uncertain

CONTINUE_S2 or REJECT_S2

What the next single direction is
```

The user should be able to read only this document and understand current project direction.

---

# 23.2 ARCHITECTURE.md Must Be Internally Consistent

Fix any stale S1 "current focus" text.

After this Goal, all roadmap/current-focus sections must agree.

No document may simultaneously claim:

```text
S1 rejected
```

and:

```text
current priority is further S1 validation
```

Add no architecture layers unless actually necessary.

---

# 24. Documentation Consistency Audit

Before final commit search the repository for stale statements such as:

```text
S1 next
S1 current focus
RQAlpha blocked
bundle missing
S2 future
```

and determine whether they are historical context or stale current-state statements.

Historical research documents may remain unchanged.

Current architecture/status documents must reflect reality.

Do not rewrite historical artifacts merely because their conclusion was true at an earlier commit.

---

# 25. Testing

Add only economically useful tests.

At minimum verify:

```text
trend uses only historical/current signal-date data
no same-close execution lookahead
200-day insufficient history → unavailable, not negative
positive-trend sleeve → risk asset
negative-trend sleeve → defensive asset
weights sum to 100%
all-negative → 100% defensive
all-positive → equal-weight eligible assets
mixed signals → inactive sleeves go to defensive
future-listed assets do not participate early
S1 outputs remain unchanged after any shared-adapter refactor
```

Do NOT create mock broker/accounting infrastructure.

---

# 26. Validation

Run actual repository checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Run the real S2 research script on frozen Tushare canonical data.

Do not report a command as successful if it was not executed.

GitHub currently may not have CI status checks configured.

Do NOT introduce a CI project in this Goal merely because of that.

Local verified tests are sufficient for this bounded research Goal.

---

# 27. Explicitly Out Of Scope

Do NOT implement:

```text
RQAlpha S2 integration unless already trivial through existing generic path

S3

volatility targeting
risk parity
inverse-vol weighting
macro regime
cross-sectional ranking
relative momentum
fund flows
valuation
breadth
machine learning
AI strategy search

new Tushare APIs without demonstrated need
new data provider
RQData integration

database
scheduler
dashboard
web UI
notification system
broker integration
VeighNa
live trading

generic research framework
generic benchmark framework
generic strategy base class
strategy registry
plugin system

new backtester
new accounting system
new execution simulator
new cost engine
```

---

# 28. Architecture Drift Audit

Before commit answer explicitly:

```text
Did we duplicate VectorBT functionality?

Did we duplicate RQAlpha functionality?

Did we write generic infrastructure without a concrete S2 blocker?

Did we create a strategy framework instead of one strategy?

Did we introduce a new data abstraction unnecessarily?

Did S1 results change unintentionally?

Did infrastructure complexity grow more than research capability?
```

Any unjustified YES must be simplified before commit.

---

# 29. Success Criterion

This Goal is successful even if:

```text
REJECT_S2
```

A failed strategy with a clear reason is useful research.

Success means:

> We learned whether simple diversified multi-asset trend following deserves more work.

Success does NOT mean:

```text
S2 achieved 10% CAGR
```

and it does NOT mean:

```text
more code exists
```

---

# 30. Final Report Required Format

Final response must contain:

```text
1. Executive Summary

2. Repository State
   - baseline HEAD
   - final HEAD
   - changed files

3. Documentation Drift Fixed

4. S2 Economic Hypothesis

5. Exact S2 Baseline Rules

6. Framework Reuse Audit
   - VectorBT native capabilities used
   - existing TactiCore code reused
   - local code added and why

7. Full-Sample Results

8. Benchmark Comparison

9. 2015–2016 S1 Failure-Mode Comparison

10. Temporal / Rolling Robustness

11. Cost Sensitivity

12. User Trading Effort
    - how often action is actually required

13. Universe Bias Status

14. S2 Decision
    exactly one:
    CONTINUE_S2
    REJECT_S2

15. Why The Evidence Supports This Decision

16. What This Goal Does NOT Prove

17. Architecture Drift Audit

18. Documentation Updated

19. Tests / Verification

20. Next ONE Recommended Goal

21. Git State
    - commit SHA
    - branch
    - push status
```

---

# 31. User-Facing Explanation Requirement

Do not finish with only engineering information.

Explain concretely:

> Compared with S1, what changed in portfolio behavior?

For example:

```text
S1:
select two strongest assets
→ can concentrate in correlated winners

S2:
give every available asset an independent sleeve
→ positive trend holds asset
→ negative trend sends sleeve to defensive asset
```

Explain the historical effect in numbers.

Also explain:

```text
If I actually followed this strategy,
roughly how often would I need to touch my portfolio?
```

This is a first-class project requirement.

---

# 32. Git Requirement

After all work and validation:

```bash
git status
git diff
```

Confirm no:

```text
TUSHARE_TOKEN
secret
RQAlpha bundle
cache
temporary files
unexpected large data
```

Then:

```bash
git add
git commit
git push
```

Suggested commit message:

```text
screen diversified multi-asset trend baseline
```

---

# 33. Final Principle

Remember throughout this Goal:

```text
TactiCore owns strategy research.

VectorBT owns fast portfolio research infrastructure.

RQAlpha owns authoritative trading infrastructure.

Tushare Pro supplies strategy-demanded market data.

Do not make TactiCore compete with any of them.
```

And:

```text
One strategy hypothesis
→ one bounded experiment
→ one evidence-based decision
→ stop.
```

Begin from the latest `main`.

# Goal: S1 Evidence Closure V1 — Decide Whether Global Dual Momentum Deserves Further Research

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

# 0. Repository-First Rule

Before modifying anything:

1. fetch / inspect latest `main`;
2. record current HEAD SHA;
3. inspect at least latest 10 commits, or all commits if fewer than 10;
4. read first:

```text
README.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md
config/universe.csv
config/strategy.toml
```

5. inspect actual implementations for:

```text
tacticore/data/
tacticore/strategies/
tacticore/engines/
research/experiments/
research/results/
tests/
```

Do not reason from this Goal Prompt alone.

Repository is the source of truth.

If latest `main` contradicts any assumption below:

```text
follow repository evidence
```

and document the discrepancy.

---

# 1. Why This Work Exists

TactiCore already has:

```text
Tushare Pro real market data
+
canonical adjusted ETF price dataset
+
Global Dual Momentum baseline
+
VectorBT research path
+
RQAlpha validation path skeleton
```

Current historical S1 evidence is approximately:

```text
252-day baseline

CAGR            ~8.32%
Max Drawdown    ~-46.81%
Sharpe          ~0.491
Calmar          ~0.178
```

and preliminary lookback checks around:

```text
80 / 120 / 160 / 252 trading days
```

do not suggest that the weakness is caused by one isolated bad lookback choice.

The primary unresolved question is therefore NOT:

```text
How can we add more strategy features?
```

It is:

> Does Global Dual Momentum provide enough robust economic value, relative to simple alternatives, to justify another round of strategy research?

This Goal must end with a research decision.

It must NOT end merely with:

```text
more infrastructure completed
```

---

# 2. Project Mission Must Remain Unchanged

TactiCore is:

```text
Low-Frequency Multi-Asset Tactical Allocation Research System
```

Its purpose is:

> Discover robust, explainable, executable low-frequency allocation strategies for a user who does not have time for frequent trading.

Default preferences remain:

```text
signal calculation:
daily if useful

normal rebalance:
weekly / biweekly / monthly

actual portfolio changes:
preferably low frequency

holding horizon:
weeks to months
```

The system is NOT intended to become:

```text
generic quant platform
generic backtest framework
high-frequency trading system
data engineering platform
experiment-governance platform
```

---

# 3. NEW PERMANENT ARCHITECTURE RULE:

# USE FRAMEWORK INFRASTRUCTURE BEFORE WRITING OUR OWN

This rule must be added to BOTH:

```text
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
```

and treated as a permanent invariant for all future Goals.

## 3.1 Core Rule

Before implementing any capability related to:

```text
backtesting
portfolio accounting
order generation
order simulation
matching
cash accounting
positions
transaction costs
slippage
corporate actions
trading calendar
suspensions
price adjustment
performance statistics
drawdown
returns
trade records
position records
benchmark analysis
portfolio value
execution sequencing
rebalance simulation
```

you MUST first inspect whether:

```text
RQAlpha
or
VectorBT
```

already provides the capability.

If it exists:

```text
USE THE EXISTING FRAMEWORK CAPABILITY
```

Do NOT reimplement it.

---

# 3.2 Explicitly Forbidden Duplication

Do not create TactiCore-specific replacements for existing framework functionality such as:

```text
custom backtest loop
custom trade matcher
custom broker simulator
custom cash ledger
custom position accounting
custom corporate-action engine
custom commission engine
custom slippage engine
custom drawdown engine
custom generic performance analytics framework
custom generic portfolio simulator
custom generic order lifecycle
```

unless a concrete strategy requirement proves that neither RQAlpha nor VectorBT can satisfy it.

---

# 3.3 Required Decision Process

Whenever implementation appears to require new infrastructure:

FIRST answer:

```text
1. Does VectorBT already implement this?
2. Does RQAlpha already implement this?
3. Can an existing public API or documented extension mechanism solve it?
4. Can the strategy be expressed differently to use existing infrastructure?
```

Only if all applicable answers are NO may TactiCore add custom implementation.

Even then:

```text
document the exact blocker
+
implement the smallest possible extension
```

Do not generalize it prematurely.

---

# 3.4 Framework Extension Is Different From Framework Reimplementation

Allowed:

```text
thin adapter
configuration
framework callback
RQAlpha Mod
RQAlpha DataSource extension
VectorBT-native parameterization
small conversion layer
```

Not allowed:

```text
copying framework functionality into tacticore/
```

If RQAlpha provides an official extension point, prefer that extension point.

For example:

```text
AbstractDataSource
BaseDataSource
Mod
scheduler
order_target_percent
history_bars
sys_analyser
sys_simulation
sys_transaction_cost
```

should be preferred over recreating equivalent behavior.

Likewise VectorBT native functionality should be preferred for:

```text
Portfolio
orders
trades
returns
drawdowns
stats
fees
slippage
target-percent allocation
parameterized research
```

where appropriate.

---

# 3.5 Local Metrics Rule

Existing TactiCore code currently calculates some research metrics locally.

Do NOT blindly rewrite them during this Goal.

Instead audit:

```text
which metrics are already directly and reliably provided by VectorBT
```

If a metric is duplicated only because of historical implementation convenience:

prefer migrating toward VectorBT's native statistic where semantics match.

However:

```text
do not perform unrelated refactoring
```

during this Goal.

Record duplication as technical debt if replacing it is not needed for S1 evidence closure.

The priority remains strategy evidence.

---

# 4. Primary Objective — ONE ONLY

Complete:

```text
S1 Evidence Closure V1
```

The Goal must answer:

> Should Global Dual Momentum be CONTINUED, REVISED once for a clearly justified economic reason, or REJECTED?

Allowed terminal decisions:

```text
CONTINUE_S1
REVISE_S1
REJECT_S1
```

There must be exactly one final research decision.

---

# 5. Current Strategy Must Stay Frozen During Evaluation

Do NOT improve the strategy before evaluating it.

Current S1 baseline is expected to remain approximately:

```text
absolute momentum:
252 trading-day return > 0

relative momentum:
rank eligible risk assets

allocation:
top 2 equally weighted

fallback:
defensive bond ETF when no risk asset qualifies

rebalance:
monthly

signal:
month-end close

execution:
next trading day
```

Verify actual repository implementation first.

Do not change:

```text
lookback
top_k
absolute threshold
fallback
rebalance frequency
```

to make results prettier.

This Goal evaluates the existing strategy.

---

# 6. Workstream A — Add Proper Benchmarks

Current CAGR is meaningless without comparison.

Implement the smallest useful set of benchmarks using existing VectorBT functionality wherever possible.

At minimum compare S1 against:

### B1 — China Equity Buy & Hold

Example:

```text
510300 / CSI300 ETF proxy
```

### B2 — US Equity Buy & Hold

Use the existing canonical US broad-market instrument if appropriate.

### B3 — Equal-Weight Risk Assets

Static equal-weight portfolio over eligible risk assets.

Handle listing availability honestly.

Do not backfill nonexistent assets.

### B4 — Simple Diversified Static Allocation

Use a simple diversified benchmark involving:

```text
equity
+
bond
+
gold
```

No tactical signal.

Rebalance no more frequently than annual or quarterly.

Keep it intentionally simple.

---

# 6.1 Benchmark Requirements

For every benchmark report at least:

```text
CAGR
Max Drawdown
Sharpe
Calmar
Worst Year
Turnover
```

Use the same evaluation period where economically meaningful.

If a benchmark cannot exist over the entire period because of instrument listing dates:

state this clearly.

Do not fabricate history.

---

# 7. Workstream B — Temporal Robustness

Do NOT optimize parameters.

Keep S1 parameters fixed.

Evaluate performance across time.

At minimum produce calendar subperiod analysis approximately like:

```text
2013–2016
2017–2019
2020–2022
2023–2026
```

Adjust exact boundaries only if required by actual data availability.

For each period report:

```text
CAGR
Max Drawdown
Sharpe
Calmar
Turnover
```

Also report:

```text
best calendar year
worst calendar year
annual-return table
```

---

# 7.1 Rolling Robustness

Add:

```text
rolling 3-year
rolling 5-year
```

performance analysis.

Focus on:

```text
rolling CAGR
rolling Max Drawdown if practical using framework-native functionality
rolling Sharpe
```

Do not create a generic rolling analytics framework.

Use VectorBT / pandas only as necessary for this exact analysis.

The goal is to answer:

> Is performance reasonably persistent across time, or concentrated in a few regimes?

---

# 8. Workstream C — Cost Sensitivity

Use existing VectorBT transaction-cost/slippage infrastructure.

Do NOT implement a custom cost engine.

Test a bounded range.

For example, total per-side implementation assumptions approximately:

```text
5 bps
15 bps
30 bps
50 bps
```

or an equivalent clearly documented combination of:

```text
fees + slippage
```

Use existing framework parameters.

Report:

```text
CAGR
MaxDD
Sharpe
Calmar
turnover
```

for each cost assumption.

Primary question:

> Does S1 remain economically meaningful under materially worse execution costs?

---

# 9. Workstream D — Universe / Selection Bias Audit

This is NOT permission to build a historical ETF database.

Do not create:

```text
survivorship database
historical constituent platform
point-in-time ETF master
generic universe engine
```

Instead perform a bounded audit using existing repository data and Tushare Pro where necessary.

Current universe has instruments with different listing dates.

For every asset report at least:

```text
symbol
asset class
listing date
first usable signal date
historical availability
```

Then analyze:

```text
how many eligible strategy assets existed at each major historical period
```

For example:

```text
2013
2015
2018
2020
2023
2026
```

or annual counts.

---

# 9.1 Bias Questions

Explicitly answer:

1. Did the strategy operate on a materially smaller universe in early history?
2. Which important assets entered only later?
3. Could today's selected ETF universe introduce hindsight selection?
4. Are any current results likely to be inflated by survivorship or ex-post universe construction?
5. Does the strategy still look interesting after acknowledging this limitation?

Do NOT claim to have solved survivorship bias unless you truly have PIT universe data.

Expected status may remain:

```text
BIAS_NOT_FULLY_RESOLVED
```

That is acceptable.

The goal is honest decision-making, not perfect infrastructure.

---

# 10. Workstream E — Inspect the Drawdown Mechanism

Current MaxDD around:

```text
-47%
```

is the major practical weakness.

Do NOT modify the strategy yet.

Instead identify:

```text
largest drawdown period
assets held during drawdown
major allocation transitions
whether drawdown came from:
    concentrated risk allocation
    momentum lag
    asset correlation convergence
    lack of defensive allocation
    execution behavior
    data artifact
```

Use existing VectorBT portfolio/trade/order records whenever possible.

Do not build a custom portfolio event tracker if framework data already exposes the information.

---

# 10.1 Explicitly Investigate Partial Top-K Behavior

Current strategy logic may behave as follows:

```text
top_k = 2
```

but if only one asset has positive momentum:

```text
100% allocated to that one risk asset
```

instead of:

```text
50% risk asset
50% defensive asset
```

Verify actual current behavior from repository code.

Do NOT change it in this Goal.

Measure:

```text
how often this occurred
which periods
whether major drawdowns overlap with this behavior
```

This is hypothesis generation only.

If this mechanism clearly matters, it may justify:

```text
REVISE_S1
```

for the NEXT Goal.

---

# 11. Workstream F — Actually Attempt RQAlpha Validation

The previous state treated missing:

```text
~/.rqalpha
```

bundle as an external blocker.

Do not leave this unchallenged.

First inspect the installed/current RQAlpha version and its documented bundle workflow.

Prefer official framework mechanisms.

Attempt, where environment/network allows:

```bash
rqalpha download-bundle
```

or the equivalent current command.

Do NOT require RQData unless actually necessary.

---

# 11.1 Important RQAlpha Rule

RQAlpha already has infrastructure for:

```text
bundle data
trading calendar
instruments
events
orders
positions
cash
commission
slippage
corporate actions
```

Do NOT recreate these using Tushare.

Use official RQAlpha infrastructure whenever possible.

---

# 11.2 If Official Bundle Is Sufficient

Run S1 through current RQAlpha path.

Compare with VectorBT:

```text
rebalance dates
selected symbols
target weights
order directions
portfolio return
turnover
cost effects
```

Bit-for-bit equality is NOT required.

Explain differences.

---

# 11.3 Adjustment Semantics

Current Tushare / VectorBT research uses:

```text
post-adjusted fund prices
```

RQAlpha may default to another adjustment convention.

Do not rely on implicit defaults.

Inspect and explicitly set / document:

```text
adjust_type
```

where appropriate.

Determine whether momentum comparisons are economically equivalent.

Do not write a new adjustment engine.

---

# 11.4 If Official Bundle Is Insufficient

Only after proving that the bundle cannot provide required ETF history:

inspect RQAlpha's official DataSource / Mod extension mechanism.

RQAlpha documentation supports external/custom data sources.

If necessary, implement ONLY the minimum adapter required to let RQAlpha consume the already-existing Tushare canonical data.

Prefer:

```text
RQAlpha DataSource extension
```

over:

```text
rewriting RQAlpha market infrastructure
```

The custom layer must NOT implement:

```text
cash
orders
matching
corporate actions
commission
portfolio accounting
```

Those remain RQAlpha responsibilities.

If even this would materially expand scope:

stop and document the blocker instead.

---

# 12. Workstream G — Pseudo-OOS / Chronological Holdout

Do not call historical slices truly untouched OOS if the full history has already been inspected.

Use honest terminology:

```text
chronological holdout
or
pseudo-OOS
```

Choose a meaningful late period, for example:

```text
2023–2026
```

while keeping parameters frozen.

Report whether S1 continues to exhibit:

```text
positive return
reasonable relative performance
acceptable turnover
```

Do not optimize using this period.

---

# 13. Do NOT Build Prospective Infrastructure Yet

Do not recreate DailyETF's complex prospective evidence machinery.

If current evidence eventually supports continuing S1, a future Goal may add something as simple as:

```text
date
signal
target portfolio
actual next rebalance
```

for forward shadow tracking.

Not in this Goal.

---

# 14. Required Decision Framework

The final research artifact must end with exactly one of:

## CONTINUE_S1

Use only if evidence broadly shows:

```text
reasonable benchmark advantage
+
temporal robustness
+
cost robustness
+
RQAlpha does not invalidate core behavior
+
drawdown is not obviously fatal
```

This does NOT mean production-ready.

It means:

```text
S1 deserves another research iteration
```

---

## REVISE_S1

Use if:

```text
there is meaningful evidence of value
BUT
one clear and economically explainable weakness dominates
```

Examples:

```text
partial Top-K concentration
defensive allocation failure
clear trend lag mechanism
```

There must be ONE clearly justified revision hypothesis.

Do not output several simultaneous changes.

---

## REJECT_S1

Use if:

```text
simple benchmarks are as good or better
OR
performance is concentrated in a few periods
OR
costs remove the advantage
OR
RQAlpha materially contradicts VectorBT
OR
bias concerns make the claimed edge unreliable
```

If REJECT_S1:

recommend:

```text
S2 Multi-Asset Trend Following
```

as the next primary strategy direction.

Do not try to rescue S1 through parameter mining.

---

# 15. Required Research Artifacts

Create or update a small bounded set such as:

```text
research/results/
    S1_EVIDENCE_CLOSURE_V1.md
    s1_benchmark_comparison.csv
    s1_period_performance.csv
    s1_annual_returns.csv
    s1_rolling_performance.csv
    s1_cost_sensitivity.csv
    s1_universe_availability.csv
```

If RQAlpha succeeds:

```text
    s1_rqalpha_comparison.csv
```

Avoid proliferation of JSON/manifests unless an existing project convention genuinely requires them.

Do not recreate DailyETF artifact governance.

---

# 16. Documentation Requirement — MANDATORY

After implementation update:

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
README.md
```

where appropriate.

At minimum:

```text
CURRENT_STATE
ARCHITECTURE
RESEARCH_RULES
```

must be reviewed and updated if necessary.

---

# 16.1 ARCHITECTURE.md Must Add

A permanent section equivalent to:

```text
Framework-First Infrastructure Rule
```

Explain:

```text
VectorBT and RQAlpha are infrastructure dependencies,
not libraries to be wrapped and gradually replaced.

TactiCore owns strategy logic.
VectorBT/RQAlpha own generic quantitative infrastructure.

Before implementing generic infrastructure,
inspect framework-native capabilities first.
```

Include examples.

---

# 16.2 RESEARCH_RULES.md Must Add

Permanent rules equivalent to:

```text
Framework capability check is mandatory before custom implementation.

Duplicate framework functionality is considered architecture drift.

A thin adapter is acceptable.
A reimplementation is not.

Prefer framework public APIs and documented extension mechanisms.
```

---

# 17. Architecture Drift Audit — Mandatory

Before finalizing explicitly answer:

```text
Did we duplicate VectorBT functionality?

Did we duplicate RQAlpha functionality?

Did we write any generic infrastructure that an existing framework already provides?

Did we create abstractions without a concrete strategy need?

Did infrastructure LOC grow more than necessary for this research question?

Did this Goal materially improve our ability to decide whether S1 has value?
```

If the first four contain unjustified YES:

simplify before committing.

---

# 18. Tests

Tests must focus on economic correctness.

Cover where relevant:

```text
fixed strategy parameters remain unchanged
no lookahead
period slicing
benchmark construction
cost scenarios
universe availability
partial Top-K measurement
RQAlpha mapping
adjustment semantic configuration
```

Do NOT build large mock trading infrastructure.

Prefer framework tests / real framework behavior where practical.

Do not chase line coverage.

---

# 19. Validation Commands

Run actual project checks such as:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

and actual research scripts.

Run RQAlpha validation if its bundle becomes available.

Do not claim a test or backtest succeeded unless it actually ran.

Clearly report:

```text
passed
failed
skipped
blocked
```

---

# 20. Explicitly Out of Scope

Do NOT implement:

```text
S2 strategy
S3 strategy

new macro regime system
fund-flow strategy
valuation strategy
ML model
AI strategy generation

live trading
broker connection
VeighNa
notifications
dashboard
web UI

database
generic experiment framework
generic provider abstraction
generic strategy plugin system
generic portfolio engine

new backtest engine
new accounting engine
new matcher
new corporate-action engine
```

---

# 21. Stop Conditions

STOP when:

```text
benchmark comparison complete
temporal robustness complete
rolling analysis complete
cost sensitivity complete
universe bias audit complete
drawdown mechanism inspected
partial Top-K behavior quantified
RQAlpha validation attempted honestly
chronological holdout evaluated
final S1 decision produced
docs updated
tests complete
```

Do not start the next strategy.

---

# 22. Final Report Format

The final Codex response must contain:

```text
1. Executive Summary

2. Repository State
   - HEAD
   - relevant commits
   - files changed

3. What Was Implemented

4. Framework Reuse Audit
   - VectorBT capabilities reused
   - RQAlpha capabilities reused
   - custom code added and why it was unavoidable

5. Benchmark Comparison

6. Temporal Robustness

7. Rolling 3Y / 5Y Evidence

8. Cost Sensitivity

9. Universe / Selection Bias Audit

10. Drawdown Mechanism

11. Partial Top-K Concentration Analysis

12. RQAlpha Differential Validation
    or exact remaining blocker

13. Chronological Holdout

14. S1 Research Decision
    exactly one:
    CONTINUE_S1 / REVISE_S1 / REJECT_S1

15. Why This Decision Follows From Evidence

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

# 23. User-Facing Explanation Requirement

The final report must be understandable to the repository owner without reading code.

For every major change explain:

```text
What changed?

Why was it needed?

Did we use VectorBT/RQAlpha existing infrastructure?

What result did it produce?

What uncertainty remains?

How does this change our overall strategy direction?
```

Do not only provide:

```text
file list
test count
implementation details
```

The user must be able to understand whether the project is getting closer to a usable investment strategy.

---

# 24. Git Requirement

After all validation:

```bash
git status
git diff
```

Confirm no:

```text
token
secret
temporary file
unexpected large dataset
cache
RQAlpha bundle
```

is accidentally committed.

Then:

```bash
git add
git commit
git push
```

Use a commit message focused on research value, for example:

```text
close S1 robustness evidence and framework validation
```

---

# 25. Final Principle

Remember:

```text
TactiCore owns alpha research.

VectorBT owns fast portfolio research infrastructure.

RQAlpha owns event-driven trading infrastructure.

Do not make TactiCore compete with its dependencies.
```

The purpose of this Goal is not to make TactiCore more sophisticated.

The purpose is to make one high-value decision:

> Is Global Dual Momentum worth continuing?

Start from latest `main`.

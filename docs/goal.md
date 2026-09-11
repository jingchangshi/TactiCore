# Goal: S2 Decision Audit V2 — Correct Availability Semantics and Test Low-Touch Execution Before Abandoning Trend Following

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

Latest repository evidence currently records:

```text
S1 = REJECT_S1
S2 V1 = REJECT_S2
next candidate = S3
```

Do NOT blindly follow that conclusion.

This Goal is a bounded audit of whether the S2 V1 rejection is economically justified.

The previous S2 V1 produced approximately:

```text
Full sample:
CAGR       7.01%
MaxDD    -26.18%
Sharpe     0.726

Common equity/bond/gold interval:
CAGR       8.18%
MaxDD    -13.49%
Sharpe     0.857

Rolling 3Y CAGR minimum:
2.50%

Rolling 5Y CAGR minimum:
4.09%
```

These results are substantially stronger on drawdown and temporal stability than rejected S1.

However V1 was rejected mainly because:

```text
1. 2015 improvement was contaminated by missing-data availability semantics.

2. Exact monthly target-weight rebalancing generated user actions almost every month.
```

Neither issue necessarily disproves the underlying trend-following hypothesis.

Therefore this Goal asks:

> Was S2 genuinely economically unattractive, or was V1 rejected because of avoidable measurement/execution semantics?

This Goal must end with exactly one of:

```text
CONTINUE_S2_TO_RQALPHA
REJECT_S2_FINAL
```

Do NOT implement S3 during this Goal.

---

# 1. Repository-First Audit

Before modifying anything:

```bash
git status
git log --oneline -10
```

Read latest:

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
current HEAD
latest relevant commits
S1 frozen decision
S2 V1 frozen decision
current VectorBT adapter
current RQAlpha availability
current Tushare canonical data
```

Repository is source of truth.

Do not overwrite historical S1/S2 V1 research artifacts.

---

# 2. Preserve The Project Mission

TactiCore remains:

```text
Low-Frequency Multi-Asset Tactical Allocation Research System
```

Primary objective:

```text
robust
+
low drawdown
+
low maintenance
+
economically meaningful
```

NOT:

```text
maximum CAGR
maximum number of strategies
maximum infrastructure completeness
```

The intended user does not have time for frequent manual trading.

A strategy with:

```text
moderate CAGR
+
materially lower MaxDD
+
stable rolling behavior
+
few actual intervention dates
```

may be preferable to a higher-return strategy with much higher drawdown or maintenance burden.

---

# 3. HARD RULE: Framework First

Before implementing any generic functionality, inspect whether:

```text
VectorBT
RQAlpha
```

already provides it.

Decision order:

```text
framework native API
    ↓
framework documented extension point
    ↓
existing TactiCore thin adapter
    ↓
smallest unavoidable local implementation
```

Do NOT implement:

```text
custom backtester
custom portfolio accounting
custom broker
custom matcher
custom cost engine
custom drawdown engine
custom trade ledger
custom generic performance framework
```

Use VectorBT for:

```text
portfolio execution
target-percent orders
fees
slippage
portfolio value
orders
trades
drawdowns
returns
```

Use RQAlpha when authoritative event-driven validation becomes justified.

Do not make TactiCore compete with either framework.

---

# 4. Very Important: This Is NOT Parameter Optimization

Freeze:

```text
trend_window = 200 trading observations
```

Do NOT test:

```text
150 / 180 / 200 / 220 / 250
```

Do NOT change:

```text
asset universe
fallback asset
trend definition
monthly signal observation
```

to improve performance.

This Goal only tests two semantics:

```text
A. correct availability semantics

B. low-touch execution semantics
```

The economic hypothesis remains:

> Each asset is independently risk-on when above its own long-term trend and risk-off otherwise.

---

# 5. Workstream A — Audit The Existing Missing-Data Semantics

Inspect:

```text
tacticore/strategies/multi_asset_trend.py
```

Current implementation is expected to use something equivalent to:

```python
prices.rolling(trend_window, min_periods=trend_window).mean()
```

This means a single missing observation can make the trend unavailable until that NaN leaves the entire 200-row window.

Verify this from current code.

Do not assume this prompt is correct.

---

# 6. Investigate 510500.SS 2015 Missing Observations

The V1 report identifies approximately:

```text
2015-04-13
2015-04-14
```

as missing canonical observations for `510500.SS`.

Investigate these dates using existing evidence first:

```text
canonical data
Tushare provenance
Tushare Pro if token is available
RQAlpha official bundle if useful
```

The user has Tushare Pro.

Do NOT build a new data provider abstraction.

Answer:

```text
Were these exchange trading days?

Did Tushare fund_daily omit the observations?

Did fund_adj omit them?

Does RQAlpha have bars around these dates?

Is this likely suspension / no-trade data or provider incompleteness?

Why did two observations invalidate approximately 200 following rows?
```

If exact economic cause cannot be proven:

state:

```text
CAUSE_UNRESOLVED
```

Do not guess.

---

# 7. Correct Trend-Availability Semantics

The intended economic definition should be:

> A 200-observation moving average means the latest 200 valid historical price observations for that asset, not necessarily 200 globally consecutive dataframe rows.

Implement the smallest correction.

Requirements:

```text
signal-date asset price must exist

use only observations available on or before signal date

require 200 valid historical observations

internal isolated missing dates are not filled

no forward fill

no zero fill

no synthetic prices

no future observations
```

An isolated missing historical observation therefore should not automatically make the asset unavailable for the following 200 market-wide rows.

Conceptually:

```text
last 200 valid observations
→ moving average
```

rather than:

```text
last 200 global calendar rows must all be non-NaN
```

Use pandas/native operations where practical.

Do NOT build a data-imputation system.

---

# 8. Important Missing-Data Boundary

Do NOT silently convert:

```text
missing current signal-date price
```

into:

```text
negative trend
```

If the current decision-date observation itself is unavailable:

report the asset as:

```text
UNAVAILABLE
```

Likewise:

```text
insufficient 200 valid historical observations
→ UNAVAILABLE
```

Maintain the permanent rule:

```text
UNAVAILABLE != NEGATIVE_SIGNAL
```

---

# 9. Quantify The Semantic Correction

Run both:

```text
S2_V1_STRICT_CONSECUTIVE_ROWS
S2_V2_VALID_OBSERVATIONS
```

with the same:

```text
200 observation window
same universe
same costs
same rebalance calendar
same fallback
```

Compare:

```text
eligible asset counts
trend states
target weights
affected months
CAGR
MaxDD
Sharpe
Calmar
turnover
```

Especially inspect:

```text
2015–2016
```

and answer:

> After fixing availability semantics, how much of S2's drawdown improvement remains?

This is the first major decision point.

---

# 10. Workstream B — Distinguish Signal Changes From Mechanical Rebalancing

Current V1 evidence reports approximately:

```text
161 execution months

57 months:
target weights exactly unchanged

but VectorBT still generated mechanical rebalance orders
because the portfolio had drifted away from exact target percentages
```

Verify this from actual records.

This distinction is crucial:

```text
economic signal changed
!=
portfolio drift exists
```

For a low-maintenance personal strategy, mechanical monthly drift correction should not automatically count as a required human intervention.

---

# 11. Implement ONE Low-Touch Execution Variant

Do NOT create a generic execution-policy framework.

Implement one bounded candidate:

```text
SIGNAL_CHANGE_ONLY
```

Semantics:

At every month-end:

```text
compute trend state and target allocation
```

but emit a new target-percent order vector only when the strategy target has actually changed because of:

```text
trend-state change
availability change
universe eligibility change
```

If the target allocation is unchanged:

```text
NO ORDER
```

Do NOT rebalance merely because market movements have caused portfolio weights to drift.

Example:

```text
January target:
A 25%
B 25%
Bond 50%

February target:
A 25%
B 25%
Bond 50%

→ February: NO ACTION
```

Even if actual February holdings drifted to:

```text
A 27%
B 24%
Bond 49%
```

No mechanical correction occurs.

---

# 12. Do NOT Add A No-Trade Band Yet

Do NOT implement:

```text
±1%
±2%
±5% rebalance bands
```

in this Goal.

That would create another tunable parameter.

First test the cleaner economic rule:

```text
trade only when target state changes
```

If later necessary, tolerance bands can become a separate hypothesis.

---

# 13. Reuse VectorBT

Continue using:

```text
vbt.Portfolio.from_orders(...)
```

for actual portfolio simulation.

For unchanged signal months, pass:

```text
NaN / no order
```

or the correct VectorBT-native representation.

Do NOT manually simulate:

```text
cash
shares
portfolio drift
transactions
fees
```

VectorBT owns those behaviors.

---

# 14. Compare Three S2 States

Produce an explicit comparison of:

```text
S2_V1
strict 200 consecutive rows
+
exact monthly target rebalance

S2_V2A
200 valid observations
+
exact monthly target rebalance

S2_V2B
200 valid observations
+
signal-change-only execution
```

Purpose:

```text
V1 → V2A
isolates data availability semantics

V2A → V2B
isolates user-maintenance / execution policy
```

Do NOT introduce additional variants.

---

# 15. Benchmark Comparison

Reuse existing S1/S2 benchmark implementations where possible.

Do NOT duplicate them.

Compare the primary candidate:

```text
S2_V2B
```

against relevant existing benchmarks:

```text
S1 rejected baseline
S2 V1
沪深300 buy-and-hold
US broad-market buy-and-hold
static risk-asset equal weight
60/20/20 equity-bond-gold
```

Use matched intervals where necessary.

Do not backfill instruments before listing.

---

# 16. Temporal Robustness

Reuse existing bounded S2 V1 temporal analysis.

Do NOT create a new generic analysis framework.

Evaluate V2B over approximately:

```text
2013–2016
2017–2019
2020–2022
2023–2026
```

and rolling:

```text
3 year
5 year
```

Report:

```text
CAGR
MaxDD
Sharpe
Calmar
```

The key question:

> Did the promising temporal stability survive the corrected data semantics and low-touch execution policy?

---

# 17. User Maintenance Burden Must Be Re-Measured Correctly

For both:

```text
V2A exact monthly rebalance
V2B signal-change-only
```

report:

```text
months with any actual order
months with no action
annualized action months
asset-level orders
average changed instruments per action month
maximum changed instruments per action month
turnover
average holding period
```

Also report strategy-level signal changes separately:

```text
trend-state-change months
```

Do not conflate:

```text
signal change
mechanical portfolio rebalance
```

Translate the result into human terms.

Example:

```text
The strategy would have required intervention in
approximately X months per year,
with Y instruments changed in a typical intervention.
```

---

# 18. Revisit The Low-Frequency Requirement Carefully

Do NOT assume:

```text
one portfolio review per month
```

automatically violates the user's requirement.

The real requirement is:

```text
no high-frequency monitoring
no daily discretionary trading
manageable manual operations
```

A monthly review with occasional actual changes may be acceptable.

Therefore distinguish:

```text
signal evaluation frequency

scheduled review frequency

actual action frequency

number of changed instruments
```

The decision should be based on actual workload, not merely "12 scheduled month ends".

---

# 19. Cost Sensitivity

Use VectorBT-native:

```text
fees
slippage
```

Only if V2B remains economically interesting.

Reuse existing bounded scenarios:

```text
15 bps
30 bps
50 bps
```

No new cost engine.

No larger parameter grid.

---

# 20. RQAlpha Is NOT Yet The Main Workstream

RQAlpha official bundle has already been proven available by S1.

Do NOT build a new S2 RQAlpha adapter before V2B passes this corrected VectorBT screen.

However, it is acceptable to use existing RQAlpha data APIs for a small diagnostic check of:

```text
510500 historical bars around 2015-04-13/14
```

if this can be done without building new infrastructure.

If V2B ends with:

```text
CONTINUE_S2_TO_RQALPHA
```

then the NEXT Goal will be:

```text
S2 RQAlpha authoritative validation
```

Do not implement that next Goal now.

---

# 21. Decision Gate

End with exactly one decision.

## CONTINUE_S2_TO_RQALPHA

Choose this if the corrected V2B evidence shows:

```text
data-semantic correction does not destroy the risk-adjusted advantage

trend strategy still materially reduces large drawdowns

rolling behavior remains reasonably stable

static diversified benchmarks do not clearly dominate it

signal-change-only execution materially reduces manual workload

turnover remains acceptable

strategy remains simple and explainable
```

It does NOT need CAGR > 10%.

Remember:

```text
8–9% CAGR
+
~15% MaxDD
+
stable rolling returns
+
few interventions
```

may be much more valuable to this project than:

```text
12% CAGR
+
40% MaxDD
```

---

## REJECT_S2_FINAL

Choose this only if, after correcting those semantics:

```text
risk-adjusted advantage disappears
OR
drawdown benefit was largely a missing-data artifact
OR
low-touch execution destroys performance
OR
simple static diversified portfolios clearly dominate
OR
actual intervention burden remains unacceptable
```

If rejected:

freeze S2 permanently.

Only then recommend:

```text
S3 China Sector / Theme Rotation
```

as the next strategy research direction.

Do not tune the 200-day window to rescue it.

---

# 22. Do NOT Implement S3

Explicitly out of scope:

```text
China sector rotation implementation
theme rotation
industry universe expansion
fund flow
valuation
crowding
macro regime
relative strength ranking
new momentum model
```

The current Goal decides whether S2 was rejected correctly.

---

# 23. Do NOT Expand Infrastructure

Explicitly forbidden:

```text
new backtest engine
new portfolio simulator
new accounting
new broker simulator
new cost engine

generic strategy interface
strategy registry
plugin system

generic experiment framework
generic benchmark framework
generic reporting platform

database
scheduler
dashboard
web UI

new provider framework
PIT ETF database
```

---

# 24. Avoid Another Giant Duplicated Research Script

Current repository already has:

```text
run_s1_evidence_closure.py
run_s2_economic_screen.py
```

Do NOT copy another several-hundred-line experiment file wholesale.

Before implementing research calculations:

```text
inspect existing helpers
inspect VectorBT native APIs
reuse exact existing bounded functions where appropriate
```

If identical research logic is now used by multiple real experiments, a small shared helper extraction is allowed.

But the extraction must be:

```text
small
concrete
already needed by real callers
```

not a new research framework.

---

# 25. Permanent Documentation Cleanup

Review:

```text
docs/RESEARCH_RULES.md
```

The permanent rules currently may still contain S1-specific language such as:

```text
80/100/120/140/160 day momentum
252-day / Top-2 baseline
```

If still present:

remove strategy-specific future instructions from permanent rules.

Replace them with generic principles such as:

```text
parameter robustness must use coarse economically meaningful neighborhoods;
never search for an isolated optimum;
exact neighborhoods belong in strategy-specific research plans.
```

`RESEARCH_RULES.md` should contain permanent rules, not stale S1 research TODOs.

---

# 26. Historical Artifact Rule

Do NOT rewrite:

```text
S1_EVIDENCE_CLOSURE_V1.md
S2_BASELINE_ECONOMIC_SCREEN_V1.md
```

Their conclusions were valid descriptions of those experiment versions.

Create a new artifact such as:

```text
research/results/S2_DECISION_AUDIT_V2.md
```

Historical decisions remain traceable.

---

# 27. Required Outputs

Keep outputs bounded.

Suggested:

```text
research/results/
    S2_DECISION_AUDIT_V2.md
    s2_v2_variant_comparison.csv
    s2_v2_period_performance.csv
    s2_v2_rolling_performance.csv
    s2_v2_user_effort.csv
```

Only add cost CSV if it materially helps the decision.

Do not create artifact lifecycle infrastructure.

---

# 28. Tests

Add economically meaningful tests.

At minimum verify:

```text
one internal historical NaN does not invalidate the next 200 global rows

200 valid historical observations are sufficient

current signal-date missing price → UNAVAILABLE

insufficient valid history → UNAVAILABLE

no future observation enters moving average

trend state is unchanged by irrelevant missing rows outside the last 200 valid observations

unchanged target state → no order under signal-change-only execution

changed trend state → order is emitted

availability change → target change is emitted

VectorBT still handles portfolio/cash/fees/orders

S1 frozen outputs remain unchanged

S2 V1 frozen artifact is not modified
```

Do not write broker mocks or custom execution simulators.

---

# 29. Documentation Update Is Mandatory

After the experiment update:

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
README.md
```

as actually required.

`CURRENT_STATE.md` must clearly explain:

```text
why V1 rejected S2
what V2 audited
what the missing-data issue actually did
difference between monthly target reset and signal change
how often the user would really need to act
whether S2 remains economically attractive
final decision
next single direction
```

---

# 30. Architecture State After Goal

If:

```text
CONTINUE_S2_TO_RQALPHA
```

then architecture should state:

```text
S1 = REJECTED
S2 V1 = rejected under strict semantics
S2 V2 = passed corrected economic screen
next = RQAlpha authoritative validation
S3 = future
```

If:

```text
REJECT_S2_FINAL
```

then:

```text
S1 = REJECTED
S2 = FINAL REJECTED
next = S3 economic screen
```

No ambiguous status.

---

# 31. Framework-Reuse Audit

Final report must explicitly state:

```text
What VectorBT functionality was reused?

Was any VectorBT capability duplicated?

Was RQAlpha used only where justified?

What custom code was added?

Why was each custom component strategy-specific rather than generic infrastructure?
```

Any unjustified framework duplication must be removed before commit.

---

# 32. Validation

Run actual repository checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Run the real S2 V2 experiment.

Do not claim success for commands not actually executed.

GitHub Actions status checks are not currently required for this bounded Goal; do not build CI infrastructure just to satisfy this Goal.

---

# 33. Final Report Format

Return:

```text
1. Executive Summary

2. Repository Baseline
   - starting HEAD
   - current architecture state

3. Why S2 V1 Required Re-Audit

4. Missing-Data Root Cause
   - 510500 case
   - Tushare evidence
   - RQAlpha evidence if inspected

5. Corrected Trend Availability Semantics

6. V1 vs V2A
   - isolate data-semantic impact

7. V2A vs V2B
   - isolate low-touch execution impact

8. Benchmark Comparison

9. 2015–2016 Drawdown Re-Analysis

10. Temporal / Rolling Robustness

11. User Effort
    - scheduled reviews
    - actual action months
    - instruments changed per action

12. Cost Sensitivity

13. Framework Reuse Audit

14. Final Decision
    exactly one:
    CONTINUE_S2_TO_RQALPHA
    REJECT_S2_FINAL

15. Why The Evidence Supports The Decision

16. What Is Still Not Proven

17. Architecture Drift Audit

18. Documentation Updated

19. Tests / Verification

20. Next ONE Goal

21. Git State
    - final commit SHA
    - branch
    - push status
```

---

# 34. User-Facing Explanation

The final report must explain in plain language:

```text
Was S2 actually a bad trend strategy?

Or did V1 punish it because of:
- two missing observations
- unnecessary exact monthly rebalancing?
```

Also answer:

> If I actually followed the corrected S2, approximately how many months per year would I need to trade, and how many ETFs would I usually touch when I do?

This is a primary acceptance criterion.

---

# 35. Git Requirement

After verification:

```bash
git status
git diff
```

Ensure no:

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

Suggested commit:

```text
audit S2 data semantics and low-touch execution
```

---

# 36. Final Principle

Do not optimize the strategy.

Do not add another strategy.

Do not build infrastructure.

This Goal has one purpose:

```text
determine whether S2 V1 was rejected for a real economic reason
or because its measurement/execution semantics were unnecessarily hostile
to the project's low-frequency objective
```

Use:

```text
Tushare Pro for required market evidence
VectorBT for economic screening
RQAlpha only for bounded diagnostics
```

and stop after the decision.

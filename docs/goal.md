# Goal: S2 RQAlpha Frozen-Target Execution Validation V1

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Research Correctness Reviewer
```

---

# 0. Goal

The frozen S2 V2B strategy has already passed the VectorBT economic screen.

Do NOT re-validate its basic signal semantics.

Do NOT build new validation infrastructure.

This Goal answers ONE question:

> When the already-frozen S2 V2B target schedule is executed by RQAlpha's native China-market execution/accounting infrastructure, does the strategy remain economically and operationally viable?

End with exactly one:

```text
CONTINUE_S2_TO_ROBUSTNESS

REVISE_S2_EXECUTION

REJECT_S2_AFTER_RQALPHA
```

---

# 1. Repository First

Read latest:

```text
README.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md

tacticore/strategies/multi_asset_trend.py
tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/results/S2_DECISION_AUDIT_V2.md
```

Record current HEAD.

Do not modify historical S1/S2 research artifacts.

---

# 2. Permanent Rule Upgrade

Update `docs/RESEARCH_RULES.md` and, if appropriate, `docs/ARCHITECTURE.md` with:

# Framework / Community First

Before implementing infrastructure:

```text
1. Check existing TactiCore code.
2. Check VectorBT / RQAlpha native API.
3. Check official framework Mod / extension points.
4. Check mature community implementation.
5. Only then write the smallest TactiCore-specific adapter.
```

Custom implementation is the final option.

Do not add another dependency merely because it exists.

A community dependency must:

```text
solve a concrete current blocker
+
be materially simpler than local implementation
+
not duplicate VectorBT/RQAlpha
```

---

# 3. Previously Closed Questions Must Stay Closed

Do NOT redo broad investigations of:

```text
Tushare fund_daily correctness
fund_adj semantics
200 valid-observation semantics
UNAVAILABLE vs NEGATIVE_SIGNAL
lookahead
V1 missing-row bug
V1 vs V2A
V2A vs V2B
cost sensitivity
rolling 3Y / 5Y
general S2 economic screen
```

These are already documented by S2 Decision Audit V2.

Re-open one only if the new RQAlpha execution result exposes a concrete contradictory observation.

No repeated generic "signal credibility audit".

---

# 4. Freeze Target Schedule

Generate or load the exact frozen S2 V2B target-change schedule from the existing strategy implementation.

Persist only if needed for reproducibility:

```text
execution_date
target weights
```

The target schedule is the experiment input.

Do NOT recompute the S2 economic signal inside RQAlpha for the primary experiment.

Architecture:

```text
Tushare canonical
      ↓
frozen S2 V2B targets
      ↓
RQAlpha
```

NOT:

```text
RQAlpha prices
      ↓
new S2 signal implementation
      ↓
RQAlpha
```

---

# 5. Reuse RQAlpha Native Infrastructure

Before adding code, inspect installed RQAlpha 5.6.5.

Prefer its native APIs and Mods.

Specifically inspect whether the installed version provides an appropriate:

```text
order_target_portfolio
```

API for ETF portfolios.

If available and semantically appropriate:

prefer it over manually recreating whole-portfolio target-order logic.

Otherwise use existing documented target-percent APIs.

Do NOT implement:

```text
order sizing engine
round-lot logic
cash reservation
fill simulator
matching
slippage simulator
commission calculation
position accounting
portfolio accounting
corporate actions
price-limit rules
volume limits
```

RQAlpha owns all of these.

---

# 6. Use sys_analyser First

Enable and use RQAlpha's existing:

```text
sys_analyser
```

for authoritative records.

Prefer its native outputs for:

```text
orders
trades
portfolio
positions
returns
risk metrics
```

Do NOT create parallel TactiCore ledgers for information already recorded by sys_analyser.

If useful, configure:

```text
output_file
or
report_save_path
```

outside temporary runtime areas as appropriate.

Only commit small derived research results.

Do NOT commit the entire framework runtime dump if large.

---

# 7. Order / Trade Event Reuse

If sys_analyser does not expose enough detail to explain a specific failed or rejected order:

use RQAlpha's existing order/trade event mechanisms.

Relevant framework events may include:

```text
ORDER_CREATION_PASS
ORDER_CREATION_REJECT
ORDER_CANCELLATION_PASS
ORDER_CANCELLATION_REJECT
ORDER_UNSOLICITED_UPDATE
TRADE
```

Use these only when required.

Do NOT build a generic TactiCore order lifecycle state machine.

---

# 8. Primary Experiment

Replay frozen S2 V2B targets through RQAlpha.

Compare:

```text
VectorBT V2B intended strategy
vs
RQAlpha realized portfolio
```

Use a matched evaluation interval.

Report native framework results including at least:

```text
total return
CAGR
Max Drawdown
Sharpe
transaction costs
orders
trades
cash
```

Use RQAlpha-native metrics where available.

Do not recreate them locally merely to match old report formatting.

If one project-specific annualization transformation is unavoidable, document it.

---

# 9. Minimal Target-Tracking Analysis

Do NOT build a "target tracking framework".

The only local derived calculation needed is a bounded comparison:

```text
intended target weights
vs
actual RQAlpha positions
```

At:

```text
target-change execution dates
+
subsequent monthly review dates
```

Report only decision-relevant summaries such as:

```text
mean total absolute weight deviation
maximum deviation
months materially off target
cash residual
number of targets not fully reached
```

Keep implementation local to this research experiment unless a second real caller later needs it.

---

# 10. Critical Economic Question

Focus specifically on:

```text
signal-change-only
+
incomplete execution
```

Example:

```text
January desired A = 20%
RQAlpha reaches only 17%

February desired A still = 20%
strategy target unchanged

V2B emits no new order
```

Determine whether this causes persistent economically meaningful drift.

Do NOT fix it yet.

---

# 11. No Generic Execution-Friction Classifier

Do NOT create a generic taxonomy/framework for:

```text
lot size
cash
volume
limit
suspension
partial fill
```

Use RQAlpha-native statuses/events/logs to explain only material cases.

A simple research table is enough:

```text
date
symbol
intended
realized
native order status / evidence
brief reason if known
```

If not known:

```text
UNEXPLAINED_EXECUTION_DIFFERENCE
```

is acceptable.

---

# 12. Signal Diagnostic Is Conditional Only

Do NOT build a second full RQAlpha-native S2 signal path.

Only if the primary frozen-target experiment produces an execution discrepancy that cannot be explained by RQAlpha execution/accounting:

inspect that specific date/symbol using:

```text
history_bars
instrument metadata
volume
suspension state
adjust_type
```

This is:

```text
targeted diagnostic
```

not:

```text
second signal validation pipeline
```

Do NOT calculate a whole-history signal-agreement metric unless evidence proves it is necessary to resolve the final decision.

---

# 13. No New Data Infrastructure

Continue using:

```text
Tushare Pro
```

as the research data source.

Continue using the existing:

```text
RQAlpha official bundle
```

for market execution semantics.

Do NOT add:

```text
RQData
AKShare
yfinance
new provider abstraction
historical master database
```

in this Goal.

---

# 14. No Parameter Work

Freeze:

```text
trend_window = 200
```

Do not evaluate:

```text
150 / 200 / 250
```

yet.

Do not add:

```text
volatility targeting
risk parity
no-trade bands
cash buffer
retry policy
```

yet.

First determine whether the frozen strategy survives RQAlpha.

---

# 15. User-Maintenance Evidence

Use RQAlpha actual order/trade records to report:

```text
monthly reviews
target-change months
months with submitted orders
months with actual fills
number of instruments actually traded
months where target remained materially unreached
```

Translate into:

> If the owner actually followed the strategy, how many months per year would require intervention?

Do not count a framework bookkeeping event as a user action.

---

# 16. Decision

## CONTINUE_S2_TO_ROBUSTNESS

Use if:

```text
RQAlpha does not materially destroy risk-adjusted performance
AND
execution drift is manageable
AND
manual intervention remains acceptable
```

Next Goal:

```text
coarse parameter plateau / robustness
```

---

## REVISE_S2_EXECUTION

Use if:

```text
trend economics survive
BUT
signal-change-only creates persistent material execution drift
```

Identify exactly ONE dominant failure mechanism.

Recommend exactly ONE bounded execution-policy experiment.

Do not implement it now.

---

## REJECT_S2_AFTER_RQALPHA

Use if:

```text
realistic execution destroys the economic advantage
OR
realized drawdown becomes unacceptable
OR
operational burden becomes incompatible with the project mission
```

Only then unlock S3.

---

# 17. Documentation

Update:

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/STRATEGY_CATALOG.md
docs/RESEARCH_RULES.md
```

only where actual semantics changed.

Every document must explain:

```text
what changed
why
what existing framework/community capability was reused
what custom code remained
what the evidence means
what it does not prove
next ONE direction
```

---

# 18. Architecture Drift Audit

Explicitly answer:

```text
Did we duplicate RQAlpha sys_analyser?

Did we duplicate RQAlpha order/account/position logic?

Did we create a generic execution validation framework?

Did we repeat an already-closed signal credibility audit?

Did we add a dependency without a concrete blocker?

Did this Goal add more infrastructure than economic evidence?
```

Any unjustified YES must be removed before commit.

---

# 19. Tests

Only add tests for TactiCore-owned logic:

```text
frozen target schedule is stable

only target-change dates are replayed

correct symbol mapping

no target is replayed before its execution date

historical S2 V2 evidence is unchanged

RQAlpha native results are parsed correctly
```

Do NOT unit-test RQAlpha's own:

```text
matching
round lots
cash accounting
commission
slippage
```

Those are framework responsibilities.

---

# 20. Final Principle

TactiCore should increasingly become:

```text
strategy logic
+
thin orchestration
+
research decisions
```

not:

```text
a growing collection of validation infrastructure
```

Reuse community/framework capabilities before adding code.

One frozen target schedule
→ RQAlpha native execution
→ one research decision
→ stop.

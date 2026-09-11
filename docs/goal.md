# Goal: TactiCore Architecture Convergence + S2 Upstream-Native Execution Closure

## 0. Mission

TactiCore is a low-frequency multi-asset tactical allocation research system.

The repository must converge toward:

```text
strategy semantics
+
thin orchestration
+
framework/community-native infrastructure
+
explicit research evidence
+
research decisions
```

and must NOT converge toward:

```text
a custom quant platform
a third backtesting engine
a custom execution simulator
a custom accounting system
a growing generic validation framework
```

The latest repository state has already closed the broad S2 signal-credibility question.

Do NOT repeat closed signal research.

The current unresolved question is execution:

> Can upstream RQAlpha native capabilities close the persistent target drift observed when the frozen S2 V2B target schedule is executed?

Before implementing any TactiCore-specific cash-reserve workaround, inspect and validate current upstream/community capabilities.

---

# 1. Repository First

Read latest `main`.

Record:

```text
HEAD SHA
recent commits
working architecture
current research state
current dependencies
existing S1/S2 artifacts
```

At minimum read:

```text
README.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/goal.md

config/strategy.toml
config/universe.csv

tacticore/data/*
tacticore/strategies/global_dual_momentum.py
tacticore/strategies/multi_asset_trend.py
tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/experiments/run_s2_decision_audit_v2.py
research/experiments/run_s2_rqalpha_validation.py

research/results/S2_DECISION_AUDIT_V2.md
research/results/S2_RQALPHA_EXECUTION_VALIDATION_V1.md
research/results/s2_v2_frozen_targets.csv
```

Do not infer repository state from this Goal.

Repository content is authoritative.

---

# 2. First Reorganize Architecture Documentation

Refactor documentation responsibilities.

## README.md

Keep only:

```text
project mission
basic usage
current high-level strategy status
links to authoritative documents
```

Do not turn README into research history.

## docs/ARCHITECTURE.md

Rewrite it as the stable architecture source of truth.

It must describe:

```text
Data
Strategy Semantics
Research Screening
Execution Validation
Evidence / Decision
Future Production Decision
```

Define explicit ownership boundaries.

### TactiCore owns

```text
economic hypothesis
signal semantics
desired portfolio targets
strategy-specific execution policy decisions
canonical data contracts
thin framework orchestration
bounded research-derived comparisons
research evidence
research decisions
```

### VectorBT owns

```text
fast portfolio research
portfolio simulation
research records
returns / trades / drawdowns
parameter and sensitivity research
```

### RQAlpha owns

```text
orders
order sizing
round lots
matching
cash
positions
portfolio accounting
transaction costs
slippage
market restrictions
corporate actions
execution records
```

### TactiCore must not own

```text
generic portfolio accounting
matching engine
order lifecycle framework
generic execution simulator
third backtester
generic data platform
generic research governance platform
```

Remove transient strategy metrics and current Goal details from ARCHITECTURE.md.

Those belong in CURRENT_STATE, STRATEGY_CATALOG or research artifacts.

---

# 3. Add Version-Aware Framework / Community First

ARCHITECTURE.md and RESEARCH_RULES.md must permanently state:

```text
Existing TactiCore capability
        ↓
Current framework native API
        ↓
Official framework extension / Mod
        ↓
Latest compatible framework release
        ↓
Latest stable upstream release
        ↓
Mature community implementation
        ↓
Smallest possible TactiCore-specific adapter
```

Custom implementation is the final option.

Before implementing a workaround for a framework limitation:

```text
inspect upstream changelog
inspect upstream API
inspect upstream issues / documented extensions when useful
determine whether a newer supported release solved the problem
run a frozen-input compatibility experiment
```

Do NOT blindly upgrade merely because a newer version exists.

Upstream adoption requires evidence that the frozen strategy semantics remain unchanged.

Community dependency adoption must satisfy all of:

```text
solves a concrete current blocker
materially reduces local implementation
does not duplicate VectorBT/RQAlpha
has acceptable maintenance maturity
```

If upstream already implements the required capability, prefer upstream over a local workaround.

---

# 4. Create docs/RESEARCH_LEDGER.md

Create a lightweight append-only research knowledge ledger.

This is NOT a governance framework.

Its purpose is:

> prevent future Goals and agents from repeating already-closed research.

Each entry should include:

```text
ID
strategy
question
status
scope
conclusion
evidence pointers
data snapshot
framework/version when relevant
reopen condition
```

Statuses should remain simple:

```text
CLOSED
REJECTED
ACTIVE
SUPERSEDED
```

Do not build software around this document.

---

# 5. Migrate Already-Closed Questions Into the Ledger

Record existing validated conclusions.

At minimum cover:

```text
Tushare canonical data provenance

fund_daily / fund_adj interpretation already investigated

missing values are not silently filled

UNAVAILABLE != NEGATIVE_SIGNAL

S2 uses per-asset latest valid observations

signal date must itself have a valid price

month-end signal cannot execute using the same close

V1 continuous-row missing-data behavior was identified and rejected

V1 → V2A availability-semantics effect is already measured

V2A → V2B does not change signal targets;
it changes target-submission behavior

general S2 VectorBT economic screen is complete

existing rolling-period evidence is complete

existing cost-sensitivity evidence is complete

generic S2 signal-credibility audit is CLOSED

frozen S2 V2B target-change schedule is established

RQAlpha 5.6.5 frozen-target replay is complete

the dominant 5.6.5 execution failure is cash insufficiency
followed by SIGNAL_CHANGE_ONLY persistence
```

Do not recompute those merely to populate the document.

Link existing evidence.

A closed item may only be reopened if:

```text
the underlying strategy semantics change
the canonical data contract changes
the framework change invalidates the relevant assumption
or new contradictory evidence appears
```

---

# 6. CURRENT_STATE Must Become Small

Rewrite `docs/CURRENT_STATE.md` to describe only:

```text
current active strategy
current decision state
current blocker
latest decisive evidence
the next ONE experiment
```

Historical detail should link to:

```text
RESEARCH_LEDGER.md
STRATEGY_CATALOG.md
research/results/*
```

Do not use CURRENT_STATE as an accumulating research notebook.

---

# 7. goal.md Is Ephemeral

Document permanently that:

```text
docs/goal.md
```

is only the currently executing Goal.

Permanent architecture decisions must not exist only in `goal.md`.

Permanent research rules must not exist only in `goal.md`.

Closed research conclusions must not exist only in `goal.md`.

The source hierarchy is:

```text
ARCHITECTURE
+
RESEARCH_RULES
+
RESEARCH_LEDGER
+
research artifacts
+
CURRENT_STATE
→ generate the next Goal
```

not the reverse.

---

# 8. Re-evaluate the Current S2 Next Step Using Upstream First

The current repository proposes a local cost-derived cash reserve experiment.

Do NOT implement it yet.

First inspect the latest stable RQAlpha upstream.

Specifically investigate official capabilities relevant to the already-observed failure:

```text
partial_fill_on_insufficient_cash
order_target_portfolio
order_target_portfolio_smart
ETF support
cash handling
transaction-cost-aware portfolio targeting
```

Record exact upstream versions and official evidence.

At the time this Goal was drafted, RQAlpha 6.x appeared to contain relevant native capabilities.

Do not trust this Goal's statement.

Verify upstream again.

---

# 9. Freeze Existing Evidence

The experiment input must remain the existing S2 V2B frozen target schedule.

Do not regenerate a new economic strategy.

Verify the existing schedule/hash.

The experiment architecture remains:

```text
existing Tushare canonical
        ↓
existing frozen S2 V2B targets
        ↓
RQAlpha execution
```

NOT:

```text
RQAlpha data
↓
new signal implementation
↓
new target schedule
```

The entire purpose is to isolate execution behavior.

---

# 10. Run an Isolated RQAlpha Upgrade Compatibility Experiment

Do not immediately change production dependency constraints.

Use an isolated environment first.

Preserve the existing RQAlpha 5.6.5 result as the control.

Then evaluate the latest appropriate upstream version.

Start with behavior closest to the existing implementation:

```text
same frozen targets
same initial cash
same fees
same slippage
same matching assumptions
same evaluation interval
same target-tracking metrics
```

First determine whether a framework-version upgrade alone changes unrelated semantics.

---

# 11. Test Native Capability One Variable at a Time

Do not combine multiple fixes in the first experiment.

Preferred sequence:

```text
A. existing 5.6.5 result
   control only; do not redo broad research

B. newer RQAlpha
   existing order_target_portfolio semantics

C. newer RQAlpha
   enable the native insufficient-cash handling capability
   if supported and appropriate

D. only if still decision-relevant:
   test order_target_portfolio_smart for ETF targets
```

Do not introduce a TactiCore cash buffer during these experiments.

Do not add retry logic.

Do not add no-trade bands.

Do not add volatility targeting.

Do not change the 200-observation rule.

---

# 12. Measure Only Decision-Relevant Execution Evidence

Reuse the existing bounded target-tracking analysis.

Do not build a new execution analysis framework.

Compare:

```text
cash-insufficient failures
volume-limit failures
materially off-target execution dates
persistent off-target review months
cash residual
orders
trades
transaction cost
turnover
CAGR
maximum drawdown
user intervention burden
```

Use the existing 5% material-deviation reporting threshold unless there is strong evidence it is inappropriate.

Separate:

```text
cash-driven persistent drift
```

from:

```text
secondary market friction
```

Do not turn secondary friction into a generic taxonomy.

---

# 13. Success Criterion

Native execution closure succeeds if upstream capability:

```text
eliminates the dominant cash-insufficient rejection mechanism
AND
eliminates persistent cash-driven target drift
AND
does not materially invalidate the strategy's economic evidence
```

Volume-related isolated execution differences may remain documented if they do not produce persistent economically material divergence.

Do not demand bit-identical VectorBT/RQAlpha returns.

They have different execution/accounting semantics.

---

# 14. Decision

End with exactly one primary decision.

## ADOPT_UPSTREAM_RQALPHA_EXECUTION

Use if upstream-native functionality closes the dominant execution problem.

Then:

```text
update the supported RQAlpha dependency
use the smallest native configuration/API change
do not implement local cash reserve
update evidence ledger
```

The next research stage becomes:

```text
S2 coarse parameter plateau / robustness
```

---

## FALL_BACK_TO_BOUNDED_CASH_RESERVE_EXPERIMENT

Use only if:

```text
upstream upgrade is incompatible
OR
upstream native execution capability does not close the dominant drift
```

Then preserve all current signal evidence and create a separate next Goal for exactly one local cash-reserve experiment.

Do not implement that fallback inside this Goal.

---

## REASSESS_S2_EXECUTION_VIABILITY

Use if upstream-native execution reveals a larger structural execution problem that materially undermines the strategy.

Document the contradictory evidence.

Do not proceed to parameter optimization.

---

# 15. Small Existing Architecture Leak

Inspect:

```text
tacticore.engines.rqalpha_adapter.build_rqalpha_config
```

It is currently typed against the S1 `GlobalDualMomentumConfig`, while S2 reuses it with another strategy config and a type-ignore.

If this code must be touched for the RQAlpha experiment, remove the strategy-specific coupling using the smallest possible change.

Prefer explicit engine inputs such as:

```text
initial_cash
fees
slippage
bundle_path
```

or a minimal structural Protocol.

Do NOT create:

```text
strategy class hierarchy
engine abstraction hierarchy
generic execution framework
```

If no code change is required, record the issue and leave it for the first natural caller.

---

# 16. Tests

Test only TactiCore-owned semantics.

Protect at least:

```text
existing frozen target schedule remains unchanged

target execution dates remain unchanged

no target is executed before its frozen execution date

symbol mapping remains correct

closed signal semantics are not changed by the execution experiment

version-specific RQAlpha configuration is explicit
```

Do not unit-test RQAlpha internals.

Do not write tests for:

```text
matching
round lots
cash accounting
transaction cost calculation
partial-fill implementation
```

Those belong upstream.

---

# 17. CI Observation

The current repository does not have an active commit-status / workflow-run gate on the latest main commit.

Do not build CI infrastructure as part of the execution experiment unless required.

After the S2 execution decision is closed, a separate small maintenance Goal may add one minimal GitHub Actions workflow for:

```text
pytest
ruff
mypy
```

Its justification must be protecting already-closed TactiCore-owned semantics, not building a CI platform.

---

# 18. Documentation at Completion

Update:

```text
README.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/goal.md
```

according to their newly defined responsibilities.

Do not rewrite historical research artifacts.

Record:

```text
what was already known
what was newly learned
which upstream/community capability was considered
which capability was adopted or rejected
what custom code remains
what remains unproven
what the next ONE research direction is
```

---

# 19. Final Architecture Drift Audit

Before completion explicitly verify:

```text
Did we repeat a closed signal-credibility investigation?

Did we implement something already provided by RQAlpha?

Did we implement something already provided by VectorBT?

Did we ignore a newer upstream solution?

Did we add an unnecessary dependency?

Did we promote experiment-local code into a generic framework?

Did ARCHITECTURE contain transient research state?

Did goal.md contain permanent knowledge not copied into the correct source-of-truth document?

Did we change strategy semantics while claiming to test execution only?
```

Any unjustified YES must be corrected before completion.

---

# 20. Commit

After all required validation succeeds:

```text
git status
git diff
tests
lint
type checks
```

Create one coherent commit and push it to the current GitHub branch.

The final report must include:

```text
starting HEAD
ending HEAD
commit SHA
files changed
tests executed
upstream/community evidence
experiment result
final decision
next ONE direction
```

Final principle:

```text
Closed questions stay closed.

Upstream capability before local workaround.

TactiCore owns strategy and decisions.

Community frameworks own generic quant infrastructure.
```

---

# 21. 本 Goal 执行状态

状态：已完成。永久架构、规则与关闭结论已分别写入 `ARCHITECTURE.md`、`RESEARCH_RULES.md`、`RESEARCH_LEDGER.md` 和研究报告；本文件只保留本次 Goal 及其结果指针。

权威结果：`research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md`

ADOPT_UPSTREAM_RQALPHA_EXECUTION

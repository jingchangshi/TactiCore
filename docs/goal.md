# Goal: TactiCore Agent Routing Contract + S2 Coarse Parameter Plateau & Robustness Gate

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Research Architecture Reviewer
+
Repository Maintainer
```

---

# 0. Why This Work Exists

TactiCore has already completed the important foundation work around:

```text
canonical market data
S1 evidence closure
S2 signal/data semantics
S2 VectorBT economic screening
S2 RQAlpha frozen-target execution validation
RQAlpha upstream-native execution closure
architecture responsibility convergence
research knowledge ledger
```

The repository should now increasingly operate as:

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

and NOT as:

```text
a custom quant platform
a growing validation framework
a custom execution engine
a custom accounting engine
an infrastructure-heavy research system
```

Two things are required in this Goal:

```text
A. Add a small root AGENTS.md
   so coding agents automatically discover
   architecture / rules / research state / closed evidence.

B. Execute the next actual research stage:
   S2 coarse parameter plateau & robustness gate.
```

The AGENTS.md work exists to prevent future agents from:

```text
ignoring repository architecture
repeating already-closed research
implementing community/framework functionality locally
following stale goal.md instructions
or expanding infrastructure without a research blocker
```

It must remain a thin routing contract.

Do NOT turn AGENTS.md into another architecture document.

---

# 1. Repository First

Start from the latest remote `main`.

Do not trust:

```text
this prompt
previous conversations
previous Codex reports
old CURRENT_STATE contents
old goal.md
memory
```

as repository truth.

Record:

```text
current HEAD SHA
recent commits
current dependency versions
current working tree state
```

Read at minimum:

```text
README.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/goal.md

config/strategy.toml
config/universe.csv

tacticore/strategies/multi_asset_trend.py
tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/experiments/run_s2_decision_audit_v2.py
research/experiments/run_s2_rqalpha_validation.py

research/results/S2_DECISION_AUDIT_V2.md
research/results/S2_RQALPHA_EXECUTION_VALIDATION_V1.md
research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md
```

Also inspect existing tests.

Before modifying anything, summarize internally:

```text
current S2 stage
closed questions
remaining unproven questions
framework responsibility boundaries
next research gate
```

If repository evidence contradicts this Goal, repository evidence wins.

---

# 2. Add Root AGENTS.md

Create:

```text
/AGENTS.md
```

Its purpose is:

> bootstrap coding agents into the repository's authoritative architecture, rules, research evidence, and current task context.

AGENTS.md must remain small and stable.

Target approximately:

```text
80–180 lines
```

Do not duplicate whole sections from architecture or rules documents.

Prefer links and routing instructions.

---

# 3. AGENTS.md Required Structure

The root AGENTS.md should contain roughly the following sections.

## 3.1 Repository Mission

State briefly:

```text
TactiCore is a low-frequency,
multi-asset tactical allocation research system.

Primary goal:
find robust, explainable, executable,
low-maintenance allocation strategies.

Strategy research > infrastructure engineering.
```

State explicitly that the repository is NOT intended to become:

```text
a generic quant platform
a custom backtester
a custom accounting engine
a custom execution simulator
a generic research governance framework
```

Do not copy the entire architecture.

Link:

```text
docs/ARCHITECTURE.md
```

as authority.

---

# 4. Mandatory Agent Bootstrap

AGENTS.md must tell every coding agent:

Before proposing or changing code, first read:

```text
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
```

Then read relevant:

```text
research/results/*
```

for the strategy being modified.

Read:

```text
docs/goal.md
```

only as the current execution instruction.

Explicitly state:

> goal.md is ephemeral and is not a permanent source of architectural or research truth.

---

# 5. Document Routing Table

AGENTS.md should contain a compact routing table such as:

| Need                                     | Read                       |
| ---------------------------------------- | -------------------------- |
| system responsibility / ownership        | `docs/ARCHITECTURE.md`     |
| permanent research rules                 | `docs/RESEARCH_RULES.md`   |
| already-closed questions                 | `docs/RESEARCH_LEDGER.md`  |
| current active blocker / next experiment | `docs/CURRENT_STATE.md`    |
| strategy lifecycle status                | `docs/STRATEGY_CATALOG.md` |
| detailed historical evidence             | `research/results/*`       |
| current task                             | `docs/goal.md`             |

This table is the main value of AGENTS.md.

Do not repeat the contents of those files.

---

# 6. Authority / Conflict Order

AGENTS.md must define how agents resolve conflicting information.

Use this order:

```text
actual current source code + frozen research artifacts
        ↓
ARCHITECTURE.md
        ↓
RESEARCH_RULES.md
        ↓
RESEARCH_LEDGER.md
        ↓
STRATEGY_CATALOG.md
        ↓
CURRENT_STATE.md
        ↓
goal.md
```

Clarify:

* repository facts override stale prose;
* architecture owns responsibility boundaries;
* research rules own permanent methodology;
* ledger owns closed-question history;
* CURRENT_STATE owns the active research frontier;
* goal.md cannot silently override permanent architecture/rules.

If a real contradiction exists:

```text
do not invent a compromise;
identify the contradiction;
fix the appropriate authoritative document
as part of the same Goal when in scope.
```

---

# 7. Closed Questions Stay Closed

AGENTS.md must point agents to:

```text
docs/RESEARCH_LEDGER.md
```

before performing broad investigation.

Permanent rule:

> Do not redo a CLOSED or REJECTED research question simply because a new Goal touches the same strategy.

A closed question may only be reopened if:

```text
strategy semantics changed
canonical data contract changed
framework change invalidates the assumption
or new contradictory evidence appeared
```

When reopening:

```text
identify the exact ledger entry
identify the contradictory evidence
keep the reopened scope bounded
```

No generic:

```text
signal credibility audit
data quality re-audit
execution taxonomy
```

without a concrete contradiction.

---

# 8. Framework / Community / Upstream First

AGENTS.md must contain only the short version:

```text
Existing TactiCore
→ native framework API
→ official extension / Mod
→ compatible/new stable upstream
→ mature community solution
→ smallest local adapter
```

Point to:

```text
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
```

for full rules.

Before implementing generic quant functionality, agents must check whether:

```text
VectorBT
RQAlpha
Tushare
or another already-approved dependency
```

already owns that responsibility.

Do NOT locally implement:

```text
portfolio accounting
matching
round lots
cash accounting
transaction-cost engines
generic order lifecycle
generic backtesting
generic performance records
```

unless existing framework capability is proven insufficient for the specific blocker.

---

# 9. Research Code Placement Rule

AGENTS.md should explain:

Strategy semantics belong in:

```text
tacticore/strategies/
```

Thin reusable framework adapters belong in:

```text
tacticore/engines/
```

One-off or bounded research work belongs in:

```text
research/experiments/
```

Research outputs belong in:

```text
research/results/
```

Tests should protect TactiCore-owned semantics.

Do not promote an experiment helper into:

```text
tacticore/
```

until at least one real reusable responsibility exists.

Avoid directories such as:

```text
research_engine/
robustness_framework/
parameter_optimizer/
execution_framework/
governance/
```

without clear multiple production callers.

---

# 10. Completion Documentation Rule

AGENTS.md must state:

When a Goal completes:

Always consider:

```text
docs/CURRENT_STATE.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
```

Update them only when their owned semantics changed.

Update:

```text
docs/ARCHITECTURE.md
```

only if architecture or responsibility boundaries changed.

Update:

```text
docs/RESEARCH_RULES.md
```

only if a permanent methodology rule changed.

Do NOT modify architecture/rules just to record current experiment numbers.

Research metrics belong in:

```text
research/results/*
```

---

# 11. Keep AGENTS.md Stable

Do not put transient information such as:

```text
current CAGR
current Max Drawdown
current exact failing dates
current current HEAD
current Goal-specific parameter list
```

inside AGENTS.md.

Those belong elsewhere.

AGENTS.md should still be valid several Goals later.

---

# 12. No Nested AGENTS Yet

Do NOT add:

```text
tacticore/AGENTS.md
research/AGENTS.md
docs/AGENTS.md
AGENTS.local.md
```

during this Goal.

The repository is currently small enough for one root routing file.

Add nested routing only when:

```text
a subtree has genuinely different rules
AND
agents repeatedly need different instructions there
```

Do not pre-architect it.

---

# 13. Current Research Frontier

After adding the routing contract, proceed to the real next research task.

The current active strategy should be verified from repository state.

Expected state is approximately:

```text
S1:
REJECTED

S2 V2B:
economic screen complete
signal/data semantics closed
RQAlpha upstream execution closure complete

S3:
locked
```

Do not assume this if latest repository says otherwise.

The next research question should be:

> Is the S2 200-valid-observation trend rule located inside a broad economically stable parameter plateau, or is 200 an isolated historical optimum?

This is robustness validation.

It is NOT parameter optimization.

---

# 14. Freeze Strategy Semantics

Only vary:

```text
trend_window
```

Freeze everything else:

```text
canonical dataset
risk universe
fallback asset
valid-observation semantics
signal-date price requirement
monthly signal timing
next-observation execution
SIGNAL_CHANGE_ONLY
equal sleeve allocation
fees
slippage
initial capital
VectorBT engine path
```

Do NOT introduce:

```text
volatility targeting
risk parity
cash buffer
retry policy
no-trade band
new data source
new universe
new execution policy
S3
```

---

# 15. Predeclare a Coarse Parameter Set

Before looking at results, freeze a small economically meaningful neighborhood around 200.

Recommended default:

```text
160
180
200
220
240
```

If repository evidence provides a stronger pre-existing declared set, use it.

Do NOT create a dense grid.

Forbidden examples:

```text
100..300 step 5
Bayesian optimization
Sharpe maximization
random search
find best trend_window
```

The Goal is to determine whether a plateau exists.

It is not to discover a better-looking number.

---

# 16. Do Not Replace 200 Just Because Another Point Wins

The 200-day value is the transparent research baseline.

If:

```text
180
200
220
```

or a broader neighboring range produces similar economics,

the correct conclusion is normally:

```text
KEEP_200
```

not:

```text
switch to 180 because backtest Sharpe is slightly higher
```

Parameter sweep evidence is used to test robustness.

It is not a production parameter optimizer.

---

# 17. Implementation Scope

Prefer one bounded experiment script:

```text
research/experiments/run_s2_parameter_plateau.py
```

Reuse existing:

```text
load_price_csv
load_trend_config
build_month_end_targets
build_signal_change_execution_weights
run_target_weights
```

For each frozen window:

```text
create an in-memory config variant
generate targets
generate signal-change execution weights
run VectorBT
collect decision-relevant evidence
```

Prefer:

```python
dataclasses.replace(config, trend_window=window)
```

or an equally small equivalent.

Do NOT add a parameter optimizer abstraction.

Do NOT modify `config/strategy.toml` repeatedly to run experiments.

The canonical configured strategy remains:

```text
trend_window = 200
```

unless a later explicit research decision changes it.

---

# 18. Full-Sample Plateau Evidence

For each parameter report at minimum:

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

Reuse framework-native records wherever possible.

Do not add a generic metrics library merely to format the report.

The key research question is the SHAPE of the parameter neighborhood.

Good:

```text
160  similar
180  similar
200  similar
220  similar
240  similar
```

Concerning:

```text
160 weak
180 weak
200 exceptional
220 weak
240 weak
```

---

# 19. Time-Regime Robustness

Use pre-existing fixed subperiods where already established.

Expected existing periods include:

```text
2013–2016
2017–2019
2020–2022
2023–2026
```

Do not create new regime boundaries after inspecting results.

Compare across parameters:

```text
CAGR
Max Drawdown
Sharpe
Calmar
```

Focus on:

```text
whether all nearby parameters survive the same regimes
whether one parameter depends on a single favorable period
whether parameter rankings reverse dramatically
whether defensive behavior disappears outside 200
```

---

# 20. Rolling Evidence

Existing S2 rolling 3Y / 5Y evidence for the 200 baseline is already CLOSED.

Do NOT repeat it as another generic audit.

Instead extend only what is necessary to answer:

> Do neighboring parameters show similar rolling robustness?

Reuse existing calculations if possible.

Do not build:

```text
RollingResearchEngine
RobustnessFramework
WindowAnalysisService
```

Keep it experiment-local.

---

# 21. Operational Robustness

TactiCore optimizes for:

```text
robust
+
executable
+
low maintenance
```

Therefore compare parameter windows not only on return but also:

```text
target-change months
annualized action months
turnover
trade count
average holding duration
```

A slightly higher CAGR with materially higher maintenance burden is not automatically better.

Do not define a synthetic weighted score unless a permanent economic rationale already exists.

Prefer transparent tables.

---

# 22. Avoid False OOS Claims

The historical 2012–2026-08 data has already been repeatedly inspected.

Do NOT call:

```text
2023–2026
```

or another previously observed historical slice:

```text
true untouched OOS
```

Use terminology such as:

```text
historical robustness
subperiod evidence
rolling evidence
```

True prospective evidence must begin only after the already-researched historical cutoff.

Expected cutoff is:

```text
2026-08-31
```

Verify from repository artifacts.

---

# 23. Decision Rules Must Be Declared Before Results

The experiment must end with exactly one primary robustness decision.

## PASS_S2_PARAMETER_PLATEAU

Use if:

```text
200 is not an isolated performance spike

AND nearby economically meaningful windows
retain broadly similar return/risk structure

AND important subperiods do not reveal
structural collapse specific to nearby windows

AND rolling evidence is not dependent
on a narrow parameter point

AND operational burden remains compatible
with TactiCore's low-frequency mission
```

If this passes:

```text
KEEP trend_window = 200
```

Do not change to the historically best neighbor.

Then freeze a research candidate.

---

## REJECT_S2_PARAMETER_FRAGILITY

Use if:

```text
200 is an isolated winner

OR nearby parameters materially destroy
the strategy's economic rationale

OR behavior changes sign / regime
over small parameter changes

OR performance depends on a narrow historical pocket
```

If this happens:

Do NOT continue searching for:

```text
187
193
207
211
```

Do NOT fine tune.

Record that the simple trend hypothesis is too parameter fragile for TactiCore's mission.

---

# 24. Optional Third Outcome Only If Evidence Truly Requires It

If there is a narrow unresolved issue preventing a defensible PASS/REJECT decision, one outcome may be:

```text
REVISE_S2_ROBUSTNESS_TEST
```

but only if:

```text
the experiment itself has a concrete methodological defect
```

not because results are unattractive or ambiguous.

Identify exactly one defect and exactly one bounded next experiment.

Do not use REVISE as permission for indefinite optimization.

---

# 25. Expected Research Outputs

Prefer:

```text
research/results/S2_PARAMETER_PLATEAU_V1.md

research/results/s2_parameter_plateau_summary.csv
research/results/s2_parameter_periods.csv
research/results/s2_parameter_rolling.csv
```

Only create files that carry decision-relevant evidence.

Avoid dozens of intermediate artifacts.

The report must explain:

```text
frozen experiment design
parameter set
why the set was chosen
what was held constant
full-sample evidence
subperiod evidence
rolling evidence
operational evidence
whether a plateau exists
what the evidence does NOT prove
final decision
```

---

# 26. RQAlpha Scope in This Goal

Do NOT automatically run full RQAlpha execution validation for every parameter.

VectorBT is the research engine for parameter robustness.

RQAlpha has already validated the chosen execution architecture.

Only consider additional RQAlpha runs if the parameter experiment reveals a concrete execution-sensitive difference that VectorBT cannot answer.

If no such blocker appears:

```text
do not run RQAlpha sweep
```

A multi-parameter RQAlpha grid would add cost and complexity without answering the primary robustness question.

---

# 27. If Plateau Passes: Freeze Research Candidate

If:

```text
PASS_S2_PARAMETER_PLATEAU
```

record a candidate such as:

```text
S2 Research Candidate R1
```

with immutable research semantics:

```text
trend_window = 200 valid observations
monthly review
next-observation execution
SIGNAL_CHANGE_ONLY
equal sleeves
existing risk universe
existing fallback
existing canonical semantics
RQAlpha 6.3 native insufficient-cash partial fill
```

Do NOT yet call it a production strategy.

The next stage should become:

```text
prospective / forward shadow evidence
```

using newly arriving data after the researched historical cutoff.

---

# 28. Prospective Evidence Is Not Implemented Yet

Do NOT build the prospective production system in this Goal.

If plateau passes, only update CURRENT_STATE to say that the next direction is:

```text
freeze candidate
+
define prospective shadow protocol
```

Do not add:

```text
scheduler
daily daemon
broker
notification system
production dashboard
```

yet.

Those require their own later Goal.

---

# 29. S3 Remains Locked

Do not begin:

```text
China Sector Rotation
Theme Rotation
```

during this Goal.

S3 remains future work until the S2 robustness decision is closed.

If S2 fails because of parameter fragility, the following Goal may decide whether S3 becomes the next research family.

Do not start it opportunistically.

---

# 30. Tests

Add only tests for TactiCore-owned additions.

Potential useful tests:

```text
parameter experiment uses declared windows only

base config remains trend_window = 200

other strategy parameters remain invariant

no same-close signal execution is introduced

SIGNAL_CHANGE_ONLY remains unchanged

output includes each declared parameter exactly once
```

Do not unit-test VectorBT internals.

Do not test RQAlpha internals in this Goal.

---

# 31. Architecture Drift Audit

Before completion answer explicitly:

```text
Did we duplicate information into AGENTS.md
instead of routing to authoritative documents?

Did we create nested AGENTS files without need?

Did we repeat a CLOSED research-ledger question?

Did we search for the historically optimal trend window?

Did we modify strategy semantics beyond trend_window?

Did we build a generic robustness framework?

Did we implement VectorBT/RQAlpha functionality locally?

Did we introduce a new dependency without a blocker?

Did we change ARCHITECTURE despite no architecture change?

Did we change RESEARCH_RULES merely to describe this experiment?

Did we claim a historical period is untouched OOS when it was already studied?
```

Any unjustified YES must be corrected before commit.

---

# 32. Documentation After the Experiment

## AGENTS.md

Add once as the stable routing/bootstrap document.

Do not put experiment results in it.

## docs/ARCHITECTURE.md

Normally unchanged.

Only modify if this Goal discovers a real responsibility-boundary problem.

## docs/RESEARCH_RULES.md

Normally unchanged.

Only modify if a genuinely new permanent research methodology is established.

## docs/RESEARCH_LEDGER.md

Append a new entry for:

```text
S2 Parameter Plateau / Robustness
```

Record:

```text
question
parameter set
final status
conclusion
evidence
data snapshot
reopen condition
```

Do not rewrite previous entries.

## docs/CURRENT_STATE.md

Replace the current frontier with:

```text
latest decision
latest decisive evidence
remaining blocker
next ONE direction
```

Keep it short.

## docs/STRATEGY_CATALOG.md

Update S2 lifecycle.

For example if successful:

```text
economic screening: passed
execution closure: passed
parameter plateau: passed
prospective evidence: pending
production candidate: no
```

## docs/goal.md

Replace the old completed Goal with this current Goal.

At completion it may contain the final outcome pointer, but permanent facts must already exist elsewhere.

---

# 33. Final Decision If Plateau Passes

The desired lifecycle becomes:

```text
S2 signal semantics
        ✅

S2 economic screen
        ✅

S2 execution closure
        ✅

S2 parameter plateau
        ↓

PASS
        ↓

KEEP 200
        ↓

Freeze S2 Research Candidate R1
        ↓

Prospective Shadow / Forward Evidence
        ↓

Production Tradability Review
        ↓

Low-Frequency Decision Product
```

Do not skip directly from historical parameter robustness to production.

---

# 34. Stop Conditions

Stop immediately if:

```text
the requested parameter study requires changing
multiple strategy semantics at once

the code starts growing into a generic framework

the experiment becomes a search for the best parameter

existing ledger evidence is being unnecessarily repeated

the task begins implementing prospective production infrastructure

the task begins S3
```

Return to the narrow research question.

---

# 35. Validation

Before commit run the repository's currently supported checks.

Expected:

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Also execute the new research experiment and verify its committed outputs are reproducible.

If repository commands changed, follow the latest repository documentation instead.

Do not claim success from an unexecuted command.

---

# 36. Commit and Push

After all work is complete:

```text
git status
git diff
```

Inspect the complete diff.

Ensure no generated junk, environment files, credentials or large framework runtime outputs are committed.

Create one coherent commit.

Suggested intent:

```text
add agent routing and close S2 parameter robustness
```

Push to the current branch.

Do not create unrelated commits.

---

# 37. Final Report

Report:

```text
starting HEAD
ending HEAD
commit SHA
files added
files modified
tests executed
experiment command
parameter set
full-sample result summary
subperiod result summary
rolling result summary
operational result summary
final S2 robustness decision
whether 200 was kept
research-ledger entry added
next ONE direction
```

Also answer:

```text
Did AGENTS.md remain only a router?
YES / NO

Were any CLOSED questions reopened?
YES / NO
If YES, identify exact ledger entry and evidence.

Was any new generic infrastructure added?
YES / NO

Was any new framework/community dependency added?
YES / NO
If YES, explain the blocker.

Was trend_window optimized?
NO must be the normal answer.
```

---

# 38. Final Principle

```text
AGENTS.md tells agents where truth lives.

It does not become another source of truth.

Closed questions stay closed.

Parameters are tested for stability,
not optimized for historical performance.

Frameworks own generic infrastructure.

TactiCore owns strategy semantics,
research evidence,
and investment decisions.
```

---

# 39. 完成状态

- 根级路由契约：[`AGENTS.md`](../AGENTS.md)
- 决策报告：[`S2_PARAMETER_PLATEAU_V1.md`](../research/results/S2_PARAMETER_PLATEAU_V1.md)
- 永久结论：[`RESEARCH_LEDGER.md#rl-015-s2-粗粒度参数平台与稳健性`](RESEARCH_LEDGER.md#rl-015-s2-粗粒度参数平台与稳健性)
- 当前前沿：[`CURRENT_STATE.md`](CURRENT_STATE.md)
- 参数动作：`KEEP_200`

PASS_S2_PARAMETER_PLATEAU

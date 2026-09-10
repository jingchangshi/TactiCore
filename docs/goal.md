# Goal: Build Tushare Pro Data Pipeline and Validate Global Dual Momentum Baseline

Repository:

```
jingchangshi/TactiCore
```

Role:

```
Principal Quant Research Engineer
+
Research Correctness Reviewer
```

---

# Context

TactiCore has completed:

* repository bootstrap;
* canonical universe;
* VectorBT research path;
* RQAlpha adapter skeleton.

The current blocker is not infrastructure.

The blocker is:

```
No reliable real market data evidence yet.
```

The repository must now move from:

```
research pipeline works
```

to:

```
strategy evidence exists or fails.
```

---

# First Read

Before changes:

Read:

```
README.md
docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/CURRENT_STATE.md
config/universe.csv
```

Treat repository as source of truth.

---

# Main Objective

Use existing Tushare Pro access to build the smallest real-data path.

Target:

```
Tushare Pro

    |

Canonical Historical Price Dataset

    |

VectorBT Global Dual Momentum

    |

Research Metrics

    |

RQAlpha Validation Preparation
```

---

# Do NOT Build

Do not create:

* generic data platform;
* generic provider abstraction;
* database;
* data governance system;
* new backtester;
* new accounting engine.

Only implement what S1 requires.

---

# Data Requirement

Create a minimal Tushare adapter.

Required:

* ETF daily price;
* trading calendar;
* adjustment handling;
* symbol metadata.

Need explicitly record:

```
symbol

source

request parameters

adjustment type

data timestamp

download timestamp
```

---

# Important Tushare Rule

Do not assume:

```
API returned data
=
correct economic measurement
```

Verify:

* adjustment semantics;
* date alignment;
* missing values;
* duplicate dates;
* look-ahead risks.

Document assumptions.

---

# Canonical Dataset

Create:

```
data/canonical/
```

with stable format:

```
date | symbol1 | symbol2 | ...
```

Requirements:

* reproducible;
* deterministic;
* documented.

---

# Strategy Validation

Run Global Dual Momentum using real data.

Current baseline:

```
252 trading day momentum

absolute momentum > 0

rank eligible assets

hold top 2

monthly rebalance

fallback defensive asset
```

Do not optimize parameters yet.

---

# Required Research Output

Generate:

```
research/results/
```

Include:

* CAGR
* Max Drawdown
* Sharpe
* Calmar
* Turnover
* Trade Count
* Average Holding Period

Also include:

```
strategy assumptions
data assumptions
limitations
```

---

# Robustness Preparation

Do not perform huge optimization.

Only prepare:

```
lookback parameter sweep

80
120
160
252
```

and compare stability.

---

# RQAlpha

Do not block the whole goal on bundle.

Current goal:

Prepare:

* data mapping;
* strategy mapping;
* validation interface.

If bundle unavailable:

document exact blocker.

Never fake successful RQAlpha validation.

---

# Documentation Requirement

After implementation update:

```
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
```

Explain:

## What changed

## Why changed

## Strategy impact

## Data impact

## Remaining uncertainty

## Next single recommended direction

---

# Final Report Format

1. Executive Summary

2. Implemented Changes

3. Tushare Data Pipeline

4. Data Quality Checks

5. Global Dual Momentum Result

6. RQAlpha Status

7. Strategy Interpretation

8. Limitations

9. Architecture Drift Check

10. Updated Documentation

11. Next Recommended Goal

12. Commit SHA

---

After verification:

```
git commit
git push
```

Do not continue beyond this goal.

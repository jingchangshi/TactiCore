# S4B ERC ETF transfer V1

**Decision: `BLOCK_S4B_UPSTREAM_DEPENDENCY`.**

This is a pre-performance implementation block, not an ERC economic failure.  The current official Riskfolio-Lib release is 7.3.0 and declares `scipy>=1.16.1`.  A pre-freeze resolver check found that dependency cannot resolve across TactiCore's declared Python range `>=3.10,<3.13`, because the required SciPy version has no compatible Python 3.10 solution.  The trial dependency was deliberately reverted; the frozen project therefore has no `research` extra.

The external mapping remains `ERC_RISK_PARITY`, E2 established method, and its external evidence tier has not changed.  No Riskfolio API was invoked, no ERC target weights were calculated, and no historical performance, coverage, turnover, or comparator result exists.  In accordance with the frozen protocol, no local solver, older Riskfolio release, or dependency-range narrowing was substituted.

Reopen only if an official current upstream Riskfolio-Lib release can resolve reliably under TactiCore's declared Python environment; then create a new bounded protocol before any ERC historical transfer test.

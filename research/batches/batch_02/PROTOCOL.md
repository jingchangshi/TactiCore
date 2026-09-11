# Batch 02 protocol — Evidence-Informed Validation

Status: **FROZEN PENDING COMMIT A**.  This document contains no Batch 02 historical-performance result.  Starting commit is `eeca3038c504da1c07489ff713b7968285ed6d32`; the evidence snapshot is 2026-09-11.

## Common controls

- Canonical adjusted-price SHA-256: `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93`; calendar SHA-256: `ad942a3e1e3e3ae4b7703ea5319ec12793d484b4c49423181682357a1a9d7512`.
- VectorBT `0.28.5`, pandas `2.3.3`, numpy `1.26.4`.  VectorBT remains the simulator; no local portfolio accounting, execution engine, or optimizer is introduced.
- S2 R1 is read-only and remains `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`.  Its manifest SHA-256 is `e280c60b9a0698e6fd19a2f268913dbb7ac42492b2062e5f3268d2a61bc4326f`.
- The external evidence gate is [EVIDENCE_GATE.md](EVIDENCE_GATE.md).  It uses `VOL_SCALED_TREND` (E3), `ERC_RISK_PARITY` (E2), and `VOL_TARGETING` (E3), including the Kim/Tse/Wald and Cederburg contradictions.  Local historical outcomes cannot change those external tiers.
- After the freeze commit, changing a parameter, timing rule, comparator, or decision threshold is forbidden.  A demonstrated correctness defect requires an invalid-run record and a new protocol freeze before rerunning that affected track.

## A. S27A robustness

Question: does the baseline S27A inverse-vol active sizing survive a limited, one-factor-at-a-time local stability test, rather than merely reflecting a narrow 200/60 result?

The frozen baseline files are not modified: `config/s27_trend_inverse_vol.toml` SHA-256 `4d5f96a7d1e1c7b38df18d53157601fc6055b18091cab1702f74b129e63e517c`, `tacticore/strategies/trend_inverse_vol.py` SHA-256 `83f52203617af70284db3e0b9df0bf6d4d1702a914344c107528508dc2d3d203`, and the baseline report SHA-256 `da90cc8fce4d1565a05205bd9dedd1df3ac3a648a018ce3277a0ac91c2b59841`.

`run_s27a_robustness.py` SHA-256 `1216856f9080df6bc2f4c6efde42972ca1297fb708cc3a87108fa93075ad2fe3` keeps the generalized target formula in the experiment layer.  At 200/60 it must reproduce the frozen baseline CAGR `0.0778665897002686` within `1e-12`; failure produces `BLOCK_S27A_ROBUSTNESS_REPRODUCTION` and no interpretation of neighbor results.

- Signal: month-end 200-valid-observation trend, next canonical observation execution, S2 risk universe and `511010.SS` fallback.  Positive sleeves retain the S27A `P/9` total risk budget and are inverse-vol weighted using valid daily returns.  Fees/slippage are 10/5 bps.
- Trend dimension only: `(trend_window, vol_window)` = `(160,60)`, `(180,60)`, `(200,60)`, `(220,60)`, `(240,60)`.
- Volatility dimension only: `(200,40)`, `(200,60)`, `(200,80)`; the central case is not duplicated in output.  This is not a 5×3 grid and 200/60 stays the baseline whatever the results.
- Fixed periods are exactly 2013-03-29–2016-12-31, 2017-01-01–2019-12-31, 2020-01-01–2022-12-31, and 2023-01-01–2026-08-31.  Rolling 3Y/5Y uses the existing S2 month-end methodology.
- Cost cases use the existing S2 definition: VectorBT native per-side `fees` only, `slippage=0`, at 15/30/50 bps.
- Primary comparator is the read-only S2 V2B fixed-sleeve trend reproduction: same universe, trend state, signal/execution timing and risk-budget semantics; only active-sleeve sizing differs.  S30's frozen annual static 25/25/25/25 result is contextual only, not a gate.

Decision is only `ADVANCE_S27A_TO_EXECUTION_REVIEW`, `REJECT_S27A_ROBUSTNESS`, or `BLOCK_S27A_ROBUSTNESS_REPRODUCTION`.  Advance requires: successful reproduction; all five trend CAGRs positive and at least four retain at least 70% of baseline CAGR and Sharpe with MaxDD > -25%; all three volatility cases have positive CAGR/Sharpe and MaxDD > -25%, with at least two retaining 80% of baseline Sharpe; every fixed period CAGR positive; each 3Y positive-CAGR share >=90% and each 5Y share >=95%; and 50-bps CAGR >0 plus Sharpe >=0.50.  No RQAlpha run is authorized.

## B. S4B canonical ERC transfer

Question: can the official upstream ERC implementation be reliably installed before testing whether correlation-aware sizing adds value to S4A's eligible inverse-vol allocation?

External method evidence is E2, but the local implementation is blocked before historical performance: a pre-freeze resolver check for Riskfolio-Lib 7.3.0 found its official dependency `scipy>=1.16.1` cannot be resolved by this repository's declared Python range `>=3.10,<3.13`.  The trial extra was deliberately reverted, so no `research` extra is present in the frozen project.  The frozen decision is **`BLOCK_S4B_UPSTREAM_DEPENDENCY`**.  No local ERC solver, old-package substitution, dependency-range narrowing, Riskfolio API call, or historical ERC run is permitted.

Were the official dependency available, the predeclared transfer would use S4A's eligible set, 60 aligned daily returns requiring 61 common price observations and at least six assets, then official Riskfolio long-only vanilla ERC target weights at month end and next-observation execution.  Inverse-vol and equal-weight would be primary controls.  This specification is recorded solely to delimit the blocked question; it is not an authorization to implement it.

## C. S10A unlevered volatility targeting

Question: after controlling for monthly rebalance mechanics, does a single no-leverage, volatility-managed version of S30 add local value?

`config/s10a_vol_targeting.toml` SHA-256 `4ef87e42e130b14b8174f391a412969f5543af37c807d3e2930c8c89015d5f0f` and `tacticore/strategies/volatility_targeting.py` SHA-256 `5fa2d2f22ddaa36726ce64da8f19ec7c75a8b174f0c9a2ccd7aad71497d6cc51` define exactly one specification: 510300/513500/518880/511010 at 25% each, 20 valid aligned daily base-portfolio returns, annual target volatility 10%, scale bounded [0,1], monthly signal and next-observation execution.  If volatility is unavailable, scale is zero.  Risk assets receive `0.25 * scale`; bond receives `0.25 * scale + (1 - scale)`; weights therefore sum to one without leverage.

The primary comparator is `MONTHLY_STATIC_25_25_25_25`, with the same signal dates, next-observation monthly executions, fees (10 bps), slippage (5 bps), capital, and data.  Annual S30 is context only.  Required diagnostics are realized volatility, scale, risk reduction, bond weight, scale summary statistics, scaled-down months, target-change months, and turnover.

Decision is only `ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS`, `REJECT_S10A_VOL_TARGETING`, `REJECT_S10A_FILTER_DEGENERATION`, `REJECT_S10A_DEFENSIVE_DEGENERATION`, or `BLOCK_S10A_DATA`.  Average scale >=.95 first rejects as filter degeneration; <=.40 rejects as defensive degeneration.  Otherwise advance requires CAGR >0, Sharpe >=.80, MaxDD >-25%; MaxDD improvement over the monthly-static control >=2 percentage points; CAGR no worse than 1.5 percentage points below it; and strictly higher Sharpe or Calmar.  No alternative target volatility or lookback will be tried after results.

## Freeze checks

Synthetic tests cover S27A's experiment/frozen formula equivalence and both tracks' decision boundaries.  The initial implementation checksums are `run_s27a_robustness.py` `1216856f9080df6bc2f4c6efde42972ca1297fb708cc3a87108fa93075ad2fe3` and `run_s10a_vol_targeting.py` `46a5560294e428aad6e2b56a5aad6c916966ea3d1d87f1d8e706ce7a34e64c15`.  Commit A is contingent on `uv sync --extra dev`, test/lint/format/type checks, and the S2 R1 candidate verifier all passing; no Batch 02 runner is invoked by those checks.

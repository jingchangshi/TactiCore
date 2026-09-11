# Batch 01 frozen protocol — BATCH_01_DIVERSE_TRANSPARENT_BASELINES

## Identity and evidence boundary

- Starting HEAD: `4c04e3518a96335daac1557c0542671ea2eaf6c7`.
- Scope: five predeclared **historical economic screens**.  They are neither OOS nor prospective validation.
- S2 R1 remains `FROZEN / PROSPECTIVE_SHADOW_ACTIVE`; its files and decision record are read-only. RL-018 S3A and RL-019 S3B stay rejected and are not tuned or reopened.
- No new download, parameter search, robustness test, RQAlpha validation, Theme Rotation, generic framework, or custom backtester is permitted.

## Frozen datasets and environment

| Dataset | Price SHA-256 | Calendar SHA-256 | Provenance SHA-256 |
| --- | --- | --- | --- |
| multi-asset `data/canonical/` | `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93` | `ad942a3e1e3e3ae4b7703ea5319ec12793d484b4c49423181682357a1a9d7512` | `7af2e21890080cec4a4d2ed08a0bd9c6c89fae666fe98d866e33e55837a8d4e3` |
| sector `data/canonical/s3_sector_rotation_v1/` | `337c28cc52c04f8b5257a8feffb7d1c508248cab10595466c8c69d758556a4a6` | `13f4240ee6531415e3ea7638d9691af01290e97da3607446246d3dc8f96e51e6` | `31a6b9870e485e317781f5cc05cccc87f1ac97af9cf0400592445e540fa40a0c` |

Python 3.11.15; VectorBT 0.28.5; pandas 2.3.3; NumPy 1.26.4.  All simulations use the existing `run_target_weights` VectorBT adapter, 10 bps fees, 5 bps slippage, and 1,000,000 initial cash. Evaluation begins at the first executable target after each strategy's first valid signal (S30 at its first common valid date).

## Frozen hypotheses, comparators, and gates

| ID | Exact semantic | Primary comparator | Decision gate |
| --- | --- | --- | --- |
| S3C_V1 | 11 sector ETFs from frozen sector universe; 120-valid-observation momentum at month-end; positive gets fixed 1/11, negative/unavailable transfers 1/11 to 511010; next observation and SIGNAL_CHANGE_ONLY | availability-aware ungated fixed 1/11 sector basket | coverage ≥8 in ≥80%; CAGR>0, Sharpe≥.45, MDD>-.35, changes/year≤10; MDD +5pp, CAGR sacrifice≤1.5pp, Sharpe and Calmar strictly higher; average risk 30%–95% |
| S4A_INVERSE_VOL_V1 | S2 frozen risk universe, excluding fallback; monthly 60-valid-return standard deviation; signal-day price and 60 returns required; ≥6 gets normalized 1/vol, otherwise 100% 511010 | same eligible set/minimum coverage, equal-weight | coverage≥80%; CAGR>0, Sharpe≥.45, MDD>-.35; MDD +3pp, CAGR sacrifice≤1.5pp, Sharpe +.03; report concentration warning if >50% in >5% months |
| S8A_EQUITY_BOND_TREND_V1 | only 510300/511010; 200-valid-observation equity momentum at month-end; positive=100% equity, non-positive/unavailable=100% bond; next observation, SIGNAL_CHANGE_ONLY | 510300 buy-and-hold and annual-rebalanced 50/50 equity/bond | CAGR>0, Sharpe≥.45, MDD>-.35, changes/year≤6; versus equity MDD +10pp, CAGR sacrifice≤2pp, Sharpe/Calmar higher; beat static in ≥2 of 4 and no worse MDD |
| S27A_TREND_INVERSE_VOL_V1 | S2's 200-valid-observation moving-average trend state, same nine assets and fallback; positive P assets receive total P/9 risk budget distributed by 60-valid-return inverse vol; next observation monthly targets | frozen S2 V2B read-only reproduction, explicitly `COMPARATOR_REPRODUCTION_ONLY` | CAGR≥5%, Sharpe≥.60, MDD>-.30; CAGR no worse by 1pp, MDD no worse by 2pp, Sharpe strictly higher, Calmar no lower, turnover≤1.5×S2 |
| S30_REFERENCE_V1 | 510300, 513500, 518880, 511010 fixed 25% each, first common valid date then annual year-end-close/next-observation rebalance | none | `REFERENCE_BASELINE`, no pass/fail |

All targets are long-only and sum to one. S3C preserves `UNAVAILABLE` separately from `NEGATIVE_SIGNAL`; it does not rank or renormalize positives. S4A and S27A contain no caps, covariance, optimizer, or risk-budget solver. S30 weights do not depend on returns.

## Frozen implementation identities

| File | SHA-256 |
| --- | --- |
| `config/s3_sector_sleeve_trend.toml` | `545e5ea9d7adcfd3becc8f29e2773e0ab5d21da1454c620177848af2a0c57632` |
| `config/s4_inverse_vol.toml` | `387c539e7de8f6ffaa87ce47f5b90cc646d3cda22c9a508ec83e86682ae72570` |
| `config/s8_equity_bond_trend.toml` | `e5bb47019d0a612aeb4210439e93625e7d965798321818373b24fb827622259e` |
| `config/s27_trend_inverse_vol.toml` | `4d5f96a7d1e1c7b38df18d53157601fc6055b18091cab1702f74b129e63e517c` |
| `config/s30_static_allocation.toml` | `774fa1b2416e0cbb09dc4891a65ff1073655bebf9252a51fa85671199f35a142` |
| `tacticore/strategies/china_sector_sleeve_trend.py` | `301b62f774827be185e4674eca2ecbe74ca8dfa2110078438b0c556f84ac6c6b` |
| `tacticore/strategies/inverse_vol_allocation.py` | `4c8ef68dc9d9bcbb341981a6f634286062d7128e641d0ff14030402739145c56` |
| `tacticore/strategies/equity_bond_trend.py` | `c212cfea9a6aaa0f11b02a47b7a57e650d408f020cae608f30ecc746632bd67a` |
| `tacticore/strategies/trend_inverse_vol.py` | `83f52203617af70284db3e0b9df0bf6d4d1702a914344c107528508dc2d3d203` |
| `tacticore/strategies/static_strategic_allocation.py` | `c36036b07bc46eb9bfcb32fcd654a13b41bfbef3490391b25010c42458b717c6` |

Known provenance: S3C follows already observed S3A/S3B evidence; S27A follows S2 evidence. These hypotheses remain historical follow-ups, not new OOS evidence. After the protocol-freeze commit, a correctness defect requires invalidating observed outputs, a revision, and a new freeze SHA before execution.

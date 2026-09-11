# S27A robustness V1

Frozen by Batch 02 Protocol commit `3e220075e9da2ca4f7373beeadc98a92273aa16c`.  This is a historical local robustness adjudication, not OOS, prospective, or an authorization to run RQAlpha.

The experiment-layer evaluator exactly reproduced the corrected 200/60 baseline: CAGR `7.7867%` (tolerance `1e-12`), MaxDD `-12.5034%`, and Sharpe `1.0150`.  This passes the required reproduction gate.

| Case | CAGR | MaxDD | Sharpe | Calmar |
| --- | ---: | ---: | ---: | ---: |
| 160 / 60 | 7.60% | -11.85% | 1.016 | 0.641 |
| 180 / 60 | 7.82% | -12.50% | 1.029 | 0.625 |
| **200 / 60 baseline** | **7.79%** | **-12.50%** | **1.015** | **0.623** |
| 220 / 60 | 7.97% | -12.50% | 1.031 | 0.637 |
| 240 / 60 | 7.85% | -12.50% | 1.017 | 0.628 |
| 200 / 40 | 7.78% | -13.05% | 1.019 | 0.596 |
| 200 / 80 | 7.58% | -12.95% | 0.985 | 0.586 |

All five trend cases have positive CAGR; all retain at least 70% of the central CAGR and Sharpe, with MaxDD above -25%.  All 40/60/80-volatility cases have positive CAGR/Sharpe, MaxDD above -25%, and retain at least 80% of central Sharpe.  Every predeclared fixed period is positive CAGR (the weakest is 160/60 in 2020–2022 at 4.53%).  Every predeclared 3Y and 5Y rolling positive-CAGR share is 100%.

At the frozen S2-style 15/30/50-bps per-side fee-only cases, central S27A CAGR/Sharpe are 7.79%/1.015, 7.27%/0.953, and 6.58%/0.869.  The 50-bps gate passes.

| Contextual series | CAGR | MaxDD | Sharpe | Turnover |
| --- | ---: | ---: | ---: | ---: |
| S27A 200 / 60 | 7.79% | -12.50% | 1.015 | 23.69 |
| S2 V2B fixed sleeve | 6.16% | -26.18% | 0.628 | 25.50 |
| S30 annual static reference | 9.92% | -15.04% | 1.114 | 1.00 |

Against the mechanism-matched S2 control, S27A has higher historical CAGR/Sharpe and materially lower drawdown at somewhat lower turnover.  It does not beat S30's CAGR or Sharpe; S30 is contextual rather than a gate.  The narrow conclusion is that inverse-vol active sizing is stable in this predeclared neighborhood, not that it is a new anomaly or a production-ready strategy.

**Decision: `ADVANCE_S27A_TO_EXECUTION_REVIEW`.**

Artifacts: [summary](s27a_robustness_summary_v1.csv), [fixed periods](s27a_robustness_periods_v1.csv), [rolling shares](s27a_robustness_rolling_v1.csv), [costs](s27a_robustness_costs_v1.csv), and [comparators](s27a_robustness_comparators_v1.csv).

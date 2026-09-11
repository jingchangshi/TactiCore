# S10A unlevered volatility targeting V1

The first post-freeze run is invalidated in [INVALID_RUN_BATCH_02_R1](INVALID_RUN_BATCH_02_R1.md): pandas' implicit forward fill conflicted with the specified valid aligned-return semantics.  Protocol V2 (`bea032742c872d7d06b7c3ba28196ad09897821c`) corrected only that defect with `pct_change(fill_method=None)` and froze the same parameters, comparator, costs, timing, and gates before the single rerun below.

| Series | CAGR | MaxDD | Sharpe | Calmar | Turnover |
| --- | ---: | ---: | ---: | ---: | ---: |
| S10A 20-day / 10% unlevered | 8.30% | -10.56% | 1.122 | 0.786 | 8.78 |
| Monthly static 25/25/25/25 | 8.42% | -13.30% | 1.007 | 0.633 | 1.00 |
| S30 annual static context | 9.92% | -15.04% | 1.114 | 0.660 | 1.00 |

S10A meets the absolute gates (positive CAGR, Sharpe >=0.80, MaxDD >-25%).  Relative to the timing-matched monthly static control, MaxDD improves by 2.74 percentage points, CAGR is only 0.12 percentage point lower (within 1.5 points), and both Sharpe and Calmar are strictly higher.

Using all 171 executed monthly signal states (including the protocol-mandated zero scale before volatility becomes available), average scale is `0.8334`, median `1.0000`, minimum `0`, maximum `1.0000`; 57 months have scale below one and 54 months change target scale.  It therefore avoids both degeneration filters.  The mechanism is reduced risk exposure routed to the bond sleeve; it does not establish a free-standing volatility-management premium and it does not outperform annual S30 CAGR.

**Decision: `ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS`.**

Artifacts: [comparison](s10a_vol_targeting_comparison_v1.csv) and [monthly diagnostics](s10a_vol_targeting_diagnostics_v1.csv).

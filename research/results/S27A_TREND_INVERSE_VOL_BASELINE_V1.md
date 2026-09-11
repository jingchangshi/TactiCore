# S27A trend plus inverse-volatility baseline V1

Historical follow-up economic screen only, not OOS/prospective evidence. Corrected protocol freeze: `ae218d70b73adac1922a0c761cd74ab6e02bf955`; the R1 comparator defect and V2 correction are disclosed in [INVALID_RUN_BATCH_01_R1](INVALID_RUN_BATCH_01_R1.md).

S27A preserves S2's 200-valid-observation trend state and P/9 total risk budget, but distributes only positive sleeves by 60-valid-return inverse volatility. The S2 comparison is a read-only `COMPARATOR_REPRODUCTION_ONLY`, not a new S2 decision.

| Series | CAGR | MaxDD | Sharpe | Calmar | Turnover |
| --- | ---: | ---: | ---: | ---: | ---: |
| S27A | 7.79% | -12.50% | 1.015 | 0.623 | 23.69 |
| S2 V2B reproduction | 6.16% | -26.18% | 0.628 | 0.235 | 25.50 |

All predeclared S27A absolute and relative gates pass. **`ADVANCE_S27A_TO_ROBUSTNESS`** closes only this baseline question; it does not change S2 R1 or authorize execution/prospective candidacy.

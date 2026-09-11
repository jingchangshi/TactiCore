# S27A trend plus inverse-volatility baseline V1

Historical follow-up economic screen only, not OOS/prospective evidence. Frozen protocol: `0d245b984108224623638301ada2de727277e7e4`; multi-asset canonical price SHA `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93`.

S27A preserves S2's 200-valid-observation trend state and P/9 total risk budget, but distributes only positive sleeves by 60-valid-return inverse volatility. The S2 comparison is a read-only `COMPARATOR_REPRODUCTION_ONLY`, not a new S2 decision.

| Series | CAGR | MaxDD | Sharpe | Calmar | Turnover |
| --- | ---: | ---: | ---: | ---: | ---: |
| S27A | 7.79% | -12.50% | 1.015 | 0.623 | 23.69 |
| S2 V2B reproduction | 6.30% | -26.18% | 0.654 | 0.241 | 25.50 |

All predeclared S27A absolute and relative gates pass. **`ADVANCE_S27A_TO_ROBUSTNESS`** closes only this baseline question; it does not change S2 R1 or authorize execution/prospective candidacy.

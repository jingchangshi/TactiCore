# S4A inverse-volatility baseline V1

Historical economic screen only. Frozen protocol: `0d245b984108224623638301ada2de727277e7e4`; multi-asset canonical price SHA `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93`; config/source identities are in [Batch protocol](../batches/batch_01/PROTOCOL.md).

S4A uses the frozen nine S2 risk assets, 60 valid daily-return volatility, monthly next-observation inverse-vol targets, and 100% 511010 fallback below six eligible assets. Its identical-eligibility comparator is equal weight.

| Series | CAGR | MaxDD | Sharpe | Calmar | Turnover |
| --- | ---: | ---: | ---: | ---: | ---: |
| S4A | 10.88% | -22.48% | 0.981 | 0.484 | 10.06 |
| eligible equal weight | 9.96% | -22.33% | 0.819 | 0.446 | 2.38 |

S4A improves CAGR and Sharpe, but its drawdown is 0.15pp worse, rather than the required 3pp improvement. **`REJECT_S4A_BASELINE`**. The screen does not justify caps or optimizer variants; concentration diagnostics are retained in `s4a_inverse_vol_diagnostics_v1.csv`.

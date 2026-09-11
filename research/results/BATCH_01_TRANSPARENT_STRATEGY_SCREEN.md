# Batch 01 transparent strategy screen

Corrected protocol freeze: `ae218d70b73adac1922a0c761cd74ab6e02bf955`. All figures are historical economic screens on frozen canonical data, not OOS or prospective validation. The initial S27A comparator run was invalidated and rerun under Protocol V2; see [disclosure](INVALID_RUN_BATCH_01_R1.md).

| Strategy | Mechanism | CAGR | MaxDD | Sharpe | Calmar | Turnover | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| S3C | local sector trend | 4.89% | -26.05% | 0.470 | 0.188 | 14.00 | REJECT |
| S4A | inverse-vol risk allocation | 10.88% | -22.48% | 0.981 | 0.484 | 10.06 | REJECT |
| S8A | equity/bond timing | 1.80% | -51.92% | 0.193 | 0.035 | 22.00 | REJECT |
| S27A | trend + inverse vol | 7.79% | -12.50% | 1.015 | 0.623 | 23.69 | ADVANCE |
| S30 | static diversification | 9.92% | -15.04% | 1.114 | 0.660 | 1.00 | REFERENCE |

Return prediction/timing did not add value here: S3C and S8A fail decisively. Pure inverse-vol sizing (S4A) improved return and Sharpe but missed its required drawdown improvement. S27A improves materially on its frozen S2 comparator, but its higher turnover and historical follow-up provenance require robustness before any further decision. S30 is a formidable simple hurdle: it exceeds S27A on Sharpe, Calmar, drawdown and maintenance, while S27A provides a lower raw-CAGR but different trend-following exposure.

S27A is the only baseline gate pass. It is not an S2 replacement: S2 R1 remains the only prospective candidate. No strategy was called prospective/OOS, and no Batch 02 work is authorized.

Architecture-drift audit: S2 frozen inputs modified **NO**; S3A/S3B reopened **NO**; rejected strategies tuned **NO**; parameter sweeps **NO**; cross-strategy redesign **NO**; post-freeze protocol modification **NO**; redownload **NO**; framework/backtester/RQAlpha/Theme/production infrastructure **NO**; ARCHITECTURE/RESEARCH_RULES changes **NO**.

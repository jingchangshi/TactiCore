# Batch 02 — Evidence-Informed Validation

Starting HEAD: `eeca3038c504da1c07489ff713b7968285ed6d32`.  Protocol freeze: `3e220075e9da2ca4f7373beeadc98a92273aa16c`; S10A correctness-protocol V2: `bea032742c872d7d06b7c3ba28196ad09897821c`.

| Track | Evidence tier / action | Local question | Decision |
| --- | --- | --- | --- |
| S27A robustness | E3 / local adjudication | Is inverse-vol active sizing stable? | `ADVANCE_S27A_TO_EXECUTION_REVIEW` |
| S4B ERC | E2 / upstream compare | Can canonical ERC be reliably transferred? | `BLOCK_S4B_UPSTREAM_DEPENDENCY` |
| S10A vol target | E3 / local adjudication | Does unlevered vol targeting add value after monthly control? | `ADVANCE_S10A_VOL_TARGETING_TO_ROBUSTNESS` |

S27A reproduced its corrected baseline and passed every predeclared parameter, fixed-period, rolling, and 50-bps cost gate.  Its improvement over the S2 fixed-sleeve comparator is stable locally, while S30 remains better in historical CAGR and Sharpe; the result earns execution-review eligibility only, not RQAlpha, production, or prospective status.

S4B did not turn a software availability claim into an economic conclusion.  The official current upstream dependency cannot satisfy this project's supported Python range, so no ERC implementation or performance claim was made.

S10A's valid V2 rerun improved monthly-static MaxDD by 2.74 points and Sharpe/Calmar while sacrificing 0.12 CAGR points.  Its average scale is 0.833, so the outcome is consistent with an active risk-reduction mechanism rather than a no-op filter.  The Moreira/Muir support and Cederburg et al. contradiction remain external context; neither has been settled by this local ETF result.

## Architecture drift audit

All answers are **NO**: S2 R1 was not modified; rejected S3/S4A/S8A questions were not reopened or tuned; no Cartesian search or best-parameter choice occurred; no local ERC solver was written; upstream implementation was not confused with evidence; contradictory volatility evidence was retained; no leverage, RQAlpha, MinVar/HRP/theme work, cross-track tuning, external-tier revision, or generic research infrastructure was added.

**Batch status: `BATCH_02_COMPLETE` — `AWAIT_BATCH_02_ARCHITECT_REVIEW`.**

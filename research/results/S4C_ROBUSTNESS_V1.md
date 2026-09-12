# S4C bounded robustness V1

固定 skfolio `RiskBudgeting` / variance / long-only equal-risk-budget、min eligible 6、PIT fallback、月末估计和下一 observation execution。唯一变动为 aligned returns window 40/60/80（价格 41/61/81）；每个 case 均用同 eligible set、execution dates、成本构造 ERC、inverse-vol 与 equal-weight。60-return center 严格重现 Batch 04 corrected baseline。

ERC 三窗口均为正 CAGR / Sharpe、signed MaxDD 优于 -30%：40 为 11.3272% / 1.064 / -17.9772%，60 为 11.6375% / 1.091 / -18.3512%，80 为 11.4794% / 1.074 / -18.7446%。三者相对 aligned inverse-vol 均满足 CAGR 不低于 1.5pp、MaxDD 不差 2pp，且 Sharpe 至少高 0.02 或 Calmar 至少高 0.03。中心四个固定 periods CAGR 均为正，3/4 的 Sharpe 或 Calmar 高于 inverse-vol；3Y/5Y positive-CAGR share 均为 100%，3Y Sharpe-or-MaxDD improvement share 为 100%。中心 50bps 成本 CAGR 11.0087%、Sharpe 1.038，通过 gate。

集中度是证据而非事后 cap 触发器：median maximum weight 26.94%，P95 51.84%，最大 66.35%，9 个月任一资产超过 50%；effective assets median 6.23、P05 3.24。因此 ERC 的收益并非无集中度依赖，后续 execution review 应保留该风险解释，不能通过添加 cap 改写本结果。

所有预注册 robustness gates 通过，决定为 **`ADVANCE_S4C_TO_EXECUTION_REVIEW`**。本批不运行 S4C RQAlpha。

机器可读证据：[summary](s4c_bounded_robustness_summary_v1.csv)、[periods](s4c_bounded_robustness_periods_v1.csv)、[rolling](s4c_bounded_robustness_rolling_v1.csv)、[costs](s4c_bounded_robustness_costs_v1.csv)、[concentration](s4c_bounded_robustness_concentration_v1.csv)。

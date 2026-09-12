# S27A RQAlpha execution review V2

Batch 05 以 PIT contract 自动截取后的 161 个 frozen targets 做 target-only replay。schedule SHA-256 为 `2eb56e58b3d051d8ec8de00e1b19733102911d743b0807b2fa162afd8a5ee542`，首个 execution date 为 2013-04-01；所有正权重已在本地 lifecycle 与 canonical price gate 下验证。VectorBT replay 严格重现 Batch 04 corrected baseline（CAGR 8.3014%、signed MaxDD -12.5034%、Sharpe 1.048、Calmar 0.664、turnover 23.5829）。

RQAlpha 6.3.0 只在 frozen execution dates 调用 `order_target_portfolio`，并启用原生账户、matching、10/5 bps、`partial_fill_on_insufficient_cash=true`。161/161 日期回放，无额外日期；CAGR 8.6003%、signed MaxDD -12.4761%、native Sharpe 0.622、turnover 23.5982、交易 995 笔、成本 77,220.54。平均 execution-date total absolute deviation 0.7285%，最大 9.5198%，material dates 3/161（1.86%），平均现金 0.2978%，cash rejection 0。没有单资产 >5pp target difference，故 material-difference 表为空；36 个 native cash-residual cancellation 属 native partial-fill 路径，未构成 rejection。

所有预注册 execution gate 均成立，决定为 **`ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW`**。这只获得独立 candidate-freeze review 资格；未创建 candidate、未开始 shadow、未替代 S2。

机器可读证据：[冻结 targets](s27a_pit_corrected_frozen_targets_v1.csv)、[native summary](s27a_rqalpha_execution_summary_v2.csv)、[tracking](s27a_rqalpha_execution_target_tracking_v2.csv)、[differences](s27a_rqalpha_execution_material_differences_v2.csv)。

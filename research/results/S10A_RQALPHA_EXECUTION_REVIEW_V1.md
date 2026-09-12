# S10A RQAlpha execution review V1

Batch 05 对 PIT-corrected 20/10、无杠杆 frozen schedule 做 target-only RQAlpha replay。161 个 targets 的 SHA-256 为 `0ff425706be648c7588edb68d6499cd2fa7868ca576d24be988c8296236c1ebd`，首个 execution date 为 2013-04-01；VectorBT 严格重现 Batch 04 corrected baseline（CAGR 8.8540%、signed MaxDD -10.5628%、Sharpe 1.158、Calmar 0.838、turnover 8.7790）。

RQAlpha 6.3.0 161/161 日期回放、无额外日期，CAGR 9.2496%、signed MaxDD -10.4483%、native Sharpe 0.721、turnover 9.8257、交易 532 笔、成本 33,804.61。平均 execution-date total absolute deviation 0.6239%，最大 9.9723%，material dates 1/161（0.62%），平均现金 0.2830%。没有单资产 >5pp target difference，material-difference 表为空。冻结 diagnostics 显示 scale<1 的月份 47，平均 frozen scale 0.8794，平均风险资产暴露 65.9584%、bond 暴露 34.0416%。

但 RQAlpha 原生事件记录到 **1 个 cash rejection**（另有 17 个 native cash-residual cancellation），违反预注册的零 cash-rejection gate；不采用本地 cash buffer、手工 sizing 或 retry 修补。因此决定为 **`DO_NOT_ADVANCE_S10A_EXECUTION`**，并停止在 execution review，不创建 candidate 或 shadow。

机器可读证据：[冻结 targets](s10a_pit_corrected_frozen_targets_v1.csv)、[native summary](s10a_rqalpha_execution_summary_v1.csv)、[tracking](s10a_rqalpha_execution_target_tracking_v1.csv)、[differences](s10a_rqalpha_execution_material_differences_v1.csv)。

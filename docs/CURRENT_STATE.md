# 当前状态

## 当前策略与决策

当前活动策略是 S2 多资产趋势 V2B。执行闭环的最终决策为 **ADOPT_UPSTREAM_RQALPHA_EXECUTION**：采用 RQAlpha 6.3 的原生 `partial_fill_on_insufficient_cash`，保留原有 `order_target_portfolio`，不实现本地现金预留。

S1 保持 `REJECT_S1`；S2 V1 保持已拒绝。历史结论见 [研究账本](RESEARCH_LEDGER.md)和 [策略目录](STRATEGY_CATALOG.md)。

## 当前阻塞

原先“资金不足整单拒绝 + `SIGNAL_CHANGE_ONLY` 持续留空”的主导阻塞已关闭。剩余 5 个显著偏离执行日主要涉及成交量限制及其组合级连锁影响，不再形成大面积现金留空；这属于已记录的次要摩擦，不阻塞进入稳健性研究。

## 最新决定性证据

冻结目标 CSV 仍为 103 个执行日，SHA-256 为 `9cc5a8e70751f274cb7c4f900784400bd8de684450833ba6d4034fd75ca70b61`。

RQAlpha 6.3.0 在不开原生开关时与 5.6.5 控制一致：34 个现金相关失败状态、34 个显著偏离执行日、72 个显著偏离检查月。开启原生能力后，现金整单拒绝降为 0，显著偏离执行日降为 5，现金权重大于 5% 的检查月由 49 降为 2；CAGR 为 6.88%，最大回撤为 -25.41%，没有实质破坏既有经济证据。

完整证据见 [S2 上游原生执行闭环报告](../research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md)。

## 下一项唯一研究方向

S2 进入粗粒度参数平台与稳健性研究。只检验 200 日附近具有经济含义的少量窗口，不加入现金缓冲、重试、no-trade band、波动率目标或 S3。

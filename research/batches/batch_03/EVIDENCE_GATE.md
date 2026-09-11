# Batch 03 外部证据门

快照日期：2026-09-11；本门禁先于任何 Batch 03 真实绩效运行。

## S27A

`VOL_SCALED_TREND` 仍为 E3。本轮不重做趋势或 sizing 的历史问题，只将 Batch 02 已冻结、已通过 robustness 的 200/60 目标表交由 RQAlpha 6.3 原生执行验证。

## S10A

`VOL_TARGETING` 仍为 E3。Moreira/Muir 的支持与 Cederburg 等的反证均不变；本轮只判定固定 20 日/10% 无杠杆规格在预声明邻域是否稳健，不能据此选择最优参数。

## S4C

S4B 的 Riskfolio-Lib 7.3.0 路径仍永久记录为依赖阻塞，未被改写。官方 skfolio 当前稳定版 1.0.6 声明 Python >=3.10；官方文档提供 `skfolio.optimization.RiskBudgeting`，可使用 `RiskMeasure.VARIANCE` 和默认等风险预算的 long-only 权重。对本项目加 `skfolio==1.0.6` 的隔离 dry-run resolver 在 Python 3.10、3.11、3.12 均成功，因此形成 S4C 的新 upstream implementation path。

skfolio 只负责 ERC 权重优化；VectorBT 仍负责模拟、成交、收益、回撤和记录。ERC 外部层级仍为 E2，软件可用不构成任何经济优越性主张。

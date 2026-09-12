# S4C PIT correctness revalidation V1

S4C 的 10 个早期 `<6 eligible → 100% fallback` target 在 511010.SS 上市前不可执行；按 contract 它们不是现金、替代债券或可静默跳过的持仓。修正 inception 自动为 2013-04-01。

保持 skfolio `RiskBudgeting`、61 价格/60 收益、min 6、同 eligible controls 和 10/5 bps，ERC corrected CAGR 为 11.6375%、MaxDD -18.3512%、Sharpe 1.091、Calmar 0.634，风险覆盖 92.55%。原 ERC transfer 的经济资格恢复为 `RESTORE_S4C_ROBUSTNESS_ELIGIBILITY`；没有启动 robustness，也没有改写 S4B Riskfolio dependency block。

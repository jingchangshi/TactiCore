# 从 DailyETF 继承的经验

TactiCore 继承研究知识，不复制旧系统。

## 我们保留什么

- 收益率和复权语义必须明确，避免把价格序列的便利性误认为正确性。
- 所有信号必须防止前视，调仓日与信号观察日必须分开。
- 轮动和市场状态假设值得研究，但必须用样本外、成本与低换手约束审查。
- 真实可交易工具优先；指数和宏观序列只作为 benchmark、regime 或风险参考。
- 失败假设、数据陷阱和负面结果也是研究资产，应进入文档而不是被覆盖。

## 我们有意放弃什么

- 自研 backtest/reference/accounting/撮合引擎。
- 通用 provider capability、数据治理平面和经济语义引擎。
- 通用 experiment database、artifact lifecycle、frozen evidence 和 workflow DAG。
- 为未知未来需求准备的 broker、策略、存储或插件抽象。

## 为什么

这些设施会把工程投入从策略经济价值转移到平台正确性，而且 VectorBT 与 RQAlpha 已分别覆盖探索和权威事件驱动验证。只有具体策略被现有能力真实阻塞时，才允许记录 blocker 并增加最小 adapter。TactiCore 的衡量标准是更可信的 alpha、更低的换手和更好的风险收益，不是基础设施数量。

# 当前状态

## 一句话结论

TactiCore 已从空仓建立到 M0–M2 最小代码路径：可以对 12 个多资产 ETF 研究代理运行月频 Global Dual Momentum 的 VectorBT 研究；RQAlpha 逻辑已可表达，但权威事件驱动结果仍被仓库外市场数据 bundle 阻塞，因此目前只能证明“研究循环能运行”，不能证明策略有效。

## 已完成

### M0 Repository Bootstrap

- Python 3.10–3.12 项目，使用 `uv.lock` 固定可复现依赖。
- VectorBT、RQAlpha 为正式依赖；pytest、Ruff、mypy 为开发依赖。
- 最小包结构、测试、研究脚本与中文文档已建立。

### M1 Minimal Multi-Asset Universe

`config/universe.csv` 包含 12 个可交易研究代理，覆盖中国、美国、香港、日本/欧洲股票、黄金、商品、债券与现金。每项记录 `symbol`、`asset_class`、`region`、`currency`、`role`、`data_source`、`start_date`，并额外记录 RQAlpha 代码映射。

这些均是人民币交易的中国上市 ETF 研究代理，便于未来由同一 RQAlpha 中国市场 bundle 验证。它们不是已经获批的生产标的，也不代表完整全球资产暴露。

### M2 Global Dual Momentum Baseline

- 252 交易日绝对动量大于 0。
- 合格风险资产按相对动量排名，等权持有前 2 名。
- 无合格资产时持有国债 ETF 代理。
- 月末收盘产生信号，下一观测日执行；正常情况下每月最多一次组合调仓。
- 参数集中于 `config/strategy.toml`。

## 引擎现状

VectorBT adapter 能消费 canonical price DataFrame，执行目标百分比订单，并返回 equity、orders/trades 与 CAGR、最大回撤、Sharpe、Calmar、累计单边换手、交易次数、平均持有天数。默认演示输出只用于 smoke test。

RQAlpha adapter 使用共享排名函数，在每月第一个交易日读取不包含当日的 253 根历史日线，生成目标仓位并调用 `order_target_percent`。完整运行要求用户先在仓库外准备与 12 个 ETF 历史区间匹配的 RQAlpha 中国市场 bundle；仓库没有该 bundle，也没有下载或伪造数据。最小下一动作是准备 bundle 后调用 `run_rqalpha(...)`，再比较调仓日、标的、方向、权重、收益、换手与成本。

## 当前证据与限制

- 13 项自动测试覆盖排名、绝对过滤、缺失数据、无前视、月度执行、权重不变量、universe、VectorBT adapter、RQAlpha 缺少 bundle 时明确失败，以及 RQAlpha 使用历史数据和提交目标仓位的 callback 行为。
- 默认演示 smoke test 已实际输出 CAGR -21.2464%、最大回撤 -94.3146%、Sharpe -5.1238、Calmar -0.2253、累计单边换手 26.5、148 笔资产级交易、平均持有 100.72 天；这些刻意标注为非市场证据。
- 真实市场研究尚未执行，因此没有 CAGR 或稳健性主张。
- `start_date` 是工具上市日期元数据，不保证 Yahoo Finance 从该日提供完整可靠的复权价格。
- VectorBT 与 RQAlpha 尚未完成 differential validation；本机没有 `/home/jcshi/.rqalpha`，adapter 的实际前置检查得到 `RQAlpha bundle 目录不存在`，这是明确外部 blocker，且不会静默返回伪成功。
- 未完成最差年度、参数平台、regime、walk-forward、样本外与交易成本敏感性，这些依赖可靠真实历史价格。

## 架构漂移检查

- 是否在无策略 blocker 时建设基础设施：否。
- 是否复制 VectorBT：否，组合模拟由 VectorBT 完成。
- 是否复制 RQAlpha：否，订单、现金、费用和市场语义由 RQAlpha 完成。
- 是否为不足两个真实用例创建通用抽象：否。
- 是否让系统更难理解：否，只有 CSV contract、一个策略模块和两个薄 adapter。
- 是否增加未提升研究能力的维护负担：否。

因此 TactiCore 仍是 strategy-first，没有无意中重建 DailyETF。

## 唯一推荐下一方向

获取并冻结一份覆盖 canonical universe 的可靠真实复权价格集，然后对 S1 做 VectorBT 参数平台、walk-forward、样本外和成本敏感性研究。原因是当前最大不确定性是策略是否具有真实经济价值；在回答它之前，不应扩展 S2、S3 或任何基础设施。

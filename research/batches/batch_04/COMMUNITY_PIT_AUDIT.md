# Batch 04 社区 PIT 能力审计

- RQAlpha 6.3.0：本地已安装代码与官方文档的 `Instrument.listed_date`、`de_listed_date`、`listed_at()`、`de_listed_at()`、`active_at()` 一致；`active_at` 是上市且未退市。其 bundle `instruments.pk` 为当前中国 ETF 生命周期的交叉验证权威。
- Zipline：`AssetFinder.lifetimes()` / pipeline root mask 的 date × asset bool matrix 是本项目 mask 的架构参考；不引入 Zipline backtester。
- LEAN：`Security.IsTradable` 与 universe selection 的 pre-trade boundary 是语义参考；不引入 LEAN execution engine。
- Qlib：PIT database 解决财务报表修订的 as-of 数据问题，是未来 financial-data reference，不是当前 ETF lifetime dependency。

TactiCore 不需要 PIT engine、security master 或 dynamic-universe platform；只保存版本控制 universe 的轻量生命周期快照、由价格和生命周期构成的 mask，以及模拟器前的正目标验证。

来源：[RQAlpha Instrument](https://rqalpha.readthedocs.io/zh-cn/latest/_modules/rqalpha/model/instrument.html)、[Zipline lifetime mask](https://zipline.ml4trading.io/_modules/zipline/pipeline/engine.html)、[LEAN IsTradable](https://www.lean.io/docs/v2/lean-engine/class-reference/Extensions_8cs_source.html)、[Qlib PIT](https://qlib.readthedocs.io/en/stable/advanced/PIT.html)。

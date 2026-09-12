# TactiCore 架构

## 1. 系统边界

TactiCore 是策略优先的低频多资产配置研究系统。稳定链路为：

```text
外部策略证据
 ↓
本地证据缺口
 ↓
数据
 ↓
策略语义
 ↓
研究筛选
 ↓
执行验证
 ↓
证据与决策
 ↓
未来生产决策
```

系统只保留策略逻辑、薄编排和研究证据，不建设通用量化平台。

## 2. 所有权边界

| 领域 | 所有者 | 职责 |
| --- | --- | --- |
| 经济假设与信号 | TactiCore | 信号语义、目标组合、策略专用执行政策 |
| 数据契约 | TactiCore | canonical 格式、标的映射、来源与缺失语义 |
| 外部策略证据 | 外部原始研究 / 社区 | canonical 定义、实证证据、反证与既有实现方法 |
| 外部证据快照 | TactiCore | 有界整理、适用范围、层级、本地缺口与上游指针 |
| 快速研究 | VectorBT | 组合模拟、研究记录、收益/成交/回撤、参数与敏感性研究 |
| 权威执行 | RQAlpha | 订单 sizing、整手、撮合、现金、持仓、账户、成本、滑点、市场限制、公司行动与执行记录 |
| 证据与决策 | TactiCore | 薄框架编排、有界派生比较、研究报告与阶段决策 |

TactiCore 不拥有通用组合会计、撮合引擎、订单生命周期框架、通用执行模拟器、第三套回测引擎、通用数据平台或通用研究治理平台。

外部世界拥有论文、复制研究与社区实现本身；TactiCore 只在
[`STRATEGY_EVIDENCE_REGISTRY.yaml`](../research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml)
中作版本化、可审计的范围化综合。它不是文献爬虫、书目数据库、知识图谱或搜索服务。外部主张的权威顺序为原始发表 > 高质量独立复制/综述 > 原始实践研究 > 二级解释；registry 不能覆盖原始来源。仓库本地事实仍以源代码和冻结产物优先于说明文档。

## 3. 架构层次

### 3.1 数据

Tushare Pro 是 canonical 研究数据源；RQAlpha 官方 bundle 只提供权威中国市场执行语义。`config/universe.csv` 显式保存 Tushare、策略和 RQAlpha 代码映射。`data/canonical/` 保存价格、交易日历和来源清单；未知值保持缺失，不前向填充、不置零、不猜测。

数据能力必须由具体策略阻塞项驱动，不预建提供方抽象、缓存服务或历史主数据库。

### 3.0 外部证据与本地缺口

任何策略代码前先读取外部证据 registry 与
[策略研究地图](STRATEGY_RESEARCH_MAP.md)：先确定 canonical strategy、外部证据层级、反证、原始研究域、成熟上游实现及尚未被本地账本关闭的缺口。只有本地缺口才进入数据、策略语义和研究筛选；外部成功不是本地验证，本地失败也不否定全局文献。

### 3.0.1 Asset Lifecycle / PIT Tradability

RQAlpha instrument lifecycle 是中国标的上市/退市语义的上游交叉验证权威；canonical 价格决定 execution timestamp 是否可观察。TactiCore 只保存 version-controlled universe 的轻量生命周期快照、date × asset mask 与正目标验证，不建设 security master、PIT database 或动态 universe 平台。VectorBT 只能接收已验证合法目标；RQAlpha 仍拥有原生执行。

```text
External evidence → canonical data + asset lifecycle → PIT eligible universe
→ strategy semantics → target → tradability validation → VectorBT → RQAlpha
```

### 3.2 策略语义

`tacticore/strategies/` 拥有经济假设、信号时点和期望目标权重。信号只能使用当时已知的数据；收盘后形成的信号最早在下一观测日执行。策略状态与研究结论见 [策略目录](STRATEGY_CATALOG.md)，已关闭语义见 [研究账本](RESEARCH_LEDGER.md)。

### 3.3 研究筛选

`tacticore/engines/vectorbt_adapter.py` 只把策略生成的目标交给 VectorBT。VectorBT 负责快速组合研究、研究记录和稳健性实验；适配器不得复制其会计、成交或风险记录能力。

### 3.4 执行验证

RQAlpha 是事件驱动验证权威。TactiCore 可以冻结目标、映射代码、选择明确的原生配置/API、编排回放，并在决策所需时比较目标与 RQAlpha 原生持仓；不得实现订单 sizing、整手、撮合、现金、账户、成本或市场限制。

RQAlpha 与 VectorBT 无需逐比特一致。差异按框架的真实执行与会计语义解释，不增加第三套引擎仲裁。

### 3.5 证据与决策

小型派生 CSV 与完成报告保存在 `research/results/`。长期知识进入只追加的 `docs/RESEARCH_LEDGER.md`；策略状态进入 `docs/STRATEGY_CATALOG.md`；`docs/CURRENT_STATE.md` 只保存当前策略、决策、阻塞、最新决定性证据和下一项唯一实验。

`docs/goal.md` 仅是当前正在执行的 Goal，不是永久事实来源。来源层级为：

```text
ARCHITECTURE
+ RESEARCH_RULES
+ EXTERNAL STRATEGY EVIDENCE
+ RESEARCH_LEDGER
+ LOCAL RESEARCH ARTIFACTS
+ STRATEGY_CATALOG
+ CURRENT_STATE
→ 生成下一 Goal
```

### 3.6 未来生产决策

未来可以在候选策略通过研究和执行验证后生成低频持仓建议与“是否操作”报告。当前没有调度器、用户界面、券商抽象或生产交易系统，也不提前建设这些能力。

## 4. 版本感知的框架与社区优先

任何框架限制的本地绕行方案都必须遵循：

```text
已有 TactiCore 能力
 ↓
当前框架原生 API
 ↓
官方扩展 / Mod
 ↓
最新兼容框架版本
 ↓
最新稳定上游版本
 ↓
成熟社区实现
 ↓
最小 TactiCore 专用适配
```

采用上游版本前必须检查 changelog、API、必要的 issue/扩展点，并以冻结输入做兼容实验。不得因存在新版本就盲目升级；只有策略语义不变且当前阻塞被解决时才能采用。社区依赖还必须成熟、显著减少本地实现且不重复 VectorBT/RQAlpha。

## 5. 禁止的架构

禁止建设：

- 自定义回测、组合会计或交易执行引擎；
- 通用订单生命周期或摩擦分类框架；
- 通用数据、策略插件、引擎抽象或研究治理平台；
- 没有策略证据需求的抽象与依赖。

如果基础设施增长快于经济证据，应停止并简化。

# TactiCore 架构

## 1. 系统边界

TactiCore 是面向个人投资的独立策略研究与验证系统：围绕经济假设、外部证据、历史及前瞻检验，研究策略的有效性、适用环境、执行约束和失效条件，并交付可复现的证据。既有低频多资产配置仍是重要研究方向；长期范围扩展到个股和 ETF 的中期波段、趋势、反转与形态、行业轮动、基本面、市场状态、策略组合和风险管理，事件驱动可作为后续方向。这些是研究范围，不是已验证策略或已授权开展的实验。

稳定链路为：

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
研究证据、冻结与前瞻观察
 ↓
有界版本交付 → 独立生产准入 → FinanceMCP 账户决策
```

系统只保留策略逻辑、薄编排和研究证据，不建设通用量化平台。

## 2. 所有权边界

| 领域 | 所有者 | 职责 |
| --- | --- | --- |
| 经济假设与信号 | TactiCore | 信号语义、目标组合、策略专用执行政策 |
| 生产数据 | FinanceMCP | 市场数据采集、治理、标准化及版本化研究快照，作为生产数据事实源 |
| 研究数据契约 | TactiCore | 每项研究的冻结输入、canonical 格式、标的映射、来源、可得时间与缺失语义；既有契约保持原样 |
| 生产策略与账户决策 | FinanceMCP | 独立审核后运行获批准版本，测量市场环境、结合真实账户提出条件化预案；最终执行由投资者决定 |
| 外部策略证据 | 外部原始研究 / 社区 | canonical 定义、实证证据、反证与既有实现方法 |
| 外部证据快照 | TactiCore | 有界整理、适用范围、层级、本地缺口与上游指针 |
| 快速研究 | VectorBT | 组合模拟、研究记录、收益/成交/回撤、参数与敏感性研究 |
| 权威执行 | RQAlpha | 订单 sizing、整手、撮合、现金、持仓、账户、成本、滑点、市场限制、公司行动与执行记录 |
| 证据与决策 | TactiCore | 薄框架编排、有界派生比较、研究报告与阶段决策 |
| 前瞻证据收集 | TactiCore | 候选级 as-of 冻结、provenance 验证、薄编排、append-only 记录 |

TactiCore 不拥有通用组合会计、撮合引擎、订单生命周期框架、通用执行模拟器、第三套回测引擎、通用数据平台或通用研究治理平台。

外部世界拥有论文、复制研究与社区实现本身；TactiCore 只在
[`STRATEGY_EVIDENCE_REGISTRY.yaml`](../research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml)
中作版本化、可审计的范围化综合。它不是文献爬虫、书目数据库、知识图谱或搜索服务。外部主张的权威顺序为原始发表 > 高质量独立复制/综述 > 原始实践研究 > 二级解释；registry 不能覆盖原始来源。仓库本地事实仍以源代码和冻结产物优先于说明文档。

## 3. 架构层次

### 3.1 数据

既有研究以 Tushare Pro 为 canonical 数据源；RQAlpha 官方 bundle 提供对应中国市场执行验证语义。`config/universe.csv` 显式保存既有 Tushare、策略和 RQAlpha 代码映射，`data/canonical/` 保存冻结价格、交易日历和来源清单。既有历史基线、候选身份和候选专属前瞻 vintage 保持各自协议及来源，不因生产数据职责变化而覆盖或静默迁移。

FinanceMCP 是生产数据事实源，未来新研究可按具体问题逐步消费其版本化、不可变快照；每次接入须冻结来源、数据版本与 hash、字段及复权/证券映射、覆盖范围、缺失和修订语义，并核验与研究协议的适配。若改变既有候选的数据契约，须按原协议建立新版本，不能改写原候选或其证据。既有 Tushare downloader 和候选路径继续服务原协议，直到有明确的独立变更及验证。

研究输入须区分事件日、公告/发布时间、供应商更新时间、实际可得时间和交易日；只能使用决策时已可获得的对应 vintage，不能把事后修订当作当时已知。未知值保持缺失，不前向填充、不置零、不猜测。数据能力由具体策略阻塞项驱动，不预建提供方抽象、缓存服务或历史主数据库。

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

### 3.5.1 前瞻证据收集

前瞻证据收集是 TactiCore 自有的一小块职责：在候选已冻结并激活后，把未来真实数据固定成
不可回填、可机器验证的 prospective evidence。

```text
Tushare        拥有外部市场数据
TactiCore      拥有候选级 as-of 冻结、provenance 验证、薄证据编排、append-only 记录
strategy runner 拥有候选级信号语义
RQAlpha        拥有执行语义
Git            拥有版本化证据历史
```

该职责在本仓库内不拥有 scheduler、database、workflow engine、通用 event store、broker、
execution simulator 或研究治理平台。现有候选复用 Tushare downloader 与 RQAlpha 原生执行，
只做候选级、极薄的编排与验证；[RL-052](RESEARCH_LEDGER.md#rl-052-所有者授权仓库外月度编排器与有界迁移研究-goal) 已授权仓库外编排器调用冻结 CLI，其运行事实以当前状态和实际记录为准。

### 3.6 策略交付与生产准入

TactiCore 研究假设、对照、样本外、成本和执行、市场状态适用性及真实前瞻证据，决定研究候选是否冻结、继续观察、淘汰或建议交付。形态识别本身不是盈利证据；状态模型和策略选择规则同样需要验证。历史回测、外部文献、本地样本外和真正前瞻证据须分别标示，不能互相冒充。

研究成熟、冻结、前瞻影子激活及生产批准是不同阶段。候选达到其预注册的评审资格后，仍须独立生产准入审核，核验适用域、风险、成本、可执行性和证据；各策略的前瞻期限按协议确定。S2 R1 和 S4C R1 是冻结的活动前瞻影子候选，均非生产候选；其当前状态和阻塞以 [CURRENT_STATE](CURRENT_STATE.md) 及候选协议为准。错过的前瞻窗口不得回填，决策须在执行结果可观察之前封存。

目标接口已实现为有界、版本化的 `strategy-release-1` schema：`tacticore/strategy_release.py` 离线校验策略身份与版本、冻结规则和参数、数据来源与快照及时间范围、适用市场与环境、信号时点与最早执行及退出/费用/整手假设、证据引用及其内容哈希、研究状态及 `production_admission`（`NOT_APPROVED` / `APPROVED_FOR_ACCOUNT`）。schema 与校验器的存在**不**代表任何候选获得生产批准：批准责任人、审核标准与具体准入决定仍按策略独立作出，并记录在对应 release 与 [CURRENT_STATE](CURRENT_STATE.md) 中。FinanceMCP 只正式启用经批准版本，并对相同输入与版本验证信号语义一致；简单规则可经一致性验证移植，复杂策略可考虑隔离批处理，无需在线研究服务或通用插件平台。

FinanceMCP 可向 TactiCore 返回版本化的市场状态、信号、账户约束下的拒绝原因及后续表现，用于研究失效、暂停或退役建议；这些反馈不能改变已冻结的历史或伪造前瞻证据。日常机会比较、持仓与现金约束、条件化账户预案属于 FinanceMCP，最终交易由投资者决定。

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

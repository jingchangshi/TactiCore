# TactiCore 研究规则

以下约束对后续所有 Goal（目标）长期有效。

## 1. 使命与核心原则

TactiCore 是一个低频、多资产战术配置研究系统，使命是：

> 发现稳健、可解释、可执行的低频资产配置策略。

TactiCore 不以以下事项为目标：

- 建设通用量化平台；
- 开发新的回测引擎；
- 最大化样本内复合年化增长率（CAGR）；
- 建设复杂的基础设施。

核心原则：

```text
策略研究 > 基础设施工程
```

只有真实策略需求造成阻塞时才建设基础设施。每项功能都必须回答：

> 它是否提高了我们对策略有效性的信心？

如果不能，则不应实现。Goal 完成即停止，不顺手扩展下一阶段。

## 2. 架构规则

### 2.1 引擎职责

VectorBT 用于：

- 快速研究；
- 参数探索；
- 敏感性分析；
- 滚动前推（walk-forward）实验；
- 策略比较。

RQAlpha 用于：

- 事件驱动验证；
- 投资组合会计核算；
- 现金管理；
- 交易成本处理；
- 执行语义验证。

禁止建立：

- 第三套回测引擎；
- 自定义投资组合会计核算引擎；
- 自定义交易执行模拟器。

不要重复实现 VectorBT 或 RQAlpha 已承担的能力。

### 2.2 框架与社区能力检查（永久规则）

在编写回测、组合会计、订单、撮合、现金、费用、滑点、交易日历、复权、公司行动或绩效记录等通用能力前，必须依次检查：

1. TactiCore 已有代码；
2. VectorBT / RQAlpha 原生 API；
3. 官方 Mod 与文档化扩展点；
4. 最新兼容的框架发行版；
5. 最新稳定上游版本；
6. 成熟的社区实现；
7. 最小的 TactiCore 专用适配。

- VectorBT 优先使用 `Portfolio.from_orders`、returns accessor 以及 order、trade、drawdown records；
- RQAlpha 优先使用官方 bundle、instrument/history/scheduler/order API、analyser 以及 DataSource/Mod 扩展点；
- 薄适配器可以转换代码、字段或调用协议，但不得接管框架的通用职责；
- 框架原生能力不能满足具体策略研究问题时，才可增加范围明确的本地计算，并记录为什么不可避免及其口径；
- 实现框架绕行方案前，必须检查上游 changelog、API、必要的 issue/扩展点，判断较新受支持版本是否已解决问题，并用冻结输入做兼容实验；
- 不得因存在新版本而盲目升级；上游采用必须证明冻结策略语义未变；
- 不得仅因为社区依赖存在就引入它；依赖必须解决当前具体阻塞、显著简化本地实现、不重复 VectorBT/RQAlpha，并具备可接受的维护成熟度；
- 复制框架已有功能一律视为架构漂移，必须在合并前删除或给出不可替代的证据。

自定义实现永远是最后选项。TactiCore 拥有策略逻辑，VectorBT / RQAlpha 拥有通用量化基础设施。

## 3. 数据规则

数据流程：

```text
外部数据提供方
      ↓
规范化市场数据集
      ↓
策略研究
      ↓
验证
```

优先数据源：

- Tushare Pro；
- RQData；
- 其他可靠的市场数据源。

数据原则：

- 不得静默猜测缺失数据；
- 不得将未知值转换为零；
- 当缺失数据使资产退出合格池时，必须把“不可用”与“负信号”分开报告，不得把由数据缺口产生的降风险效果归因于策略；
- 没有真实市场数据时，不得声称已经获得策略有效性证据；
- 必须区分研究代理标的与生产交易标的；
- 优先使用可交易工具。

## 4. 策略开发规则

研究顺序：

```text
External Evidence Gate
   ↓
PIT Tradability Gate
   ↓
Canonical Strategy Mapping
   ↓
Local Evidence Gap
   ↓
经济假设
   ↓
策略实现
   ↓
回测
   ↓
稳健性验证
   ↓
生产候选策略
```

不得从基础设施建设开始。样本外证据的优先级高于样本内 CAGR。

### 4.2 PIT tradability 与指标符号

- 正目标权重只在 execution timestamp 上标的 active 且 canonical 价格有限、正值时合法；NaN 不表示现金、持有、跳过或 fallback。
- universe 必须 date-aware，今天的 ETF 不得回填至历史。策略 inception 是完整冻结 target 首次可以合法形成并执行的日期，而非 dataframe 首日或首个 signal。
- fallback 是完整 target contract 的一部分；其尚未可交易时没有可执行 target，除非冻结策略已明确另一语义。
- MaxDD 以负数保存；较少负值更好。`candidate >= comparator` 表示 no worse，决策代码必须使用集中 helper，而不是临时裸比较。

### 4.1 External Evidence / Literature Gate

任何新 strategy family、signal、allocator 或 tactical overlay 在写代码前必须回答：canonical name、是否已被研究、最强支持与反证、原始市场/资产/实现域、是否有成熟上游实现、对 TactiCore 的精确未解问题、该问题是否已被 `RESEARCH_LEDGER` 关闭、最简单隔离比较器及为何需要新代码。不能回答即 **NO STRATEGY CODE**。

先读 `research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml`；没有条目时先作有界文献审计再增加条目。行动词只用 `TRANSFER_VALIDATE`、`UPSTREAM_COMPARE`、`LOCAL_ADJUDICATION`、`NEW_HYPOTHESIS`、`REFERENCE_ONLY`、`DO_NOT_PURSUUE`，不是状态机。

- `E1_MATURE`：跨样本/市场的现象证据成熟；只研究本地 transfer，不重问其存在性。
- `E2_ESTABLISHED_METHOD`：构造方法成熟，未声称 alpha；优先上游比较。
- `E3_MIXED_CONDITIONAL`：支持与反证必须同列，作本地裁决。
- `E4_OPEN_LOCAL`：公开证据不足或高度依赖中国 ETF、PIT、流动性/执行；先证明合理检索未回答才可形成新假设。

层级不等于本地决定：E1 不自动 PASS，local REJECT 不推翻全局文献，local PASS 不提高外部层级。论文的期货、多空、杠杆或因子域不得被写成“已证明适用于长多中国 ETF”。每条 evidence snapshot 均需 `evidence_as_of`；只在相关 Goal 遇到重要新复制、反证或上游变化时刷新。

复杂策略必须回答“为什么不是更简单的适当 comparator？”比较器应隔离新增机制（如 1/N、S30、buy-and-hold、同 universe 等权或同风险暴露），而非强制一律战胜 S30。

未来 strategy Goal 须先写：canonical strategy、external tier/consensus/sources/contradictions、原始域与 TactiCore mismatch、upstream implementation、已有本地证据、remaining gap、research action；之后才可定义实现或实验。批次优先经济上正交的本地缺口；成熟策略称 Replication / Transfer Batch，不称 Discovery Batch。

### 4.1 经济正确性

- 信号只能使用当时已知的数据；月末收盘信号最早在下一交易日执行。
- 缺失动量的资产不得用零填充后参与排名。
- 目标权重必须非负，单项不得超过 100%，且每次调仓的目标权重合计必须为 100%。
- 任何策略结论都必须建立在真实历史数据上，不得从演示数据推断。

## 5. 低频约束

默认假设：

- 信号频率：每日；
- 调仓频率：每周、每月或更低；
- 预期交易频率：每月 0–4 次。

任何高换手或提高交易频率的设计都必须明确说明理由，并证明新增收益能够显著覆盖交易成本、执行复杂度和人工维护成本。

## 6. 评估规则

不得仅凭 CAGR 评价策略。策略比较至少必须报告：

- 复合年化增长率（CAGR）；
- 最大回撤；
- 夏普比率（Sharpe）；
- 卡玛比率（Calmar）；
- 最差年度表现；
- 换手率；
- 交易次数；
- 平均持有期；
- 参数稳定性；
- 市场状态稳定性；
- 滚动前推稳定性；
- 样本外稳定性；
- 交易成本敏感性。

当前基线适配器仅输出其中七项基础指标；其余指标必须在获得真实历史数据后完成，不能从演示数据推断。

选择策略时，应优先考虑：

```text
稳健 + 可执行 + 低维护
```

而不是：

```text
历史收益最高
```

## 7. 参数规则

不得优化并选择唯一的最佳参数，而应寻找参数平台，即相邻参数在合理范围内表现相近。

可接受的证据示例：

```text
回看期：80 / 100 / 120 / 140
各参数表现相近
```

应拒绝的证据示例：

```text
仅回看期 = 117 时表现良好
```

参数稳健性必须使用粗粒度、具有经济含义的邻域，并通过滚动前推和样本外区间检验参数平台。具体邻域属于各策略的研究计划，不应写入永久规则；任何透明基线都不代表最优参数声明。

## 8. 文档与完成规则

每个 Goal 完成时必须更新：

```text
docs/CURRENT_STATE.md
```

架构发生变化时还必须更新：

```text
docs/ARCHITECTURE.md
```

每份完成报告必须说明：

1. 改了什么；
2. 为什么修改；
3. 新增了什么能力；
4. 尚未解决什么；
5. 对架构有什么影响；
6. 下一项研究决策是什么。

`docs/goal.md` 只描述当前正在执行的 Goal，不承载永久架构、研究规则或已关闭结论。永久信息必须分别写入 `ARCHITECTURE.md`、`RESEARCH_RULES.md`、只追加的 `RESEARCH_LEDGER.md` 或 `research/results/`；`CURRENT_STATE.md` 只保留当前策略、决策、阻塞、最新决定性证据和下一项唯一实验。

生成新 Goal 的信息层级固定为：

```text
ARCHITECTURE
+ RESEARCH_RULES
+ EXTERNAL STRATEGY EVIDENCE
+ RESEARCH_LEDGER
+ LOCAL RESEARCH ARTIFACTS
+ STRATEGY_CATALOG
+ CURRENT_STATE
→ next Goal
```

研究账本只追加简短条目，不为其建设状态机、数据库或治理软件。关闭项只有在策略语义或 canonical 数据契约变化、框架变化使相关假设失效，或出现新矛盾证据时才能重开。

## 9. 前瞻候选与预注册规则

在任何真正前瞻结果产生前，候选必须冻结策略与执行语义、historical cutoff、prospective start、数据 vintage 规则、决策记录时点、评审资格以及重开/失效条件。前瞻 observation 必须严格晚于 historical cutoff；历史研究、滚动窗口和已查看区间只能称为历史证据，不能改称真正前瞻证据。

一旦已有前瞻 observation，不得根据看到的结果修改原候选、追溯改变旧 target decision、把新策略回填到旧前瞻期间，或静默以供应商修订替换旧 data vintage。任何实质变更都必须建立新的顺序候选版本，旧候选与其记录保持可复现。历史 canonical 基线保持冻结；后续数据只能作为候选专属、append-only 的 vintage 证据。候选完整性失效与策略表现偏弱必须分别记录，不能用短期收益或回撤触发隐形优化。

## 10. 提交与架构漂移检查

只有完成验证后才可提交并推送。

## 11. DailyETF 经验边界

继承以下内容：

- 策略思路；
- 风险管理思路；
- 市场状态概念；
- 失败实验的经验；
- 数据陷阱。

不继承以下内容：

- 自定义回测基础设施；
- 自定义会计核算；
- 过度复杂的治理框架。

## 12. 架构漂移检查

每次合并前必须检查：

- 是否正在重建 DailyETF？
- 是否正在重复实现 VectorBT？
- 是否正在重复实现 RQAlpha？
- 是否在没有策略需求的情况下增加基础设施？
- 这项变更是否提高了策略研究能力？

如果基础设施的增长速度超过策略证据的积累速度，应立即停止并简化。

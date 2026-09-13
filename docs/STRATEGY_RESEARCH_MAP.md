# 策略研究地图

## 用途与边界

本地图是 Principal/Agent 选择研究方向的入口；完整外部证据快照在 [registry](../research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml)。它不是书目数据库，也不把外部证据包装成本地验证。层级含义：E1 成熟现象（transfer）、E2 成熟方法（upstream compare）、E3 有条件/争议（local adjudication）、E4 高度本地的开放问题（new hypothesis）。

## 外部世界与本地结果

| Canonical Strategy | Family | Tier | External conclusion | TactiCore Mapping | Local Status | Remaining Gap | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Time-series momentum | trend | E1 | 多资产期货证据成熟，域不等于长多ETF | S2 | PROSPECTIVE_SHADOW_ACTIVE | 前瞻ETF transfer/执行 | TRANSFER_VALIDATE |
| Cross-sectional / dual momentum | trend | E1/E3 | 现象成熟，组合规则域敏感 | S1 | REJECTED | 仅独立新ETF问题 | LOCAL_ADJUDICATION |
| Industry momentum | trend | E1 | 行业股票文献成熟 | S3A | REJECTED | PIT ETF transfer | TRANSFER_VALIDATE |
| Aggregate breadth | tactical | E4 | 当前ETF universe本地定义 | S3B | REJECTED | 新问题才可研究 | NEW_HYPOTHESIS |
| Per-sector trend | tactical | E3 | trend transfer而非新异常 | S3C | REJECTED | PIT/工具域 | LOCAL_ADJUDICATION |
| Inverse volatility | allocation | E2 | 成熟风险配置，不是alpha | S4A | REJECTED | 简单比较器下复杂度 | UPSTREAM_COMPARE |
| Equity/bond tactical trend | tactical | E3 | GTAA相关但单规则域敏感 | S8A | REJECTED | 非S8A救援的新问题 | LOCAL_ADJUDICATION |
| Trend + inverse vol | composite | E3 | 成熟组件的组合 | S27A | candidate-freeze review eligible（deferred） | 独立候选冻结审查；与 S2 机制重叠，非前瞻/生产资格 | LOCAL_ADJUDICATION |
| Equal risk contribution | allocation | E2 | 成熟构造方法，非收益异常 | S4B blocked / S4C R1 | S4C R1 FROZEN / PROSPECTIVE_SHADOW_ACTIVE（observations = 0） | 第一条真实前瞻 decision 只能在 2026-09-30 及之后形成；集中度为已知候选风险而非待优化项，S4B block 保留 | UPSTREAM_COMPARE |
| Volatility targeting | overlay | E3 | 支持与反证并存 | S10A | execution review did not advance | native cash rejection；不以 local repair 重开 | LOCAL_ADJUDICATION |
| Static diversification | allocation | E1 | 复杂度门槛 | S30 | REFERENCE_BASELINE | 机制匹配比较器 | REFERENCE_ONLY |

## 成熟/已知：不应从零验证存在性

time-series momentum、cross-sectional momentum、industry momentum、value、value+momentum、1/N 与经典优化方法已有外部基础。TactiCore 只能问它们是否转移到限定的可交易中国/全球 ETF 域，而不是重发现异常。

## 成熟方法与上游

inverse-vol、ERC/risk parity、mean/minimum variance、shrinkage、maximum diversification、Black-Litterman、HRP/HERC 是构造方法；软件可用不代表经济优越。PyPortfolioOpt 覆盖 efficient frontier、minimum volatility、Black-Litterman 与 HRP；Riskfolio-Lib 覆盖 mean-risk、BL、HRP/HERC。仅未来具体缺口需要时评估依赖，当前不安装。

## 有条件/争议

GTAA/moving-average tactical allocation、volatility targeting/managed portfolios、HRP优越性以及中国动量均属 E3：支持与反证必须同时读取。Moreira/Muir 的 volatility-managed 结果与 Cederburg 等关于可投资 OOS 组合的质疑都已登记；中国动量综述显示研究设计、频率与IPO处理会改变结论。

## 开放的本地问题

China ETF transfer、theme rotation、defensive ETF、PIT ETF universe、launch/survivorship、流动性、交易成本、sector/theme overlap 与可用资产类别 breadth 是 TactiCore 可能贡献本地证据的范围；它们均未在本 Goal 自动实现。

PIT ETF universe、上市/退市与 execution-date price 已在 Batch 04 升级为 **ACTIVE RESEARCH CORRECTNESS FOUNDATION**：任何后续 transfer 先通过 lifecycle mask 与正目标验证，再进入本地 evidence gap。

## 已关闭本地问题与当前缺口

S1、S3A、S3B、S3C、S4A、S8A 与 S10A 的具体问题已关闭，不能换名或调参重开。S2 R1 与 S4C R1 是**活动**前瞻影子候选（S4C 由独立 lifecycle artifact 激活，`observation_count = 0`），S4C 的集中度是已登记的已知候选风险而不是待优化项；S27A 保留 candidate-freeze review 资格但继续推迟。已有候选都不构成生产资格。S4B 因 Riskfolio-Lib 依赖阻塞的历史结论保持不变。S30 是简单复杂度门槛，不是alpha策略。

## 未来选择规则

只从 registry 的 remaining local gaps 选择，并优先高相关性、证据质量、经济正交、低实现自由度与能区分机制的设计。不得按历史 CAGR、叙事或“最兴奋的想法”选择；不得把成熟策略称为 Discovery Batch。

## 代表性来源

Moskowitz/Ooi/Pedersen (2012, TSMOM, DOI `10.1016/j.jfineco.2011.11.003`)；Moskowitz/Grinblatt (1999, industry momentum)；DeMiguel/Garlappi/Uppal (2009, 1/N, DOI `10.1093/rfs/hhm075`)；Moreira/Muir (2017, DOI `10.1111/jofi.12513`) 与 Cederburg 等 (2020)；Faber (2007, DOI `10.3905/jwm.2007.674809`)；López de Prado (2016, DOI `10.3905/jpm.2016.42.4.059`)；Yang/Gebka/Hudson (2019, DOI `10.1016/j.ribaf.2018.07.003`)。

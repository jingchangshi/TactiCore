# S4C candidate-freeze review V1

独立候选冻结审查，回答一个问题：**已经通过 transfer、PIT correctness、bounded robustness 与 RQAlpha 6.3.0 原生执行的 S4C 经济身份，是否应冻结为研究候选？**

审查由 [research priority decision](RESEARCH_PRIORITY_DECISION_V1.md)（Commit `7cef1bc`，先于本审查）授权。审查是只读裁决：不重跑历史、不改参数、不加 cap、不制造前瞻证据。

## 审查方法

只做只读核对：SHA-256（CRLF 归一化后的冻结文本 hash）、冻结目标结构与 PIT 校验、策略语义再推导（`run_s4c_erc_skfolio_transfer.py` 的 `build_targets` 语义、`build_execution_weights` 的时点语义）、已提交机器产物与报告的一致性、框架版本核对。**没有**重跑 40/60/80 robustness、VectorBT 历史或 RQAlpha 历史。

## S4C_EVIDENCE_CHAIN_STATUS

`ONE_UNAMBIGUOUS_AUTHORITATIVE_CHAIN`。

| 阶段 | 记录 | 结果 |
| --- | --- | --- |
| External Evidence Gate | registry `ERC_RISK_PARITY`，`E2_ESTABLISHED_METHOD`，`UPSTREAM_COMPARE` | 成熟构造方法，非 alpha 主张；限制（协方差估计、集中度、无杠杆 ETF 域）已登记 |
| S4B 上游阻塞 | [S4B_ERC_TRANSFER_V1](S4B_ERC_TRANSFER_V1.md)、RL-026 | `BLOCK_S4B_UPSTREAM_DEPENDENCY`，保持历史事实，未被 S4C 替换或改写 |
| S4C skfolio transfer | [S4C_ERC_SKFOLIO_TRANSFER_V1](S4C_ERC_SKFOLIO_TRANSFER_V1.md)、RL-030 | `ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS` |
| PIT correctness closure | [S4C_PIT_CORRECTNESS_REVALIDATION_V1](S4C_PIT_CORRECTNESS_REVALIDATION_V1.md)、RL-031/RL-033 | 旧 10 个上市前 fallback target 不可执行；修正后 inception `2013-04-01`，`RESTORE_S4C_ROBUSTNESS_ELIGIBILITY` |
| 40/60/80 邻域 + 固定分期 + rolling + 50bps | [S4C_ROBUSTNESS_V1](S4C_ROBUSTNESS_V1.md)、RL-037 | `ADVANCE_S4C_TO_EXECUTION_REVIEW` |
| 权威执行 Protocol V1 | [PROTOCOL.md](../batches/s4c_execution_review/PROTOCOL.md)、commit `356ed98` | 在 reproduction gate 处停止，保留为 [INVALID_RUN R1](INVALID_RUN_S4C_EXECUTION_R1.md) |
| 权威执行 Protocol V2 | [PROTOCOL_V2.md](../batches/s4c_execution_review/PROTOCOL_V2.md)、commit `61c4962` | 仅替代不可跨平台的 `1e-12` reproduction 判据，不放松任何 native gate |
| RQAlpha 执行结果 V2 | [S4C_RQALPHA_EXECUTION_REVIEW_V2](S4C_RQALPHA_EXECUTION_REVIEW_V2.md)、RL-040 | `ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW` |

无第二条并行权威链，无互相矛盾的 S4C 语义版本。`INVALID_RUN` 是同一链上的协议缺陷记录，不是替代结果。

### 只读核对结果

| 核对项 | 期望 | 实测 | 结论 |
| --- | --- | --- | --- |
| 冻结目标 SHA-256（CRLF 归一化） | `f7bf398d…1227e47` | `f7bf398d7f8a016933cbe287bfa1cac98b3cccf175d40ef99092b95db1227e47` | PASS |
| 行数 / 首末 execution date | 161 / `2013-04-01` / `2026-08-03` | 一致 | PASS |
| 日期唯一严格递增 | 是 | 是 | PASS |
| 权重非负、逐行合计为一 | 是 | 是（min 0.9999999999999992 / max 1.0） | PASS |
| canonical 价格 hash | `0ab40b9c…e15d8e93` | 一致 | PASS |
| 交易日历 hash | `ad942a3e…a1a9d7512` | 一致 | PASS |
| provenance hash / 截止日 | `7af2e218…37a8d4e3` / `20260831` | 一致 | PASS |
| `config/strategy.toml` / `config/universe.csv` hash | `9935dbdb…931c2ce` / `190aacbc…aadb8829` | 一致 | PASS |
| 策略实现 `multi_asset_trend.py` hash | `2a11156f…eb7d1a6` | 一致 | PASS |
| 冻结目标列结构 | canonical universe 12 列 | 12 列；`511260.SS`、`511880.SS` 恒为 0 | PASS（记录为身份细节） |

## ECONOMIC_IDENTITY

以下身份由源代码与冻结产物核对确认，不是从文档转述：

| 维度 | 冻结值 | 核对来源 |
| --- | --- | --- |
| canonical strategy | Equal Risk Contribution / Risk Budgeting | registry `ERC_RISK_PARITY` |
| upstream implementation | 官方 `skfolio==1.0.6` `RiskBudgeting` | `run_s4c_erc_skfolio_transfer.erc_weights` |
| risk measure | `RiskMeasure.VARIANCE` | 同上 |
| risk budgets | equal（默认，未传自定义预算） | 同上 |
| 约束 | long-only（`min_weights=0.0`）、fully invested（权重和为 1）、无杠杆（`max_weights=1.0`） | 同上 |
| min eligible | 6；不足即完全回退 fallback，不部分持有 | `MIN_ELIGIBLE = 6`；`aligned_window` 返回空即 fallback |
| returns window | 60 条 `pct_change(fill_method=None)` 对齐日收益 / 61 个共同可见价格 | `WINDOW = 61`；`returns = window.pct_change(fill_method=None).dropna(how="any")` |
| 风险 universe | 现有冻结 risk universe（9 个 `risk_symbols`） | `config/strategy.toml` |
| fallback | `511010.SS`（100%） | `S4CConfig.fallback_symbol` |
| signal timing | 月末 canonical 观测日 | `groupby(to_period("M")).tail(1)` |
| execution timing | 不得早于信号日后的下一 canonical 观测日 | `build_execution_weights` 的 `next_location` |
| 目标提交政策 | 每月提交（`build_execution_weights`），**不是** `SIGNAL_CHANGE_ONLY` | 与 S2 R1 的执行政策不同，必须分别冻结 |
| 成本 | 10 bps fee、5 bps slippage | `S4CConfig` 默认值来自 `config/strategy.toml` |
| 初始资金 | CNY 1,000,000 | 同上 |
| PIT 契约 | `validate_execution_targets` + universe `start_date` 生命周期 | `tacticore/data/tradability.py` |
| strategy inception | `2013-04-01`（完整 target 的首个合法执行日） | PIT-corrected 冻结目标首行 |
| authoritative execution | RQAlpha 6.3.0，`order_target_portfolio`，原生撮合/整手/现金/成本，`partial_fill_on_insufficient_cash=true` | Protocol V2 + `run_s4c_rqalpha_execution_review.py` |
| 框架版本 | skfolio 1.0.6 / RQAlpha 6.3.0 / VectorBT 0.28.5 / pandas 2.3.3 / numpy 1.26.4 / tushare 1.4.29 | 实测 `importlib.metadata.version` |
| historical data cutoff | `2026-08-31`（canonical 快照截止） | `provenance.end_date = 20260831` |

任何与此不一致的表述都不是 S4C。任何实质语义、数据契约或执行语义变更都必须创建下一顺序候选版本，不得改写本身份。

## MECHANISM_ORTHOGONALITY_VS_S2

| 问题 | S2 R1 | S4C R1 |
| --- | --- | --- |
| 前瞻中检验的经济风险 | 时间序列趋势信号在长多 ETF 域是否稳健：趋势择时能否避开风险资产的下行段 | 风险预算分配能否在**给定同一可投资集合**内把组合风险更均衡地摊到资产上 |
| 信号来源 | 逐资产 200 有效观测价格趋势（含方向） | 60 日对齐收益的样本协方差结构（无方向判断） |
| 组合逻辑 | 趋势为负的 sleeve 转防御资产；等额 sleeve | 月度重新求解 ERC 权重；不足 6 个资产时整体 fallback |
| 目标提交 | `SIGNAL_CHANGE_ONLY` | 每月提交 |
| 重叠部分 | 同一 risk universe、同一 `511010.SS` fallback、同一成本与 canonical 数据契约、同一 RQAlpha 执行语义、同一 PIT 契约 | 同左 |
| 真正正交部分 | 方向性择时（何时离场） | 横截面风险分配（如何分权），不产生择时方向 |

**S4C 能提供而 S2 不能提供的信息**：

1. 在完全相同的可投资集合上，**风险均衡化本身**（相对同 eligible 等权与 inverse-vol）是否在前瞻中维持历史观察到的风险调整优势。
2. 协方差估计误差与**结构性集中**（ERC 在低相关/低波动资产上会自然给出大权重）在样本外是否产生 S2 结构不会产生的行为——S2 的权重由趋势状态与等额 sleeve 决定，不会出现 50%+ 单资产。
3. 执行层的前瞻问题是**常规月度再平衡**的整手、现金与成本行为；S2 的前瞻执行问题主要是**状态切换日**的换手。两者对执行与维护负担的证据不可互相替代。

结论：S4C 与 S2 不是同一经济问题的两次测量。共享的数据与执行脚手架是工程重叠，不是机制重叠；机制层面二者互补。

## CONCENTRATION_DISPOSITION

已知数值（来自 [s4c_bounded_robustness_concentration_v1.csv](s4c_bounded_robustness_concentration_v1.csv)，RISK 月）：

| 指标 | 值 |
| --- | --- |
| median maximum weight | 26.94% |
| P95 maximum weight | 51.84% |
| historical maximum weight | 66.35% |
| 任一资产超过 50% 的月份数 | 9 |
| median effective number of assets | 6.23 |
| P05 effective number of assets | 3.24 |

**裁决：`ACCEPT_AS_KNOWN_CANDIDATE_RISK`。**

理由：

1. 集中度是**无约束 ERC 在低相关资产上的数学后果**，不是实现缺陷、不是数据错误，也不是被观察到的目标偏离。它在该构造方法被选定之前就已被登记为已知限制（registry `ERC_RISK_PARITY.known_limitations`）。
2. 它在 transfer、robustness 与 execution 三个阶段都被当作**诊断证据**保留，从未被用作修改门槛或事后 cap 的理由；execution review 的结果是在不添加任何 cap 的同一身份上取得的。
3. 在本 Goal 内添加 cap 会**改变经济身份**，使冻结对象不再是获得资格的那个 S4C，属于被明确禁止的优化行为。
4. 候选冻结不是生产批准。集中度在候选被冻结后仍然是**前瞻必须观测的风险特征**，写入候选协议作为已知风险，而不是被消除的前提。

如果未来用户的政策要求对策略集中度设硬上限，那是**新的经济问题与新的策略版本**，必须在新的 External Evidence Gate 与预注册协议下研究，不得回溯改写本候选。

## EXECUTION_EVIDENCE_STATUS

RQAlpha 6.3.0 原生 target-only 回放，冻结目标 161/161，额外 replay 日期 0。

| 指标 | 值 |
| --- | --- |
| CAGR | 12.0929% |
| signed MaxDD | -18.3512% |
| Sharpe | 0.7758 |
| turnover | 11.2436 |
| native order count / trade count | 1,184 / 1,181 |
| cash rejection events | 0 |
| native cash-residual cancellation events | 0 |
| volume-limited events | 3 |
| 平均 execution-date total absolute weight deviation | 0.3246% |
| 最大 deviation | 15.9521% |
| materially off-target execution dates | 3 / 161 = 1.86% |
| 平均现金比 | 0.1399% |

reproduction gate 在 Protocol V2 容差（`isclose(rel_tol=1e-4, abs_tol=1e-4)`）下逐指标 PASS，V1 的精确判据作为 `INVALID_RUN` 保留且未被修改。

**证据性质必须说清楚**：这是历史执行证据，不是前瞻样本外证据，也不构成生产可交易性结论。它证明的是"该冻结目标日程能在 RQAlpha 原生语义下被忠实执行"，而不是"该策略在未来有效"。

## MATERIAL_ASSET_DIFFERENCE_DEFINITION

```text
material_asset_difference
= 单个资产在某个 execution date 上的 |intended_weight - realized_weight| > 5pp
```

历史实现：`run_s2_rqalpha_validation.material_difference_table`，逐标的比较 `schedule` 与 `actual`，阈值 `MATERIAL_DEVIATION = 0.05`。机器产物为 [s4c_rqalpha_execution_material_differences_v2.csv](s4c_rqalpha_execution_material_differences_v2.csv)，历史条件下有 2 条：

| date | symbol | intended | realized | native 原因 |
| --- | --- | --- | --- | --- |
| 2014-05-05 | 513500.SS | 21.61% | 16.48% | 市场单 205,000 股超过当前 bar 成交量 25% 上限，成交 156,200 股后被取消 |
| 2026-02-02 | 518880.SS | 9.44% | 14.67% | 触及跌停价（`limit_down`）拒单 |

## MATERIAL_PORTFOLIO_TRACKING_DEFINITION

```text
material_portfolio_tracking_date
= 某 execution date 上组合层 total absolute weight deviation > 5pp
```

历史实现：`run_s2_rqalpha_validation.target_tracking_table` 的 `materially_off_target = total_deviation.gt(MATERIAL_DEVIATION)`，阈值同为 `0.05`。历史条件下有 3 个这样的日期。

**两个概念在同一次历史审查中恰好共用同一个 5pp 阈值，但它们不是同一个量**：前者是单资产偏差，后者是组合层偏差之和。历史条件下 `material_portfolio_tracking_date` 的数量（3）大于 `material_asset_difference` 记录条数（2）。

最重要的推论：`2015-01-05` 是一个 `material_portfolio_tracking_date`，但**没有**任何单资产偏差超过 5pp（该日最大单资产偏差 3.84pp，现金残差 3.80%），因此它不在 `material_asset_difference` 表中，本审查也不为它声称存在"已记录的原生单资产原因"。历史报告在 V1 中已如实描述这一点，本审查不改写任何历史结论。

对**未来候选前瞻协议**的要求：两个概念必须分别命名、分别记录、分别设阈值，且 `material_portfolio_tracking_date` 不得被表述为"每个组合层跟踪日期都有已记录的原生单资产原因"。

## MAINTENANCE_BURDEN

| 维度 | 估计 | 依据 |
| --- | --- | --- |
| decision frequency | 每月 1 次 | 月末 canonical 观测日 |
| target-change frequency | 历史 161/161 个月提交目标（年化 12.00） | [user effort v2](s4c_rqalpha_execution_user_effort_v2.csv) |
| execution-event frequency | 历史 150/150 个提交月份都发生了实际成交 | 同上 |
| 人工复核负担 | 每月一次，近似机械 | 无状态切换判断，无手工 sizing |
| 工具数量 | 10 个（9 risk + 1 fallback）；冻结目标表中另有 2 个恒为 0 的 canonical 列 | 冻结目标结构 |
| 依赖负担 | 无新增运行时依赖；`skfolio` 已作为 `research` extra 引入 | `pyproject.toml` |
| data-vintage 负担 | 每月一次 candidate-specific vintage + 重叠校验 | 待前瞻协议冻结 |
| RQAlpha 证据负担 | 已在执行阶段完成；前瞻期只需复用同一原生语义 | Protocol V2 |

与 S2 R1 相比，S4C 的决策更频繁（每月提交 vs 仅在信号变化时提交），但仍属月频、低维护。负担对个人投资者研究系统而言合理。

## CANDIDATE_FREEZE_DECISION

```text
FREEZE_S4C_RESEARCH_CANDIDATE_R1
```

依据：

1. 存在**唯一无歧义**的权威证据链，且每一段都可追溯到具体 committed artifact 与 RL 条目。
2. 经济身份的全部维度可从源代码与冻结产物核对，无文档-代码冲突。
3. canonical provenance 完整：截止 `2026-08-31`，价格/日历/来源清单 hash 全部一致。
4. PIT 边界完整：inception `2013-04-01`，`validate_execution_targets` 通过，上市前 fallback target 已被修正而非被静默跳过。
5. robustness 与 execution 证据可归属于**恰好这个**身份（commit 顺序：protocol 冻结先于结果）。
6. upstream/execution 语义可被固定（skfolio 1.0.6、RQAlpha 6.3.0，均已实测）。
7. historical/prospective 边界可以干净划定；版本与失效规则可以不带策略语义变更地写出。
8. 集中度已被明确裁决为**已知候选风险**，而不是通过 cap 被消除。

不构成：生产批准、前瞻有效性证据、候选已被激活。冻结候选与激活前瞻是两件事；本 Goal 只做前者，并预注册后者所需协议。

## 不授权与边界

本审查不授权：修改 S4C 经济语义、参数、窗口、risk measure、fallback 或 solver；添加集中度 cap；重跑 40/80 robustness、VectorBT 历史或 RQAlpha 历史；改写 S2 R1、Batch 05 冻结产物或任何 `INVALID_RUN`；用历史结果制造前瞻证据；建设通用 candidate/execution/治理基础设施。

候选身份与前瞻协议见 [research/shadow/s4c_r1/](../shadow/s4c_r1/README.md)。

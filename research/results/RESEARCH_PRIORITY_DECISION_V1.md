# TactiCore research priority decision V1

独立 C2C 研究优先级决策。本文在**任何**候选实现、候选清单或前瞻协议之前写成并提交；它只回答“下一个单位的研究注意力与前瞻证据预算应投向哪里”，不产生新策略结果。

决策者：ChatGPT（Principal Architect / Research Portfolio Manager），基于 MCP 只读检查仓库；执行者为 Codex。本文记录决策本身，不替代 `docs/ARCHITECTURE.md`、`docs/RESEARCH_RULES.md` 或 `docs/RESEARCH_LEDGER.md` 的职责。

## 仓库基线

| 项 | 值 |
| --- | --- |
| STARTING_HEAD | `1b74b8e`（`record batch 5 architect and windows audit`） |
| ORIGIN_MAIN_HEAD | `1b74b8e`（`main == origin/main`） |
| WORKING_TREE_STATE | clean，无未跟踪文件 |

## CURRENT_RESEARCH_PORTFOLIO

| 策略 | 家族 | 本地状态 | 说明 |
| --- | --- | --- | --- |
| S2 Multi-Asset Trend Following R1 | trend | `FROZEN / PROSPECTIVE_SHADOW_ACTIVE` | 唯一活动前瞻候选；PIT integrity pass；0 条前瞻 decision record |
| S27A Trend + Inverse Vol | composite | `ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW`（deferred） | 资格成立，但 RL-039 因与 S2 趋势机制重叠而有意推迟 |
| S4C Canonical ERC / skfolio | allocation | `ADVANCE_S4C_TO_CANDIDATE_FREEZE_REVIEW` | transfer、PIT correctness、bounded robustness、RQAlpha 原生执行全部通过 |
| S10A Unlevered Volatility Targeting | overlay | `DO_NOT_ADVANCE_S10A_EXECUTION` | 原生 cash rejection gate 失败，不得本地修补 |
| S1 / S3A / S3B / S3C / S4A / S8A | 多种 | `REJECTED` | 已关闭；不得换名或调参重开 |
| S4B Canonical ERC / Riskfolio-Lib | allocation | `BLOCK_S4B_UPSTREAM_DEPENDENCY` | 依赖解析阻塞，保持历史事实 |
| S30 Static Diversification | benchmark | `REFERENCE_BASELINE` | 复杂度门槛，不是 alpha 主张 |

## CURRENT_PROSPECTIVE_CANDIDATES

仅 `S2_R1`。`research/shadow/s2_r1/observations.csv` 只有表头，表示尚无真实前瞻月末决策，而不是零收益。前瞻证据预算当前完全集中在 S2。

## CURRENT_ELIGIBLE_NEXT_STAGES

- S4C：candidate-freeze review 资格（本次决策的候选主 Goal）。
- S27A：同一资格，继续推迟。
- S10A：无资格，仅新语义/契约/矛盾证据可重开。
- S2：时间驱动，不能被任何工作加速（中期完整性复核 ≥ 12 个日历月，production-candidate review 资格 ≥ 18 个日历月且 ≥ 10 次真实 target-change 执行事件）。

## 选项

- **A — S4C candidate-freeze review**：S4C 是否已有足够的经济、正确性、可复现、执行与运维证据，去占用第二个 TactiCore 前瞻候选名额。
- **B — S27A candidate-freeze review**：在 S2 R1 已经占据前瞻带宽时，再冻结一个趋势衍生候选是否带来足够的增量前瞻信息。
- **C — 暂不新增候选**：有意只保留 S2 处于前瞻影子，等待真实前瞻观测。
- **D — 开启新的经济正交本地缺口**：例如 defensive ETF、theme rotation、liquidity/implementation 或其他 E4 本地问题。

## OPTION_A_SCORE

### 14 维评分（1 = 最差，5 = 最优；负担/风险类维度按“越轻越好”计分）

| 维度 | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| Evidence Maturity | 5 | 5 | 3 | 1 |
| Stage Readiness | 5 | 5 | 2 | 2 |
| Economic Orthogonality | 4 | 2 | 1 | 5 |
| Incremental Information Gain | 4 | 2 | 2 | 4 |
| Prospective Evidence Value | 5 | 2 | 2 | 3 |
| Overlap With Existing Candidate（低重叠=5） | 4 | 2 | 1 | 5 |
| Candidate Slot / Attention Cost（低成本=5） | 3 | 3 | 5 | 2 |
| Operational Maintenance Burden（低负担=5） | 4 | 4 | 5 | 2 |
| Implementation Freedom / Data-Mining Risk（低自由度=5） | 5 | 4 | 5 | 2 |
| Correctness Risk（低风险=5） | 4 | 4 | 4 | 2 |
| Upstream / Community Coverage | 5 | 4 | 5 | 2 |
| Time To New Information（快=5） | 3 | 3 | 2 | 1 |
| Reversibility | 4 | 4 | 5 | 4 |
| Expected Decision Value | 5 | 3 | 2 | 3 |
| **合计** | **60** | **47** | **44** | **38** |

评分口径与 `docs/STRATEGY_RESEARCH_MAP.md` 的未来选择规则一致：高相关性、证据质量、经济正交、低实现自由度与机制区分度；仓库未规定权重，因此取等权。历史 CAGR 不作为任何维度的依据。

### OPTION_A_SCORE — 说明

S4C 的未决问题被明确限定为“**已冻结的历史身份**是否完备、可复现、可追溯、可执行且具备前瞻协议准备度”。transfer（RL-030）、PIT correctness（RL-031/RL-033）、bounded robustness（RL-037）与 RQAlpha 6.3.0 原生执行（RL-040）均已关闭，因此证据成熟度与阶段就绪度最高。实现自由度极低：161 行冻结目标与 SHA-256 已存在，审查是只读裁决而不是再优化。经济正交性高：ERC/risk budgeting 不含趋势信号，与 S2 的时间序列动量不是同一问题；但它与 S2 共享 risk universe、511010.SS fallback 与成本脚手架，因此不是满分正交。时间到新信息不快：真正的增量信息是前瞻性的，而前瞻观测需要真实市场时间；这也是它唯一的明显弱项。

## OPTION_B_SCORE — 说明

S27A 阶段就绪度同样满分，PIT-corrected 原生执行也已通过，但它复用 S2 的 200 有效观测趋势信号，只用 inverse-vol 重分配已激活 sleeve。两个候选将回答同一个经济问题（趋势暴露是否在 ETF 域稳健），因此机制区分度低、边际前瞻信息低，而前瞻污染风险与注意力成本与非重叠候选相同。冻结第二个趋势型候选是“资格”不是“优先级”。

## OPTION_C_SCORE — 说明

“什么都不做”是有效的研究决定，不是低价值默认项：它对候选数量零成本、可逆性最高、维护负担为零，并避免可解释性稀释。它在本次没有被选中，只因为它不减少任何当前可减少的不确定性——S2 的前瞻证据只能随日历时间积累，任何等待型决策都无法加速它，而 S4C 的冻结问题在今天就已被充分前置证据支持。

## OPTION_D_SCORE — 说明

registry 中的 E4 本地缺口（`CHINA_THEME_ETF`、`CHINA_DEFENSIVE_ETF`、`ETF_LIQUIDITY`、`PIT_ETF_UNIVERSE` 等）在经济正交性上可能最高，但它们尚未通过 External Evidence Gate 与 PIT Tradability Gate，需要新的问题定义、可能的新数据契约，且实现自由度与数据挖掘风险显著更高。在已经获得资格、且实现自由度极低的 S4C 冻结裁决尚未完成时，先开启更宽的搜索空间会以更高成本换取更低确定性的信息。

## SELECTED_PRIMARY_GOAL

```text
S4C_CANDIDATE_FREEZE_REVIEW
```

## WHY_THIS_GOAL

它是唯一同时满足“阶段已获得资格”“实现自由度已被冻结到接近零”“经济机制与当前唯一前瞻候选不同”三项的选项。它把一个已经存在但尚未裁决的资格转成一个明确、可审计、可逆的二值决定，且不需要任何新的历史优化。

## WHY_NOW

S4C 的四段证据链刚刚在同一 Batch 05 窗口内关闭，身份尚未被任何后续工作漂移；此时做裁决的追溯成本最低。推迟不会让证据变多——S4C 的增量证据只能来自前瞻，而前瞻只可能在候选被冻结之后开始。每多等一个研究周期，冻结成本与身份漂移风险都上升。

## WHY_NOT_THE_OTHERS

- 不选 B：S27A 与 S2 共用趋势信号，冻结它主要产生流程性证据，边际经济信息低，且会稀释前瞻解释力。资格保留、继续推迟。
- 不选 C：它是正确的默认态而非本次的最优解；它不减少当前可减少的不确定性（见 OPTION_C_SCORE）。
- 不选 D：E4 缺口需要先经过 External Evidence Gate 与 PIT Tradability Gate，实现自由度与数据挖掘风险高，不是当前成本最低、确定性最高的下一步。

## UNCERTAINTY_REDUCED

如果这项工作成功完成，以下不确定性会变小：

1. S4C 的历史证据链是否构成**唯一无歧义**的可复现身份，而不是若干局部通过的拼接。
2. TactiCore 能否在不稀释可解释性的前提下承载**第二个**前瞻候选，以及第二个名额是否被正确使用。
3. ERC 的**已知集中度特征**（P95 maximum weight 51.84%、historical maximum 66.35%、effective assets median 6.23 / P05 3.24）是否可以作为候选的已知风险被接受，而不是通过事后 cap 被“修复”。
4. 在真实前瞻开始前，是否已经具备干净的 historical/prospective 边界、vintage 规则与失效语义。

它**不**减少的不确定性：S4C 的未来收益、回撤或前瞻稳定性。这些只能由前瞻观测回答，本 Goal 不制造也不回填任何前瞻证据。

## CANDIDATE_BUDGET_IMPACT

前瞻证据预算稀缺。选择 A 会**申请**占用第二个候选名额，但占用与否取决于独立审查的终局裁决（FREEZE / DEFER / REJECT / BLOCK），而不是本次优先级决策。若裁决不是 FREEZE，候选预算继续只属于 S2。无论裁决如何，本次决策都不创建候选、不激活前瞻、不改变 S2。

## SMALLEST_SUFFICIENT_CLOSURE

一次只读的 S4C 候选冻结审查，加上恰一个终局裁决文档：

```text
research/results/S4C_CANDIDATE_FREEZE_REVIEW_V1.md
```

只有当裁决为 `FREEZE_S4C_RESEARCH_CANDIDATE_R1` 时，才追加最小的候选冻结身份（`research/shadow/s4c_r1/candidate_manifest.json` 与简短 `README.md`）与其要求的前瞻协议 preregistration。不得重跑 40/60/80 robustness、VectorBT 历史或 RQAlpha 历史，只允许只读的 SHA/hash/静态身份校验。

## STOP_CONDITIONS

遇到以下任一情况立即停止并重新规划，不得静默继续：

```text
committed 冻结目标 hash/身份与 RL-040 / Protocol V2 不一致
S2 strict candidate integrity 失败
解冻/修补需要新优化、40/80 重跑、集中度 cap、新 risk measure、新 fallback、solver 替换
需要数据回填或历史目标重生成
需要本地 cash/sizing/retry 逻辑或通用 candidate/execution 基础设施
在观察到新生成结果之后才想修改冻结判据
```

## ESCALATION_CONDITIONS

升级给用户（而不是自行折中）的条件：

```text
审查发现 S4C 经济身份与已接受历史证据之间存在真实矛盾
集中度被判定为候选不可接受，但仓库没有任何被授权的集中度政策可引用
冻结候选与 S2 的并存需要用户决定前瞻注意力分配
裁决要求改变 ARCHITECTURE / RESEARCH_RULES 的永久边界
```

## 边界

本决策不授权：修改 S4C 经济语义、参数、窗口、risk measure 或 fallback；添加集中度 cap；重跑历史研究；改写 S2、Batch 05 冻结产物、`INVALID_RUN` 或外部证据 tier；启动 S4C 前瞻影子；开启 Batch 06、Theme Rotation 或其他新策略；建设通用候选治理框架。

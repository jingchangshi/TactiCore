# Goal: TactiCore Batch 00 — External Strategy Evidence Foundation

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Architect
+
Systematic Strategy Literature Reviewer
+
Repository Architecture Maintainer
```

---

# 0. Why This Work Exists

TactiCore 已经完成第一轮内部策略研究：

```text
S2
Multi-Asset Trend Following
→ historical evidence PASS
→ execution closure PASS
→ parameter plateau PASS
→ Research Candidate R1
→ PROSPECTIVE_SHADOW_ACTIVE

S3A
Sector winner momentum
→ REJECTED

S3B
Sector breadth global switch
→ REJECTED

S3C
Sector sleeve trend
→ REJECTED

S4A
Inverse-vol allocation
→ REJECTED under its local gate

S8A
Equity/bond trend
→ REJECTED

S27A
Trend + inverse-vol
→ ADVANCE_TO_ROBUSTNESS

S30
Static diversified allocation
→ REFERENCE_BASELINE
```

但此前研究流程仍存在一个结构性缺口：

```text
idea
→ local hypothesis
→ code
→ backtest
```

这会导致 TactiCore 重复研究金融学界、量化社区和成熟开源项目已经研究多年的问题。

从本 Goal 开始，长期研究流程必须改变为：

```text
External Literature
+
Practitioner Evidence
+
Community / Upstream Implementations
        ↓
External Strategy Evidence Registry
        ↓
What is already known?
        ↓
What remains unknown specifically for TactiCore?
        ↓
Local Evidence Gap
        ↓
Only then:
strategy implementation / experiment
```

核心原则：

```text
Literature first for strategy ideas.

Upstream first for implementations.

Local research only for the remaining evidence gap.
```

以及：

```text
Prior literature is evidence,
not merely inspiration.
```

---

# 1. This Goal Is NOT a Strategy Backtest

本 Goal：

```text
NO new strategy backtest
NO new parameter experiment
NO robustness run
NO RQAlpha run
NO new historical data
NO Theme Rotation implementation
NO Batch 02 strategy implementation
```

目标只有：

```text
建立 External Strategy Evidence Foundation

+
把这一原则永久写入
architecture / rules / agent routing / strategy documents
```

完成后停止。

---

# 2. Repository First

开始前重新读取最新 remote `main`。

执行：

```bash
git fetch origin
git status
git log --oneline -20
```

不要相信本 Prompt 写死的 HEAD。

阅读：

```text
AGENTS.md

README.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/STRATEGY_CATALOG.md
docs/CURRENT_STATE.md
docs/goal.md

research/results/BATCH_01_TRANSPARENT_STRATEGY_SCREEN.md
research/results/INVALID_RUN_BATCH_01_R1.md
research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md
research/results/S30_STATIC_STRATEGIC_ALLOCATION_V1.md

research/batches/batch_01/PROTOCOL.md
research/batches/batch_01/PROTOCOL_V2.md

research/shadow/s2_r1/candidate_manifest.json
```

检查当前源代码和 relevant artifacts。

记录：

```text
starting HEAD
recent commits
working tree

S2 R1 status
Batch 01 status
S27A status
S30 status

latest S27 corrected comparator values
```

Repository evidence 优先。

---

# 3. First Fix the Existing S27A Ledger Drift

当前最新仓库疑似存在：

```text
S27A main report
vs
RESEARCH_LEDGER RL-023
```

之间 corrected comparator 数字不同。

必须先核实：

```text
research/results/S27A_TREND_INVERSE_VOL_BASELINE_V1.md

research/results/s27a_trend_inverse_vol_comparison_v1.csv

research/results/BATCH_01_TRANSPARENT_STRATEGY_SCREEN.md

research/results/INVALID_RUN_BATCH_01_R1.md

research/batches/batch_01/PROTOCOL_V2.md

docs/RESEARCH_LEDGER.md
```

确认 corrected authoritative values。

如果确实只有：

```text
RL-023
```

残留旧 comparator 数值：

只修正账本文字。

不要：

```text
rerun S27
change strategy
change protocol
change decision
```

这是：

```text
documentation consistency correction
```

不是重新研究。

在 commit/report 中明确记录原因。

---

# 4. Protect S2 R1

开始前运行：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

不得修改 S2 frozen inputs。

尤其：

```text
config/strategy.toml
config/universe.csv

data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json

tacticore/strategies/multi_asset_trend.py
tacticore/engines/rqalpha_adapter.py

research/shadow/s2_r1/candidate_manifest.json
```

本 Goal 与 S2 candidate semantics 无关。

---

# 5. New Architecture Concept: External Evidence Layer

修改：

```text
docs/ARCHITECTURE.md
```

这是本 Goal 的真实 architecture change。

当前链路：

```text
数据
↓
策略语义
↓
研究筛选
...
```

升级为类似：

```text
External Strategy Evidence
        ↓
Local Evidence Gap
        ↓
Data + Strategy Semantics
        ↓
Historical Research Screen
        ↓
Robustness
        ↓
Execution Validation
        ↓
Prospective Candidate
        ↓
Future Production Decision
```

重点不是具体排版，而是表达：

> TactiCore 不从“想到一个策略”开始，而从“外部世界已经知道什么，以及当前交易域还不知道什么”开始。

---

# 6. Architecture Ownership Boundary

在 `ARCHITECTURE.md` 中新增明确职责。

## External literature / community

拥有：

```text
canonical strategy definitions
published empirical evidence
replications
contradictory findings
known implementation methods
```

TactiCore 不拥有这些知识本身。

TactiCore 只：

```text
curate
scope
map
interpret
```

---

## TactiCore External Evidence Registry

拥有：

```text
external evidence snapshot
canonical strategy mapping
evidence tier
known limitations
TactiCore applicability
remaining local evidence gap
upstream implementation pointers
```

它不是：

```text
bibliographic database
paper crawler
academic search engine
knowledge graph
```

---

## TactiCore local research

只拥有：

```text
domain transfer
local replication
local adjudication
new local hypotheses
execution verification
prospective evidence
```

---

# 7. Dual Evidence Authority

在架构中明确：

对于 repository/local facts：

```text
source code
+
frozen artifacts
>
repository documentation
```

对于 external research claims：

```text
primary publication
>
high-quality independent replication/review
>
original practitioner research
>
secondary explanation
```

External Evidence Registry 是：

```text
versioned local synthesis
```

不是比原始论文更高的 authority。

---

# 8. Permanent Research Rule: Literature Gate

修改：

```text
docs/RESEARCH_RULES.md
```

新增永久规则：

# External Evidence / Literature Gate

任何新的 strategy family、signal、allocator 或 tactical overlay 在写代码前必须回答：

```text
1. What is its canonical name?

2. Has this already been studied?

3. What does the strongest external evidence say?

4. Is the evidence supportive, mixed,
   method-only, or insufficient?

5. What market / asset class / implementation
   did that evidence actually study?

6. Does a mature upstream implementation exist?

7. What exact question remains unanswered
   for TactiCore?

8. Has that local question already been
   answered by RESEARCH_LEDGER?

9. What is the simplest appropriate comparator?

10. Why is new code necessary?
```

如果这些问题无法回答：

```text
NO STRATEGY CODE
```

---

# 9. External Evidence Tiers

把以下 taxonomy 写入：

```text
docs/RESEARCH_RULES.md
```

并在 registry/map 中统一使用。

---

## E1_MATURE

定义：

```text
多篇高质量研究、
跨样本/跨市场或长期历史证据，
某一现象本身已有成熟外部证据。
```

典型 action：

```text
TRANSFER_VALIDATE
```

不得重新问：

```text
Does this anomaly exist?
```

只能研究：

```text
Does the canonical finding transfer
to TactiCore's tradable domain?
```

---

## E2_ESTABLISHED_METHOD

定义：

```text
方法/组合构建算法已经成熟，
但并不意味着其一定产生 alpha
或稳定优于简单 benchmark。
```

典型：

```text
1/N
inverse volatility
ERC / risk parity
minimum variance
HRP
Black-Litterman
```

典型 action：

```text
UPSTREAM_COMPARE
```

而不是：

```text
DISCOVER_ALPHA
```

---

## E3_MIXED_CONDITIONAL

定义：

```text
已有大量研究，
但结果存在冲突、
强烈依赖样本、实现或市场状态。
```

典型 action：

```text
LOCAL_ADJUDICATION
```

必须同时记录：

```text
supporting evidence
contradicting evidence
```

不能只引用支持自己想法的论文。

---

## E4_OPEN_LOCAL

定义：

```text
公开证据不足，
或问题高度依赖中国 ETF、
本地交易工具、PIT universe、
实际流动性等具体约束。
```

典型 action：

```text
NEW_HYPOTHESIS
```

但必须先证明：

```text
reasonable literature search
did not already answer the question
```

---

# 10. Evidence Tier Does NOT Equal Local Decision

永久写入规则：

```text
External E1
does NOT imply
TactiCore local PASS
```

例如：

```text
global time-series momentum evidence may be strong
while a particular China ETF implementation can fail.
```

反过来：

```text
TactiCore REJECT
does NOT falsify
the canonical strategy globally.
```

同样：

```text
TactiCore PASS
does NOT upgrade
an external evidence tier.
```

必须严格区分：

```text
external evidence
vs
local evidence
```

---

# 11. Research Action Vocabulary

永久采用：

```text
TRANSFER_VALIDATE

UPSTREAM_COMPARE

LOCAL_ADJUDICATION

NEW_HYPOTHESIS

REFERENCE_ONLY

DO_NOT_PURSUUE
```

如果仓库已有更合适命名，可统一成等价命名。

不要建设状态机。

这些只是 research semantics。

---

# 12. Complexity Hurdle Rule

更新 `RESEARCH_RULES.md`：

任何复杂策略必须回答：

```text
Why not the simpler benchmark?
```

适当 comparator 可以是：

```text
1/N
S30
buy-and-hold
same-universe equal weight
same-risk-exposure comparator
canonical unmanaged version
```

不是所有策略都强制比较同一个 benchmark。

必须选择：

```text
the simplest comparator
that isolates the added mechanism
```

---

# 13. Community Implementation Rule — Expand Existing Rule

当前社区优先主要针对：

```text
VectorBT / RQAlpha infrastructure
```

扩展为：

```text
strategy implementation also follows upstream-first
```

对于经典 allocator / optimizer：

先检查：

```text
existing TactiCore capability

VectorBT

PyPortfolioOpt

Riskfolio-Lib

official/reference implementation

other mature community implementation
```

然后才允许：

```text
minimal local implementation
```

但不要因为 registry 中列出项目就立即引入 dependency。

依赖只有在未来具体实验需要时才评估。

---

# 14. Do Not Create Research Infrastructure

本 Goal 禁止创建：

```text
literature crawler
paper downloader
citation database
SQL database
strategy registry service
research knowledge graph
web scraper
agent workflow engine
```

只创建轻量：

```text
one machine-readable registry
+
one human-readable research map
```

---

# 15. New Machine-Readable Evidence Registry

新增：

```text
research/strategy_evidence/STRATEGY_EVIDENCE_REGISTRY.yaml
```

不要增加 YAML runtime dependency。

这是 version-controlled research artifact，不需要软件运行它。

每个 entry 建议至少：

```yaml
strategy_id:

canonical_name:

family:

strategy_type:
  # anomaly
  # allocation_method
  # tactical_rule
  # benchmark
  # overlay
  # local_hypothesis

external_evidence:
  tier:
  consensus:
  summary:
  evidence_as_of:

canonical_sources:
  - title:
    authors:
    year:
    venue:
    doi_or_identifier:
    role:
      # canonical
      # replication
      # contradiction
      # review
      # practitioner

known_limitations:

implementation_prior:
  upstream_available:
  known_projects:
  preferred_action:

tacticore:
  relevance:
  local_mapping:
  local_status:
  local_evidence_refs:
  remaining_gap:

research_action:

do_not_research:
```

字段可以合理收敛，但必须保留这些语义。

---

# 16. No Fake Precision

registry 不得包含：

```text
evidence_score = 87
confidence = 93%
strategy_quality = 8.7
```

这种伪精确评分。

只使用：

```text
tier
consensus
scope
limitations
remaining gap
```

---

# 17. Source Quality Rule

优先：

```text
peer-reviewed primary publication

major academic working paper
when no published version exists

independent replication/review

original practitioner paper
for practitioner-origin strategy

official upstream documentation/source
for implementation claims
```

避免用：

```text
SEO blogs
strategy marketing pages
random Medium posts
uncited summaries
```

替代原始证据。

如果只能找到 practitioner evidence：

必须明确：

```text
PRACTITIONER_EVIDENCE
```

不能包装成 academic consensus。

---

# 18. Contradictory Evidence Is Mandatory

对于：

```text
E3_MIXED_CONDITIONAL
```

必须主动搜索：

```text
negative replication
OOS failure
recent contradictory paper
implementation sensitivity
```

不能只收集 supporting literature。

---

# 19. Minimum Strategy Universe

本轮建立：

```text
>= 35
```

个与 TactiCore 有合理相关性的 canonical strategy/method entries。

不要为了数量加入大量：

```text
intraday
options
high-frequency
single-stock microstructure
```

策略。

重点覆盖以下五类。

---

# 20. Family A — Trend / Momentum

至少覆盖：

```text
time-series momentum / trend following

cross-sectional momentum

asset-class relative momentum

industry momentum

dual momentum

moving-average tactical allocation / GTAA

multi-horizon trend / trend ensemble

volatility-scaled trend

trend + inverse-volatility allocation

defensive momentum / defensive asset rotation
```

---

# 21. Family B — Portfolio / Risk Allocation

至少覆盖：

```text
1/N equal weight

static diversified allocation

inverse volatility

equal risk contribution

risk parity

mean-variance optimization

minimum variance

shrinkage minimum variance

maximum diversification

Black-Litterman

HRP

HERC
```

---

# 22. Family C — Volatility / Tactical Risk

至少覆盖：

```text
volatility targeting

volatility-managed portfolios

equity/bond tactical trend

multi-asset tactical trend

drawdown-control approaches

asset-class breadth
```

---

# 23. Family D — Established Return Premia

至少覆盖与低频 ETF allocation 有潜在关系的：

```text
value

momentum

value + momentum

carry

low-volatility / defensive equity

quality / profitability
```

对于 stock-level evidence：

必须标：

```text
TactiCore relevance = MEDIUM/LOW
```

如果不能直接迁移 ETF allocation。

---

# 24. Family E — China / ETF-Specific Open Questions

至少覆盖：

```text
China A-share momentum

China industry momentum

China sector ETF rotation

China theme ETF rotation

China ETF defensive asset rotation

ETF liquidity-aware allocation

PIT ETF universe effects

fund-launch / survivorship effects

China ETF transaction-cost implementation
```

其中某些是：

```text
research concerns
```

而非 standalone strategy。

允许使用：

```text
strategy_type = research_problem
```

如果更准确。

---

# 25. Mandatory Canonical Source Seeds

这些只是最低起点。

必须自行搜索最新、原始和反证来源，不得只使用本列表。

至少核实：

```text
Moskowitz, Ooi, Pedersen
"Time Series Momentum"
Journal of Financial Economics, 2012

Hurst, Ooi, Pedersen
"A Century of Evidence on Trend-Following Investing"

Moskowitz, Grinblatt
"Do Industries Explain Momentum?"
Journal of Finance, 1999

Asness, Moskowitz, Pedersen
"Value and Momentum Everywhere"
Journal of Finance, 2013

DeMiguel, Garlappi, Uppal
"Optimal Versus Naive Diversification:
How Inefficient Is the 1/N Portfolio Strategy?"
Review of Financial Studies, 2009

Maillard, Roncalli, Teiletche
"On the Properties of Equally-Weighted
Risk Contributions Portfolios"

Moreira, Muir
"Volatility-Managed Portfolios"
Journal of Finance, 2017

Cederburg, O'Doherty, Wang, Yan
"On the Performance of Volatility-Managed Portfolios"
Journal of Financial Economics, 2020

Faber
"A Quantitative Approach to Tactical Asset Allocation"

López de Prado
"Building Diversified Portfolios
that Outperform Out-of-Sample"
```

同时搜索：

```text
later replications
contradictory evidence
China-specific literature
```

---

# 26. Current Upstream Implementation Seeds

至少调查当前状态：

```text
PyPortfolioOpt

Riskfolio-Lib

VectorBT

RQAlpha
```

只记录与 strategy implementation 直接相关的能力。

例如：

```text
minimum volatility
mean-variance
Black-Litterman
HRP/HERC
risk measures
portfolio simulation
execution validation
```

不要立即安装任何新 dependency。

---

# 27. Human-Readable Strategy Research Map

新增：

```text
docs/STRATEGY_RESEARCH_MAP.md
```

这是以后 Principal / Agent 选择研究方向的入口。

至少包含：

```text
1. Purpose

2. External Evidence Tier Definitions

3. Strategy Families

4. Mature External Findings

5. Established Allocation Methods

6. Mixed / Contested Strategies

7. Open / Local Questions

8. Existing TactiCore Mapping

9. Closed Local Questions

10. Current Transfer Gaps

11. Candidate Future Research

12. Strategies We Should NOT Re-study From Scratch
```

---

# 28. Strategy Map Summary Table

至少给出：

| Canonical Strategy | Family | External Tier | External Conclusion | TactiCore Mapping | Local Status | Remaining Gap | Action |
| ------------------ | ------ | ------------- | ------------------- | ----------------- | ------------ | ------------- | ------ |

不要用一个：

```text
overall strategy score
```

排序。

---

# 29. Existing TactiCore Strategy Mapping

必须映射所有现有策略。

至少：

## S1

判断其 canonical mapping。

明确：

```text
local rejection
!=
global momentum rejection
```

---

## S2

映射至：

```text
time-series momentum / trend following
```

外部 evidence 应反映成熟 trend literature。

本地 gap：

```text
long-only ETF transfer
China/global ETF proxy
fallback semantics
execution
prospective stability
```

本地状态：

```text
PROSPECTIVE_SHADOW_ACTIVE
```

---

## S3A

映射至：

```text
industry momentum / sector momentum
```

说明：

```text
canonical phenomenon has external literature
but this exact China ETF implementation failed
```

---

## S3B

更接近：

```text
local aggregate breadth regime hypothesis
```

不要硬包装成已有成熟策略。

如果外部 evidence 不足：

```text
E4_OPEN_LOCAL
```

---

## S3C

映射至：

```text
per-sector time-series trend transfer
```

明确：

```text
exact local implementation rejected
```

不是：

```text
trend following globally rejected
```

---

## S4A

映射至：

```text
inverse-volatility allocation
```

应归：

```text
established allocation method
```

本地 gate rejection 只说明：

```text
this implementation did not justify
incremental local complexity
```

---

## S8A

映射到最贴近的：

```text
moving-average tactical allocation
or
single-asset time-series trend
```

根据文献审计决定准确归类。

---

## S27A

映射至：

```text
time-series trend
+
inverse-volatility sizing
```

明确：

```text
composite of mature/established components
```

而不是：

```text
novel TactiCore anomaly
```

本地状态：

```text
ADVANCE_TO_ROBUSTNESS
```

但 robustness 是否应立即执行：

```text
NOT decided in this Goal
```

---

## S30

映射至：

```text
naive/static diversification
```

强调其角色：

```text
complexity hurdle
```

而不是待寻找 alpha 的 strategy。

---

# 30. Update STRATEGY_CATALOG

修改：

```text
docs/STRATEGY_CATALOG.md
```

不要重写已有 local evidence。

对每个 local strategy 增加或统一表达：

```text
Canonical external mapping

External evidence tier

Local research question

Local lifecycle status

What the local result does NOT prove
```

原则：

```text
STRATEGY_CATALOG
=
what TactiCore implemented
and what happened locally
```

而：

```text
STRATEGY_RESEARCH_MAP
=
what the wider research world knows
and where TactiCore gaps remain
```

不要混为一份巨型文档。

---

# 31. Update AGENTS.md — Mandatory

这一步非常重要。

修改根：

```text
AGENTS.md
```

因为未来 Agent 必须自动读取这套思路。

启动检查增加：

```text
docs/STRATEGY_RESEARCH_MAP.md

research/strategy_evidence/
STRATEGY_EVIDENCE_REGISTRY.yaml
```

规则：

> Any Goal that proposes, implements, compares, tunes, or extends a strategy must perform the External Evidence Gate before touching strategy code.

如果已有 registry entry：

```text
read it first
```

如果没有：

```text
perform literature review
and add/update the entry
before coding
```

---

# 32. AGENTS Strategy Proposal Gate

在 `AGENTS.md` 写明：

未来 Agent 不得直接：

```text
"I propose strategy X"
→ code
```

必须先输出内部判断：

```text
Canonical mapping:
External tier:
External conclusion:
Relevant contradictions:
Upstream implementation:
Existing TactiCore evidence:
Remaining local gap:
Research action:
```

然后才能继续 Goal。

---

# 33. AGENTS Closed-Question Interaction

External evidence 和 local ledger 必须同时检查。

未来新 strategy proposal：

```text
External registry
        +
RESEARCH_LEDGER
        ↓
Is there actually a new question?
```

如果：

```text
external literature already answers existence
AND
local ledger already answers transfer
```

则：

```text
DO_NOT_PURSUUE
```

不得换名字重新研究。

---

# 34. Update Architecture Information Flow

更新 `ARCHITECTURE.md` 的 Goal 生成信息层级。

从当前：

```text
ARCHITECTURE
+ RESEARCH_RULES
+ RESEARCH_LEDGER
+ research artifacts
+ CURRENT_STATE
→ next Goal
```

升级成：

```text
ARCHITECTURE
+
RESEARCH_RULES
+
EXTERNAL STRATEGY EVIDENCE
+
RESEARCH_LEDGER
+
LOCAL RESEARCH ARTIFACTS
+
STRATEGY_CATALOG
+
CURRENT_STATE
→ next Goal
```

`docs/STRATEGY_RESEARCH_MAP.md` 是导航/综合视图。

---

# 35. Update RESEARCH_RULES Research Sequence

长期研究顺序升级为：

```text
External Evidence Gate
        ↓
Canonical Strategy Mapping
        ↓
Local Evidence Gap
        ↓
Predeclared Research Question
        ↓
Strategy / Upstream Implementation
        ↓
Historical Screen
        ↓
Robustness
        ↓
Execution Validation
        ↓
Prospective Candidate
```

不得跳过前三步。

---

# 36. Batch Design Rule

把以下永久规则写入 `RESEARCH_RULES.md`：

批次研究优先选择：

```text
economically orthogonal gaps
```

而不是：

```text
five nearby variants
of the same strategy
```

一个 batch 中：

```text
one strategy's observed result
must not alter another strategy's
already frozen design
```

对于 mature external strategy：

Batch 应称：

```text
Replication / Transfer Batch
```

而不是：

```text
Discovery Batch
```

---

# 37. Rejected Strategy Rule

把现有规则进一步明确：

如果一个：

```text
local implementation
```

被 REJECT：

禁止：

```text
quietly reinterpret it
as rejection of the entire
canonical literature family
```

例如：

```text
S3A rejected
≠ industry momentum disproved

S4A rejected
≠ inverse-volatility useless

S8A rejected
≠ trend following invalid
```

---

# 38. External Evidence Refresh Rule

registry 是：

```text
evidence snapshot
```

每条 entry 必须有：

```text
evidence_as_of
```

未来 Goal：

只更新：

```text
relevant entries
```

不要求每次刷新整个 registry。

如果发现：

```text
new major replication
new contradiction
new meta-analysis
major upstream implementation change
```

则更新对应 entry。

不要制造周期性维护系统。

---

# 39. Evidence Search Stop Rule

Literature research 也不能无限扩展。

对于普通 strategy entry：

通常达到以下即可停止：

```text
canonical source identified

at least one independent confirmation/review
when available

material contradiction searched

market / implementation scope understood

TactiCore gap identifiable
```

不追求：

```text
complete academic bibliography
```

---

# 40. Current Literature Map Must Be Honest

不要预设所有 tier。

本 Prompt 中的候选 tier 只是方向。

Codex 必须根据实际 evidence 决定。

特别：

```text
China momentum
industry momentum transfer
HRP superiority
volatility targeting
GTAA
```

可能存在：

```text
mixed / conditional evidence
```

必须如实分类。

---

# 41. No Citation Laundering

如果二级文章说：

```text
"paper X proves Y"
```

必须尽可能找到：

```text
paper X
```

本身。

不要让 blog/marketing page 成为：

```text
canonical evidence
```

---

# 42. No Abstract Overreach

论文研究：

```text
futures
long-short
leveraged volatility-scaled portfolio
```

不能直接登记为：

```text
proven for long-only China ETF
```

必须记录 domain mismatch。

这是 External Evidence Registry 最重要的作用之一。

---

# 43. Upstream Implementation Does Not Equal Evidence

例如存在：

```text
PyPortfolioOpt HRP
Riskfolio ERC
```

只证明：

```text
implementation exists
```

不证明：

```text
strategy economically superior
```

必须把：

```text
research evidence
```

和：

```text
software availability
```

分开。

---

# 44. Update CURRENT_STATE

完成 Batch 00 后：

`CURRENT_STATE.md` 应表达：

```text
S2 R1:
PROSPECTIVE_SHADOW_ACTIVE

Batch 01:
architect review completed

S27A:
historical baseline ADVANCE,
robustness eligible but not automatically started

External Evidence Foundation:
ESTABLISHED

Current research frontier:
EVIDENCE_INFORMED_STRATEGY_SELECTION
```

下一步写成类似：

```text
AWAIT_EXTERNAL_EVIDENCE_ARCHITECT_REVIEW
```

不要自动开始：

```text
S27 robustness
Batch 02
Theme Rotation
```

---

# 45. Update docs/goal.md

用本 Goal 替换已经完成的 Batch 01 Goal。

完成时末尾记录：

```text
Status: completed

Goal:
BATCH_00_EXTERNAL_STRATEGY_EVIDENCE_FOUNDATION

Starting HEAD:
...

Ending HEAD:
...

Registry entries:
...

External evidence tiers:
...

Existing TactiCore strategies mapped:
...

Next state:
AWAIT_EXTERNAL_EVIDENCE_ARCHITECT_REVIEW
```

---

# 46. RESEARCH_LEDGER

不要把全部 external literature 塞进：

```text
RESEARCH_LEDGER.md
```

Ledger 继续只拥有：

```text
TactiCore local research decisions
```

External literature 属于：

```text
STRATEGY_EVIDENCE_REGISTRY
```

本 Goal 只：

1. 修复确认存在的 RL-023 corrected-value drift；
2. 如果确实产生一个需要永久记录的 local meta-decision，可追加一个非常短的 entry，例如：

```text
External Evidence Gate adopted
```

但优先把永久方法放：

```text
RESEARCH_RULES
```

不要让 ledger 变成 governance log。

---

# 47. README

可以最小更新：

```text
README.md
```

增加入口：

```text
Strategy Research Map
External Strategy Evidence Registry
```

不要扩大 README。

---

# 48. Documentation Ownership After This Goal

最终明确：

```text
AGENTS.md
=
future agent startup / routing

ARCHITECTURE.md
=
system stages and ownership

RESEARCH_RULES.md
=
permanent research method

STRATEGY_EVIDENCE_REGISTRY.yaml
=
external evidence snapshot

STRATEGY_RESEARCH_MAP.md
=
human-readable external/local research map

RESEARCH_LEDGER.md
=
append-only local decisions

STRATEGY_CATALOG.md
=
implemented local strategy lifecycle

research/results/*
=
detailed local experiment evidence

CURRENT_STATE.md
=
current frontier

goal.md
=
current ephemeral task
```

不得混淆职责。

---

# 49. Important Existing Strategy Interpretation

完成后，至少能在 map/catalog 中直接回答：

```text
S2:
Is this a novel anomaly?
NO.

What is it?
A local long-only ETF transfer
of mature trend / TSMOM ideas.

What remains?
Prospective local evidence.
```

```text
S27A:
Is this a novel anomaly?
NO / mostly NO.

What is it?
Trend signal
+
established inverse-volatility sizing.

What happened locally?
Historical baseline advanced.

What remains?
Robustness and later execution,
if Principal Review authorizes it.
```

```text
S30:
Is this alpha?
NO.

What is it?
Simple-diversification complexity hurdle.
```

---

# 50. Required Strategy Research Map: Mature / Known

The finished map should clearly identify strategies for which TactiCore should normally NOT research existence from scratch.

Expected examples include, subject to actual literature verification:

```text
time-series momentum

cross-sectional momentum

industry momentum

value

value + momentum

naive diversification

classical portfolio optimization methods
```

Their remaining questions should be:

```text
transfer
implementation
local constraints
robustness
```

not rediscovery.

---

# 51. Required Map: Established Methods

Expected method-oriented entries include:

```text
inverse volatility

ERC / risk parity

minimum variance

shrinkage covariance allocation

maximum diversification

HRP/HERC

Black-Litterman
```

Research action usually:

```text
UPSTREAM_COMPARE
```

not:

```text
prove alpha exists
```

---

# 52. Required Map: Mixed / Conditional

Actively identify strategies where external evidence is materially contested.

Likely examples requiring verification:

```text
volatility-managed portfolios

volatility targeting

some China momentum formulations

GTAA / moving-average tactical allocation

HRP superiority claims
```

These are valuable future:

```text
LOCAL_ADJUDICATION
```

candidates.

---

# 53. Required Map: Open / Local

Identify problems for which TactiCore can plausibly add new evidence:

```text
China tradable ETF transfer

China theme ETF rotation

PIT ETF universe

ETF launch / survivor effects

defensive ETF selection

China-specific liquidity effects

local execution-cost effects

sector/theme overlap

asset-class breadth in available ETF universe
```

Do not automatically implement them.

---

# 54. Future Goal Template Rule

`RESEARCH_RULES.md` or `AGENTS.md` should require every future strategy Goal to begin with a short section:

```text
External Evidence Gate

Canonical strategy:
External tier:
External consensus:
Canonical sources:
Contradictory evidence:
Original implementation domain:
TactiCore domain mismatch:
Upstream implementation:
Existing local evidence:
Remaining local gap:
Research action:
```

Only after this section may the Goal define:

```text
implementation
experiment
```

---

# 55. Future Batch Selection Rule

Future Batch 02 should NOT be chosen by:

```text
highest historical CAGR
most exciting idea
current market narrative
```

It should be chosen from:

```text
remaining local evidence gaps
```

with preference for:

```text
high TactiCore relevance

external evidence quality

economic orthogonality

simple implementability

ability to distinguish mechanisms

low data-mining freedom
```

No composite score is required.

---

# 56. S27A Special Handling

Do not start S27A robustness in this Goal.

Instead registry/map must first determine:

```text
Which components are externally mature?

Which claims are already established?

What exactly did Batch 01 add locally?

What remains a legitimate robustness question?
```

Then Principal Review will decide whether:

```text
S27A robustness
```

deserves the next batch.

---

# 57. S30 Special Handling

S30 should become a permanent example of:

```text
simple benchmark before complexity
```

But do NOT hard-code:

```text
every strategy must beat S30
```

because comparator must isolate the actual mechanism.

Instead rule is:

```text
every complex strategy must face
an appropriate simple complexity hurdle
```

S30 is one important such hurdle.

---

# 58. Validation

本 Goal 主要修改文档，因此仍需运行现有 repository validation：

```bash
uv sync --extra dev

uv run pytest

uv run ruff check .
uv run ruff format --check .
uv run mypy
```

再次：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

必须 PASS。

---

# 59. Evidence Artifact Review

提交前人工/Agent 自检 registry：

```text
>=35 relevant entries

no duplicate strategy IDs

all entries have evidence tier

all entries have evidence_as_of

all entries have research_action

all HIGH-relevance entries have remaining_gap

E3 entries include contradictory search

existing S1/S2/S3/S4/S8/S27/S30 mappings complete

no unsupported "proven" claims

no external claim presented as China ETF evidence
without transfer support
```

不要为了这个检查写一个 framework。

---

# 60. Architecture Drift Audit

逐项回答：

```text
Did we add a literature crawler?
Did we add a research database?
Did we add a strategy registry service?
Did we add a workflow engine?
Did we run new backtests?
Did we tune existing strategies?
Did we modify S2 frozen inputs?
Did we start S27 robustness?
Did we start Batch 02?
Did we start Theme Rotation?
Did we introduce a dependency without a current need?
Did we confuse upstream implementation with empirical evidence?
Did we treat local rejection as global rejection?
Did we treat external evidence as local validation?
```

正常全部：

```text
NO
```

---

# 61. Required Diff

Expected meaningful changes:

```text
AGENTS.md

README.md                     # minimal, if useful

docs/ARCHITECTURE.md

docs/RESEARCH_RULES.md

docs/STRATEGY_RESEARCH_MAP.md # new

docs/STRATEGY_CATALOG.md

docs/CURRENT_STATE.md

docs/RESEARCH_LEDGER.md       # only factual correction / minimal local decision

docs/goal.md

research/strategy_evidence/
  STRATEGY_EVIDENCE_REGISTRY.yaml
```

Normally NO changes to:

```text
tacticore/**
config/**
data/**
research/experiments/**
research/results/**
research/shadow/**
tests/**
```

unless required only to fix a proven existing correctness/document inconsistency.

---

# 62. Commit

完成全部工作、验证后：

```bash
git status
git diff
```

创建一个 coherent commit。

建议 intent：

```text
establish external evidence first strategy research
```

然后：

```bash
git push
```

---

# 63. Final Report

最终向用户报告：

```text
starting HEAD
ending HEAD
commit SHA

S2 verification before
S2 verification after

Batch 01 current authoritative decisions

S27 ledger inconsistency:
confirmed? yes/no
corrected? yes/no

number of registry entries

number of:
E1
E2
E3
E4

number HIGH/MEDIUM/LOW relevance

existing TactiCore strategies mapped

canonical academic sources reviewed

contradictory evidence captured

upstream projects reviewed

files changed

architecture changes

permanent rule changes

AGENTS routing changes
```

并明确：

```text
Did this Goal run strategy backtests?
NO

Did this Goal start S27 robustness?
NO

Did this Goal start Batch 02?
NO

Did this Goal modify S2 R1?
NO

Does S2 candidate verification still pass?
YES
```

---

# 64. Stop Condition

完成以下全部即停止：

```text
External Evidence Registry built

Strategy Research Map built

Architecture updated

Research Rules updated

AGENTS routing updated

Strategy Catalog mapped

Current State updated

existing factual drift corrected

S2 candidate intact
```

不要继续实现任何新策略。

状态：

```text
BATCH_00_EXTERNAL_EVIDENCE_FOUNDATION_COMPLETE

AWAIT_EXTERNAL_EVIDENCE_ARCHITECT_REVIEW
```

---

# 65. Final Principle

```text
Do not rediscover what the community already knows.

External literature
defines the prior.

TactiCore
defines the local gap.

Mature anomaly
→ transfer validation.

Established method
→ upstream comparison.

Mixed literature
→ local adjudication.

Open local problem
→ new hypothesis.

Local failure
does not invalidate global evidence.

External success
does not guarantee local success.

Implementation existence
does not prove economic superiority.

Simple benchmark
is the complexity hurdle.

Literature first.
Upstream first.
Local evidence second.
Infrastructure last.
```

---

Status: completed

Goal: BATCH_00_EXTERNAL_STRATEGY_EVIDENCE_FOUNDATION

Starting HEAD: f64bfc1c8e41e757e558599b461c07ce3f8a069f

Ending HEAD: recorded by completion commit

Registry entries: 38 (E1=11, E2=8, E3=11, E4=8; HIGH=23, MEDIUM=10, LOW=5)

Existing TactiCore strategies mapped: S1, S2, S3A, S3B, S3C, S4A, S8A, S27A, S30

Next state: AWAIT_EXTERNAL_EVIDENCE_ARCHITECT_REVIEW

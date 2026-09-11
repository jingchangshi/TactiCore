# Goal: S2 Research Candidate R1 Freeze + Prospective Shadow Protocol V1

Repository:

```text
https://github.com/jingchangshi/TactiCore
```

Role:

```text
Principal Quant Research Engineer
+
Research Architecture Reviewer
+
Research Reproducibility Owner
```

---

# 0. Why This Work Exists

TactiCore 当前已经完成一条较完整的 S2 历史研究闭环。

预期已有阶段包括：

```text
canonical data semantics             CLOSED
S2 signal credibility                CLOSED
VectorBT economic screening          PASS
RQAlpha authoritative execution      PASS
RQAlpha upstream execution closure   PASS
coarse parameter plateau             PASS
```

当前预期候选状态：

```text
S2 Research Candidate R1
```

当前真正缺失的不是更多历史研究，而是：

> 在历史数据已经被多次观察后，如何从一个明确时间点开始，以完全冻结的候选语义持续积累真正 prospective evidence。

本 Goal 的目标是：

```text
1. 冻结 S2 Research Candidate R1
2. 冻结 historical / prospective 边界
3. 建立轻量 prospective shadow protocol
4. 固定数据 vintage 和 decision record 规则
5. 固定未来 review eligibility
6. 防止未来研究过程中隐形修改 R1
7. 将 S2 转为 PROSPECTIVE_SHADOW_ACTIVE
8. 为下一阶段解锁 S3 research
```

本 Goal 不以获得新的策略收益结果为目的。

当前日期尚未提供足够的 prospective observation。

因此：

```text
NO prospective PASS/REJECT decision
```

应该是正常结果。

---

# 1. Repository First

必须首先读取最新 remote `main`。

不要依据：

```text
本 Goal 中写出的预期状态
上一轮对话
Codex 的上一轮完成报告
旧的 CURRENT_STATE
旧的 goal.md
记忆
```

直接继续实现。

首先读取根级：

```text
AGENTS.md
```

并遵守其中的文档路由与 authority order。

至少读取：

```text
README.md

AGENTS.md

docs/ARCHITECTURE.md
docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/goal.md

config/strategy.toml
config/universe.csv

data/canonical/README.md
data/canonical/provenance.json

tacticore/data/prices.py
tacticore/data/tushare.py
tacticore/data/universe.py

tacticore/strategies/multi_asset_trend.py

tacticore/engines/vectorbt_adapter.py
tacticore/engines/rqalpha_adapter.py

research/experiments/download_tushare_data.py
research/experiments/run_s2_parameter_plateau.py
research/experiments/run_s2_rqalpha_validation.py

research/results/S2_PARAMETER_PLATEAU_V1.md
research/results/S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1.md
```

并检查相关 tests。

记录：

```text
starting HEAD
recent commits
working tree
dependency versions
canonical historical cutoff
canonical price hash
trading-calendar hash
strategy config
universe
S2 current lifecycle state
```

如果实际仓库状态与本 Goal 矛盾：

```text
repository evidence wins
```

---

# 2. Respect AGENTS.md Routing

不要修改已经稳定的根级 `AGENTS.md`，除非发现真实路由错误。

预期本 Goal：

```text
AGENTS.md = unchanged
```

不得将：

```text
S2 R1 当前状态
candidate hash
prospective 日期
未来 promotion threshold
当前收益指标
```

加入 AGENTS.md。

AGENTS.md 仍只负责：

```text
bootstrap
+
routing
+
authority
+
architecture-drift protection
```

---

# 3. Previously Closed Questions Stay Closed

首先读取：

```text
docs/RESEARCH_LEDGER.md
```

特别确认已有 S2 closed entries。

不得重新研究：

```text
Tushare fund_daily / fund_adj 语义
historical canonical data credibility
missing-value policy
UNAVAILABLE vs NEGATIVE_SIGNAL
200 valid-observation semantics
month-end lookahead
V1 missing-row issue
V1 vs V2A
V2A vs V2B
general S2 signal credibility
historical rolling 3Y / 5Y
historical cost sensitivity
RQAlpha 5.6.5 execution failure
RQAlpha 6.3 native partial-fill closure
160 / 180 / 200 / 220 / 240 parameter plateau
```

尤其不要重新运行参数搜索。

预期：

```text
RL-015
S2 coarse parameter plateau
=
CLOSED
```

如果确实需要重开一个关闭条目，必须同时指出：

```text
ledger ID
new contradictory evidence
exact bounded scope
```

否则禁止重开。

---

# 4. Confirm the Research Frontier

预期当前状态是：

```text
S1
REJECTED

S2 V1
REJECTED

S2 V2B
historical economic screen: PASS
execution architecture: PASS
parameter plateau: PASS

S2 Research Candidate R1
FROZEN CANDIDATE TO BE FORMALIZED

S3
not yet active
```

预期 S2 R1 语义：

```text
trend_window = 200 valid observations

signal day itself must have a valid price

monthly review

month-end close generates signal

execution no earlier than next canonical observation day

SIGNAL_CHANGE_ONLY

equal sleeves among eligible risk assets

negative-trend sleeve → existing fallback asset

existing risk universe

existing canonical missing-data semantics

existing fee / slippage assumptions

RQAlpha 6.3 native
partial_fill_on_insufficient_cash = true
```

必须从源码、配置和研究产物重新确认。

不要从本 Prompt 复制这些事实而不验证。

---

# 5. Historical / Prospective Boundary

当前历史研究数据预计截止：

```text
2026-08-31
```

必须从：

```text
data/canonical/provenance.json
```

实际确认。

一旦确认，将其定义为：

```text
historical_cutoff
```

真正 prospective 数据必须满足：

```text
date > historical_cutoff
```

预期：

```text
prospective_start = 2026-09-01
```

任何：

```text
2012–2026-08
2013–2026
2023–2026
rolling historical window
```

均不得再称为：

```text
untouched OOS
true prospective
forward evidence
```

它们只能称为：

```text
historical evidence
historical robustness
```

---

# 6. Create a Machine-Readable Candidate Manifest

新增：

```text
research/shadow/s2_r1/candidate_manifest.json
```

其唯一作用是：

> 机器可验证地冻结 S2 Research Candidate R1 的身份和输入边界。

不要建设 candidate registry、数据库或 lifecycle framework。

Manifest 至少包含：

```text
candidate_id
candidate_version
strategy_family
strategy_version

freeze_commit
freeze_timestamp

historical_cutoff
prospective_start

strategy_semantics

execution_semantics

framework_versions

data_contract

file_hashes
```

建议结构类似：

```json
{
  "candidate_id": "S2_R1",
  "strategy": "multi_asset_trend_v2b",
  "historical_cutoff": "2026-08-31",
  "prospective_start": "2026-09-01",
  "trend_window": 200,
  "rebalance_frequency": "monthly",
  "execution_policy": "SIGNAL_CHANGE_ONLY",
  "allocation": "equal_sleeves",
  "rqalpha_partial_fill_on_insufficient_cash": true
}
```

实际字段必须基于当前仓库事实生成。

---

# 7. Manifest Must Freeze Important Files by Hash

至少记录 SHA-256：

```text
config/strategy.toml
config/universe.csv

data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json

tacticore/strategies/multi_asset_trend.py

tacticore/engines/rqalpha_adapter.py
```

如果当前执行闭环还依赖其他明确文件，可以加入。

不要把整个仓库做 hash registry。

范围只限：

> 能改变 R1 经济语义、数据输入或执行语义的关键文件。

同时记录：

```text
git commit SHA
```

Git commit 与文件 hash 两者都保留。

---

# 8. Candidate Versioning Rule

在 prospective 阶段：

如果以下任意内容发生实质变化：

```text
trend window
valid-observation definition
signal timing
execution timing
SIGNAL_CHANGE_ONLY policy
asset universe
fallback asset
allocation rule
canonical missing-data policy
cost assumption
RQAlpha execution policy
```

则不得继续称为：

```text
S2_R1
```

必须建立新的 candidate version，例如：

```text
S2_R2
```

或者：

```text
S2_R1B
```

但优先保持简单顺序版本：

```text
R1
R2
R3
```

不得修改旧 manifest 来“保持最新”。

旧 candidate 保持历史可复现。

---

# 9. Add a Permanent Prospective Research Rule

对：

```text
docs/RESEARCH_RULES.md
```

做一个小而永久的修改。

新增类似：

```text
Prospective Candidate / Preregistration Rule
```

永久规则至少表达：

在任何真正 prospective 结果产生之前，必须冻结：

```text
candidate semantics
historical cutoff
prospective start
evaluation protocol
review eligibility
reopen / invalidation conditions
```

一旦 prospective observation 已经产生：

```text
不得依据看到的结果修改原 candidate
```

如果需要改变：

```text
create a new candidate version
```

不得：

```text
retroactively change old target decisions
backfill a new strategy into an old prospective period
silently replace old data vintages
```

这一规则是永久研究方法。

因此应该进入：

```text
RESEARCH_RULES.md
```

不要将 S2 的具体 200 日参数或具体日期写成通用规则。

---

# 10. Do NOT Change ARCHITECTURE Unless Necessary

本 Goal 正常情况下没有新的系统所有权边界。

因此预期：

```text
docs/ARCHITECTURE.md
=
unchanged
```

Prospective shadow 是：

```text
Evidence / Decision
```

阶段的一种研究模式，而不是新的平台层。

不要因为本 Goal 新增：

```text
Prospective Layer
Shadow Engine
Candidate Management Layer
Research Registry Layer
```

如果没有真实架构需求。

只有发现现有 ARCHITECTURE 确实无法表达 responsibility boundary 时才做最小修订。

---

# 11. Prospective Data Vintage Policy

当前：

```text
data/canonical/
```

中的 historical dataset 已经承载过去全部研究证据。

不要在 prospective 阶段简单：

```text
download 2012 → current_date
↓
overwrite data/canonical/*
```

然后把它当作原来的历史输入。

这会混淆：

```text
what was frozen then
vs
what the vendor returns today
```

定义最小 prospective data policy。

历史基线：

```text
data/canonical/
```

继续代表截至 historical cutoff 的冻结历史研究数据。

新的 prospective 数据写入 candidate-specific 目录，例如：

```text
research/shadow/s2_r1/vintages/
```

未来每次数据拉取形成类似：

```text
research/shadow/s2_r1/vintages/2026-09-30/
research/shadow/s2_r1/vintages/2026-10-30/
...
```

实际日期按交易日决定。

不要在本 Goal 生成不存在的未来数据目录。

只定义规则和代码路径。

---

# 12. Reuse Existing Tushare Capability

优先复用：

```text
research/experiments/download_tushare_data.py
tacticore/data/tushare.py
```

现有 downloader 已支持：

```text
--start-date
--end-date
--output-dir
```

不要建立：

```text
DataProvider
DataLake
PITDatabase
DataWarehouse
IncrementalMarketDataPlatform
```

如现有 downloader 足够，则直接复用。

如确有一个非常小的 candidate-specific wrapper 能显著降低操作错误，可以增加，但必须保持薄。

例如未来允许：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --as-of YYYY-MM-DD \
  --prospective-data-dir ...
```

但这个 runner：

```text
不是 scheduler
不是 daemon
不是 service
不是 production pipeline
```

---

# 13. Historical Data Must Not Be Mutated

Prospective experiment 必须保护：

```text
data/canonical/etf_adjusted_close.csv
data/canonical/trading_calendar.csv
data/canonical/provenance.json
```

在 S2 R1 生命周期中保持 historical freeze。

未来 signal 计算的逻辑输入应概念上是：

```text
frozen historical data
        +
prospective delta available as-of decision date
        ↓
candidate signal
```

而不是：

```text
today's freshly redownloaded entire history
        ↓
reconstructed old candidate
```

如果 prospective delta 与 historical range 重叠：

默认拒绝覆盖。

除非：

```text
overlapping values are byte/semantically identical
```

且该行为被明确测试。

任何 vendor historical correction：

```text
不得静默改写 old candidate history
```

应记录为新的数据事件，后续另行决定是否建立新 candidate。

---

# 14. Create Prospective Protocol Documentation

新增：

```text
research/shadow/s2_r1/README.md
```

或者：

```text
research/shadow/s2_r1/PROTOCOL.md
```

二选一即可。

不要重复创建多个相似文档。

该协议必须明确：

```text
candidate identity
historical cutoff
prospective start
data-vintage policy
signal generation time
decision freeze time
execution observation time
record schema
review eligibility
candidate invalidation rules
what is NOT allowed
```

---

# 15. Signal / Decision Timeline

协议应明确：

对于每个正常 monthly review：

```text
月末交易日收盘
        ↓
仅使用截至该时点已知数据
        ↓
S2 R1 计算 signal
        ↓
生成 desired target
        ↓
冻结 Shadow Decision Record
        ↓
下一 canonical observation day
        ↓
观察 / 回放 RQAlpha execution semantics
        ↓
记录 execution evidence
        ↓
未来继续累计 portfolio evidence
```

关键要求：

> decision record 必须在其 outcome 被未来数据揭示之前形成。

不能在未来数据已知后：

```text
backfill
reconstruct
rewrite
```

旧 decision。

---

# 16. Prospective Record Schema

建立一个最小 append-only schema。

可以选择：

```text
research/shadow/s2_r1/observations.csv
```

或者：

```text
JSONL
```

优先使用简单、Git diff 友好的格式。

不要建数据库。

字段至少覆盖：

## Identity

```text
candidate_id
protocol_version
```

## Data Vintage

```text
record_generated_at
data_as_of
vintage_identifier
historical_manifest_hash
prospective_data_hash
```

## Signal

```text
signal_date
eligible_assets
trend_states
```

## Decision

```text
target_changed
desired_targets
action_required
```

## Execution

在执行信息真正可获得以后记录：

```text
execution_date
execution_status
realized_weights
cash_weight
target_deviation
```

## Portfolio Evidence

可以包含：

```text
portfolio_value
drawdown
turnover
```

但不要为了这些字段复制 RQAlpha 的 portfolio accounting。

尽量引用或压缩框架原生结果。

---

# 17. Do Not Pretend Future Data Exists

当前 Goal 的正常结果可以只有：

```text
manifest
protocol
record schema
manual prospective runner
tests
documentation
```

不要为了让 CSV 非空而：

```text
生成 synthetic prospective market data
把 2026-08 的历史数据当 prospective
把 2026-09-01 之后尚未到月末的数据硬凑成月度结果
```

如果截至实际执行 Goal 时：

```text
尚未形成第一个符合协议的 prospective month-end decision
```

则：

```text
observations = empty/header-only
```

是正确状态。

---

# 18. Optional Minimal Manual Shadow Runner

如果实现价值明确，可增加：

```text
research/experiments/run_s2_r1_shadow.py
```

其职责必须严格限定为：

```text
load candidate manifest

verify hashes / candidate identity

load frozen historical data

load one candidate-specific prospective vintage

validate no forbidden historical mutation

combine data in memory

generate S2 R1 signal as-of supplied date

generate a shadow decision artifact

optionally summarize execution evidence
when such evidence already exists
```

不得：

```text
automatically change strategy
download unknown additional providers
schedule itself
send notifications
place broker orders
maintain database
run continuously
```

---

# 19. Runner Must Be As-Of Driven

如果增加 runner，要求显式参数：

```text
--as-of
```

而不是默认读取：

```text
today
latest available file
```

来决定研究时点。

这样可以保证：

```text
reproducible
+
auditable
+
no hidden wall-clock dependency
```

示例：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --as-of 2026-09-30 \
  --vintage-dir research/shadow/s2_r1/vintages/2026-09-30
```

如果 `--as-of`：

```text
<= historical_cutoff
```

应拒绝 prospective mode。

如果数据中包含：

```text
as-of 之后的观测
```

不得使用。

---

# 20. No Same-Close Execution

继续保护已经关闭的时点语义：

```text
month-end close
    ↓
signal
    ↓
next canonical observation
    ↓
execution
```

Prospective runner 不得为了方便改成：

```text
same-close execution
```

这属于 R1 candidate semantic drift。

---

# 21. Prospectively Freeze Review Eligibility

必须在结果出现前定义：

> 什么情况下才有资格进行正式 prospective review。

不要定义历史收益最大化阈值。

首先冻结 evidence quantity floor。

建议：

## Interim Review

不得早于：

```text
12 calendar months
```

并且应有实际 prospective decision history。

Interim review 仅用于：

```text
integrity
execution
operational burden
qualitative consistency
```

不能凭 12 个月结果宣布生产有效。

## Production-Candidate Eligibility

建议同时满足：

```text
>= 18 calendar months

AND

>= 10 genuine target-change execution events
```

后才允许进入：

```text
production-candidate review
```

这里的 10 个事件应基于当前历史低频特征进行解释，但不得根据未来结果调整。

如果实际仓库证据支持更合理的预注册数量，可以调整一次。

但必须在本 Goal 完成时永久冻结。

---

# 22. Do Not Predefine a Profit Target

Prospective protocol 不应包含类似：

```text
CAGR > 8%
Sharpe > 1
return > benchmark by X%
```

这种短样本下容易数据挖掘的 promotion rule。

正式 future review 应综合：

```text
return/risk consistency
drawdown
signal behavior
execution deviation
turnover
maintenance burden
unexpected failure modes
```

相对 historical expectation 判断。

本 Goal 重点冻结：

```text
what will be observed
when it may be reviewed
what changes are forbidden
```

而不是预测未来必须达到哪个收益数字。

---

# 23. Early Invalidation Conditions

允许 prospective candidate 在最短 review period 前被标记为：

```text
INVALIDATED
```

但只允许清晰结构性原因。

例如：

```text
candidate manifest integrity failure

strategy implementation no longer matches manifest

canonical data semantics changed

universe instrument became unusable
in a way that invalidates candidate semantics

RQAlpha native execution semantics became incompatible

material implementation bug
that means the prospective decision was not actually R1
```

不要因为：

```text
连续三个月亏损
某个月回撤大
短期跑输 benchmark
```

就提前优化或修改 R1。

短期市场结果不是协议违规。

---

# 24. Candidate Integrity Failure vs Strategy Failure

必须严格区分：

```text
CANDIDATE_INVALIDATED
```

和：

```text
STRATEGY_PERFORMANCE_WEAK
```

前者表示：

```text
无法继续证明我们运行的是被冻结的 R1
```

后者表示：

```text
R1 确实按协议运行，
但未来表现可能不佳
```

不要混为一谈。

---

# 25. Existing Historical Canonical Remains Historical Evidence

不要修改现有 historical research artifacts。

特别不要因为建立 prospective protocol 就重新生成：

```text
S2_PARAMETER_PLATEAU_V1
S2_RQALPHA_UPSTREAM_EXECUTION_CLOSURE_V1
historical rolling evidence
cost sensitivity evidence
```

这些已经属于 frozen historical evidence。

---

# 26. Add Research Ledger Entries

对：

```text
docs/RESEARCH_LEDGER.md
```

只追加，不重写历史。

建议新增两个轻量条目。

## RL-016 S2 Research Candidate R1 Freeze

记录：

```text
candidate ID
freeze commit
historical cutoff
frozen semantics
manifest path
frozen hashes
status
reopen / replacement rule
```

状态可为：

```text
CLOSED
```

因为“R1 是什么”在本 Goal 完成后应该已经关闭。

---

## RL-017 S2 Prospective Shadow Protocol V1

记录：

```text
question
protocol start
historical cutoff
review eligibility
record location
candidate integrity rules
current state
```

如果尚未积累足够未来数据：

状态建议：

```text
ACTIVE
```

因为 prospective evidence 正在等待时间积累。

不要创建 ledger 状态机代码。

---

# 27. CURRENT_STATE After This Goal

完成后：

```text
docs/CURRENT_STATE.md
```

应保持很短。

预期变为：

```text
Current candidate:
S2 Research Candidate R1

Candidate state:
FROZEN

Prospective state:
PROSPECTIVE_SHADOW_ACTIVE

Historical cutoff:
2026-08-31

Latest decisive evidence:
parameter plateau passed
candidate + protocol frozen

Current blocker:
insufficient future prospective observations

Next S2 action:
accumulate evidence without changing R1

Next active research direction:
S3 transparent baseline / hypothesis research
```

不要把完整 protocol 复制进 CURRENT_STATE。

链接相应 manifest、protocol 和 ledger。

---

# 28. Update STRATEGY_CATALOG

更新：

```text
docs/STRATEGY_CATALOG.md
```

S2 生命周期应表示：

```text
economic screening          PASS
execution closure           PASS
parameter plateau           PASS
Research Candidate R1       FROZEN
prospective shadow          ACTIVE
production candidate        NO
```

同时修正 S3 unlock condition。

旧逻辑类似：

```text
S3 waits until S2 next robustness decision
```

参数 robustness 已经完成。

完成本 Goal 后：

```text
S3 may become the next active research family
while frozen S2 R1 continues accumulating prospective evidence.
```

但明确：

> 本 Goal 不实现 S3。

---

# 29. Why S3 Should Unlock After Protocol Freeze

Prospective evidence 的积累受：

```text
calendar time
```

限制。

不能要求：

```text
Codex
Agent
more backtests
```

加速真实未来市场。

因此不应该：

```text
freeze whole TactiCore development
for 12–18 months
```

正确模型是：

```text
                  S2 R1
                    │
               candidate frozen
                    │
              shadow protocol
                    │
                    ▼
          prospective evidence
          accumulates over time
                    │
                    │
          ┌─────────┴──────────┐
          │                    │
          ▼                    ▼
   future S2 review       S3 active research
```

S2 R1 与 S3 在此阶段不是互相污染的参数竞争。

因为：

```text
S2 R1 is immutable
```

---

# 30. Do NOT Start S3 in This Goal

即使 `STRATEGY_CATALOG.md` 被修改为允许下一 Goal 开始 S3，本 Goal 也必须停止。

禁止顺手：

```text
设计 S3 signal
下载新的行业数据
增加 sector universe
建立 rotation strategy
运行 S3 backtest
```

Goal completion 后：

```text
next active research direction = S3
```

即可。

---

# 31. Tests

增加最少、但高价值的测试。

如果增加 manifest / runner，至少保护：

### Candidate identity

```text
candidate_id == S2_R1
trend_window == current frozen baseline
historical_cutoff matches frozen canonical
prospective_start > historical_cutoff
```

### File integrity

测试 manifest 中关键文件 hash 能与仓库当前 frozen inputs 对应。

### Strategy freeze

确保 prospective runner 没有自行修改：

```text
trend_window
universe
fallback
fees
slippage
SIGNAL_CHANGE_ONLY
```

### Data boundary

确保：

```text
prospective dates <= historical_cutoff
```

不会被接受为 prospective observation。

### No future leakage

对于：

```text
--as-of X
```

只允许使用：

```text
date <= X
```

的数据。

### Historical mutation protection

如果 prospective vintage 与 historical range 有冲突且值不同：

```text
fail
```

不要静默覆盖。

### Empty prospective period

没有合法未来 signal 时：

```text
no fabricated observation
```

应是有效结果，而不是测试失败。

---

# 32. Do Not Test Framework Internals

不要 unit-test：

```text
VectorBT accounting
RQAlpha matching
RQAlpha partial fill algorithm
Tushare internal API behavior
```

只测试：

```text
TactiCore candidate freeze
protocol integrity
data boundary
as-of semantics
record construction
```

---

# 33. Expected File Changes

合理的目标 diff 应接近：

```text
research/shadow/s2_r1/candidate_manifest.json
research/shadow/s2_r1/README.md

research/experiments/run_s2_r1_shadow.py   # only if useful

tests/test_s2_r1_shadow.py

research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md

docs/RESEARCH_RULES.md
docs/RESEARCH_LEDGER.md
docs/CURRENT_STATE.md
docs/STRATEGY_CATALOG.md
docs/goal.md
README.md                                  # only if a short discoverability link helps
```

正常情况下：

```text
AGENTS.md       unchanged
ARCHITECTURE.md unchanged
strategy code   unchanged
VectorBT adapter unchanged
RQAlpha adapter unchanged
```

如果大量 core source 被修改：

```text
STOP
```

重新检查是否发生 architecture drift。

---

# 34. Completion Report Artifact

新增：

```text
research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md
```

必须记录：

```text
starting HEAD
candidate freeze commit
candidate ID
historical cutoff
prospective start
manifest path
manifest hash
frozen input hashes
protocol version
data vintage policy
decision timing policy
review eligibility
candidate invalidation rules
files changed
tests
what remains unproven
next active research direction
```

不要伪造 prospective performance。

如果尚无未来 month-end observation，应明确写：

```text
No prospective performance conclusion exists yet.
```

---

# 35. docs/goal.md

用本 Goal 替换已经完成的旧 Goal。

不要无限累积多个完成 Goal。

完成时可在文末增加：

```text
Status: completed

Decision:
ACTIVATE_S2_R1_PROSPECTIVE_SHADOW
```

以及权威结果指针：

```text
research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md
```

但所有永久规则和状态必须已经写入各自权威文档。

---

# 36. Decision at End of This Goal

正常成功决策：

```text
ACTIVATE_S2_R1_PROSPECTIVE_SHADOW
```

条件：

```text
candidate identity frozen
manifest reproducible
historical cutoff explicit
prospective data cannot overwrite historical baseline
protocol preregistered
as-of semantics explicit
record schema ready
review eligibility frozen
candidate-version rule documented
tests pass
```

然后：

```text
S2 Research Candidate R1
→ PROSPECTIVE_SHADOW_ACTIVE
```

并：

```text
next active research family
→ S3
```

---

# 37. Alternative Decision: REVISE_PROTOCOL

只有发现协议本身无法做到：

```text
reproducible candidate identity
historical/prospective separation
as-of correctness
```

时允许：

```text
REVISE_S2_R1_PROSPECTIVE_PROTOCOL
```

必须指出：

```text
one concrete blocker
one bounded next fix
```

不得以“未来数据还没来”为理由 REVISE。

等待未来数据是正常状态。

---

# 38. Architecture Drift Audit

完成前逐项回答：

```text
Did we modify S2 R1 economic semantics?

Did we rerun a CLOSED historical investigation?

Did we search for a new optimal parameter?

Did we overwrite the historical canonical dataset?

Did we build a data platform?

Did we build a scheduler / daemon?

Did we build a candidate registry?

Did we build a governance framework?

Did we duplicate VectorBT capability?

Did we duplicate RQAlpha capability?

Did we put transient candidate data into AGENTS.md?

Did we change ARCHITECTURE without a real architecture change?

Did we fabricate prospective evidence?

Did we use data after the stated as-of date?

Did we start S3 inside this Goal?
```

Normal answers应为：

```text
NO
```

任何无法解释的 YES 必须在提交前修正。

---

# 39. Validation

执行仓库当前正式检查。

预期至少：

```text
uv sync --extra dev

uv run pytest

uv run ruff check .

uv run ruff format --check .

uv run mypy
```

如果新增 shadow runner：

运行能够验证 candidate manifest / frozen historical state 的安全模式。

例如：

```text
uv run python research/experiments/run_s2_r1_shadow.py \
  --verify-candidate
```

如果不存在未来 month-end data：

不要强迫生成 observation。

验证：

```text
candidate verification succeeds
prospective record count may remain zero
```

---

# 40. Do Not Add CI in This Goal

当前如果仍无 GitHub Actions gate，不在本 Goal 处理。

Prospective protocol 是当前研究主线。

不要把它扩展成：

```text
CI modernization
release automation
branch protection
deployment
```

这些可以以后独立维护。

---

# 41. Commit and Push

完成全部验证后：

```text
git status
git diff
```

人工检查完整 diff。

确认：

```text
no token
no credentials
no temporary environment
no generated framework cache
no unintended canonical overwrite
```

形成一个 coherent commit。

建议 commit intent：

```text
freeze S2 R1 and activate prospective shadow protocol
```

随后 push 当前分支。

---

# 42. Final Report

最终报告必须给出：

```text
starting HEAD
ending HEAD
commit SHA

files added
files modified

candidate ID
historical cutoff
prospective start

candidate manifest hash

frozen strategy/config/universe/data hashes

protocol version

review eligibility

tests executed

prospective observations currently available
```

并明确回答：

```text
Was S2 R1 modified?
YES / NO

Were historical CLOSED questions reopened?
YES / NO

Was historical canonical data overwritten?
YES / NO

Was any future evidence fabricated?
YES / NO

Was a new generic platform/framework created?
YES / NO

Is S2 R1 now prospective-shadow active?
YES / NO

Is S2 a production candidate?
NO

Is S3 implemented in this Goal?
NO

Is S3 unlocked as the next active research family?
YES / NO
```

---

# 43. Expected Final Repository State

成功以后：

```text
                         TactiCore

                   ┌─────────────────┐
                   │ Stable Contract │
                   │   AGENTS.md     │
                   └────────┬────────┘
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
       Architecture      Rules          Ledger
             │              │              │
             └──────────────┼──────────────┘
                            │
                            ▼
                    Historical Research
                            │
                  S2 V2B fully reviewed
                            │
                            ▼
                S2 Research Candidate R1
                         FROZEN
                            │
                    2026-08-31 cutoff
                            │
════════════════════════════╪════════════════════════════
 Historical                 │                  Prospective
                            │
                            ▼
               Shadow Protocol V1
                            │
                     preregistered
                            │
                            ▼
                PROSPECTIVE_SHADOW_ACTIVE
                      /             \
                     /               \
                    ▼                 ▼
           future S2 evidence      S3 research
                    │
                    ▼
          production-candidate gate
                    │
                    ▼
             tradability review
                    │
                    ▼
        low-frequency decision product
```

---

# 44. Final Principle

```text
Do not manufacture more historical evidence
when the real missing variable is future time.

Freeze before observing.

Record before outcome.

Never rewrite an old candidate
to improve its future record.

Historical canonical stays frozen.

Future vintages are append-only evidence.

S2 R1 waits for the market.

TactiCore continues research through S3.

Strategy research > infrastructure engineering.
```

---

## 完成状态

Status: completed

Decision: `ACTIVATE_S2_R1_PROSPECTIVE_SHADOW`

权威结果：[S2 R1 前瞻影子协议报告](../research/results/S2_R1_PROSPECTIVE_PROTOCOL_V1.md)。

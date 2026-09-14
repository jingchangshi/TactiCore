# DUAL_CANDIDATE_PROSPECTIVE_AUDIT_V1

本记录在两个活动前瞻候选的任何实现改动**之前**产生，只做审计，不做实现、不做激活、不生成
observation、不下载任何数据。

## 1. 基线与取证边界

| 项 | 值 |
| --- | --- |
| Workspace | TactiCore |
| STARTING_HEAD | `4a1bf8c` |
| Branch | `main` |
| Working tree | clean；HEAD diff 为空 |
| S2 observations | `0`（仅表头） |
| S4C observations | `0`（仅表头） |
| Candidate vintage 目录 | 不存在 |
| 真实 2026-09 市场数据 | **未下载、未冻结、未查看** |

本审计只读取：冻结身份（两个 `candidate_manifest.json`）、候选级 lifecycle artifact、
`research/shadow/*/observations.csv`（仅表头）、`data/canonical/`（截止 `2026-08-31`）、
runner/verifier 源码、authority docs 与既有测试。任何 `2026-09-01..2026-09-30`
真实价格都不曾进入本审计。

## 2. 逐项审计

审计对象是两个候选各自的 prospective path：`S2_R1`（时序趋势，`SIGNAL_CHANGE_ONLY`）与
`S4C_R1`（无杠杆 ERC 风险预算，月度提交）。

| 不变量 | S2_R1 | S4C_R1 | 结论 |
| --- | --- | --- | --- |
| Candidate identity immutability | PASS | PASS | 冻结 manifest、hash 与框架身份都稳固 |
| Historical cutoff | PASS | PASS | 两者都绑定 `2026-08-31` |
| First eligible signal | PARTIAL | PASS | S2 由月度语义 + `prospective_start` 推出 `2026-09-30`；S4C 显式冻结 |
| Lifecycle / activation | PASS | PASS | S2 保持 active 且不补造 activation；S4C 由不可变 `activation.json` 描述 |
| Explicit as-of | PASS | PASS | 两个生产决策路径都要求显式 `--as-of` |
| Candidate-specific canonical vintage path | **GAP** | PASS | S2 接受任意 `--vintage-dir`；S4C 在读取文件前校验 canonical 位置 |
| Vintage authenticity | **GAP** | **GAP** | 两者都只要求 `provenance.json` 存在 |
| Provenance parsing / hash verification | **GAP** | **GAP** | 前瞻 loader 都不校验 source、请求日期、时间戳、行数或 provenance 声明的文件 hash |
| Price after as-of rejection | PASS | PASS | 两者都拒绝 as-of 之后的行情行 |
| Historical overlap validation | PASS | PASS | 重叠行逐值比较 |
| Price/calendar as-of 区分 | **GAP** | **GAP** | 当前 provenance 模型把下载截止日与日历覆盖混为一谈；协议必须区分 `price_as_of` 与 `calendar_as_of` |
| Decision generation timestamp | **GAP** | PARTIAL | S2 无时间戳校验；S4C 只拒绝早于 signal date 的时间戳 |
| Late / backfilled decision rejection | **GAP** | **GAP** | 在执行结果已可观察后数日生成的 decision 目前可以通过 |
| Decision 不含 execution 结果 | 仅结构 | PASS | S4C 显式检查 execution-only 字段；S2 只是留空，缺少同等强制 |
| Append-only decision | PARTIAL | PASS | S2 拒绝重复 signal date，但允许任意 record 目的地；S4C 证明了重复拒绝与字节不变 |
| Execution-row completeness | **GAP** | **GAP** | S2 没有 execution 写入器；S4C 接受实质上只含日期/类型的 execution 行 |
| Execution evidence binding | **GAP** | **GAP** | append 前没有强制的 RQAlpha evidence path/hash/框架身份绑定 |
| Framework identity | PASS | PASS | 冻结版本被机器校验 |
| Integrity failure vs performance weakness | PASS | PASS | 两者协议都已分离这两个概念 |
| Production CLI authorization | **GAP** | PASS | S2 暴露 `--record-path` 与任意 vintage 路径；S4C 生产 CLI 不暴露 lifecycle/record 覆盖 |
| Test coverage | PARTIAL | PARTIAL | S4C 覆盖 activation/路径/idempotency；两者都没有覆盖 provenance 真实性、时间上界与完整 execution evidence |
| Operational burden | ACCEPTABLE | ACCEPTABLE | 月频节奏与低维护目标相容 |
| Future-proof strict verification | PASS | **GAP** | `verify_s4c_r1_candidate.py --verify-candidate` 仍假定 header-only / 未观测状态，会拒绝合法的未来 observation |

## 3. 候选级发现

### 3.1 S2_R1

S2 的证据边界**明显更弱**：canonical vintage 位置与 canonical observation 路径都未被 CLI 授权；
provenance 不透明；decision 时间未被 seal；execution append 与完整性尚不存在。

**不得**为 S2 补造 S4C 风格的历史 activation artifact。S2 的历史生命周期表示保持不变。

### 3.2 S4C_R1

S4C 的 lifecycle 授权与 canonical 写入路径控制明显更强，但此前的 activation review
**高估**了 decision-before-execution：`record_generated_at >= signal_date` 不能阻止晚到的回填。
provenance 真实性与 execution 完整性同样尚未关闭。

S4C 候选 README 仍描述 pre-activation 状态。机器权威是无歧义的（`activation.json` 加上
authority docs），因此这是**非阻塞**的历史文档不一致；不得仅为让行文"当前化"而改写候选历史。

独立 S4C 冻结候选 verifier 也保留了 pre-activation / header-only 假设；后续实现必须让未来的真实
cycle 可验证，同时不削弱不可变 manifest 契约。

## 4. 共享阻塞

```text
1. machine-verified prospective provenance
2. 显式 price_as_of 与已知日历覆盖语义的区分
3. 阻止晚到 decision 重建的时间上界
4. Git 分离的 decision 与 execution 证据
5. append 之前必须完整的 execution 行
6. RQAlpha evidence path/hash 绑定
7. 失败/重复操作不改变 evidence bytes
```

## 5. 建议的时间契约

选择**更严格也更简单**的 signal-day seal，而不是多日 window：

```text
signal close
  <= provenance download / decision generation
  < next canonical execution date
```

对这两个 SSE/SZSE ETF 候选，Foundation V1 冻结的候选级操作规则等价于：

```text
signal_close = 15:00 Asia/Shanghai on signal_date
decision_seal_time 必须时区感知
decision_seal_time 的本地日历日 == signal_date
decision_seal_time >= signal_close
decision_seal_time < 下一个 canonical 交易日的起点
provenance download_timestamp <= decision_seal_time
```

下一个开盘日**只**由当时已合法的交易所日历推导。该规则比必要更严格：它让"先看 execution
结果、再重建昨天的 decision"在机制上不可能，同时不引入 scheduler 或 database。
真实 decision cycle 必须随后 commit + push decision evidence 并 STOP，早于任何 execution
evidence goal。

## 6. 该审计的边界

- 本文件**不**声称任何候选已具备前瞻证据，**不**声称 Foundation 已完成。
- 已有 S4C activation 仍是有效的 lifecycle 授权，但它**不**证明 Foundation V1 的正确性。
- 本文件**不**修改任何 candidate identity、observation、canonical 数据或策略语义。
- 后续实现的范围由 [RESEARCH_PRIORITY_DECISION_V3.md](RESEARCH_PRIORITY_DECISION_V3.md) 与
  [Foundation 预注册协议](../batches/prospective_evidence_foundation/PROTOCOL.md) 界定。

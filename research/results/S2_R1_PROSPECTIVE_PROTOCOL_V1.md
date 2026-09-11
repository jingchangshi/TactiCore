# S2 R1 前瞻影子协议报告 V1

## 决策

**ACTIVATE_S2_R1_PROSPECTIVE_SHADOW**。S2 Research Candidate R1 的身份与历史/前瞻边界已在结果可见前冻结，现进入 `PROSPECTIVE_SHADOW_ACTIVE`。这不是 prospective PASS/REJECT，也不是生产批准。

## 冻结记录

- 起始 HEAD：`68c31b88e8432bee8078aa233a2b95ab414afdb6`。
- Candidate ID / protocol：`S2_R1` / `V1`；candidate freeze commit 为 `68c31b88e8432bee8078aa233a2b95ab414afdb6`。
- historical cutoff：2026-08-31；prospective start：2026-09-01。
- manifest：[research/shadow/s2_r1/candidate_manifest.json](../shadow/s2_r1/candidate_manifest.json)，SHA-256 `e280c60b9a0698e6fd19a2f268913dbb7ac42492b2062e5f3268d2a61bc4326f`。
- R1 为逐资产 200 个有效观测、月末收盘信号、下一 canonical 观测日执行、`SIGNAL_CHANGE_ONLY`、现有资产池与防御资产、等额 sleeve、既有成本及 RQAlpha 6.3 原生资金不足部分成交。任何实质修改必须产生 R2 或更高版本，不能修改 R1。

## 冻结输入

| 文件 | SHA-256 |
| --- | --- |
| `config/strategy.toml` | `9935dbdb54f3ea369574f2edfcdba2103c97d539697ff119c7ac9d084931c2ce` |
| `config/universe.csv` | `190aacbca6feadd2ba825b1f284c06f48f30bdc3b5a4618f405711e5aadb8829` |
| `data/canonical/etf_adjusted_close.csv` | `0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93` |
| `data/canonical/trading_calendar.csv` | `ad942a3e1e3e3ae4b7703ea5319ec12793d484b4c49423181682357a1a9d7512` |
| `data/canonical/provenance.json` | `7af2e21890080cec4a4d2ed08a0bd9c6c89fae666fe98d866e33e55837a8d4e3` |
| `tacticore/strategies/multi_asset_trend.py` | `2a11156f2f44f2cda9774b7c035bed9cb9757a83900b17028f6fd8c65eb7d1a6` |
| `tacticore/engines/rqalpha_adapter.py` | `76c551f703b354d033fbb11849170dadee39654d947c1e93e389db5694530477` |

冻结环境为 VectorBT 0.28.5、RQAlpha 6.3.0、Pandas 2.3.3、NumPy 1.26.4、Tushare 1.4.29。

## 数据、决策与记录协议

历史 `data/canonical/` 不再下载覆盖。新数据只能由既有 Tushare downloader 写入 `research/shadow/s2_r1/vintages/YYYY-MM-DD/`；若同历史范围重叠，价格和日历必须逐值一致，否则停止并作为数据事件处理。手工 runner 必须显式提供 `--as-of`，拒绝 cutoff 当日或更早的请求、含有 as-of 后行情的 vintage，及未覆盖完整 signal 月的交易日历；日历仅可用于确认月末，不得进入价格信号。

月末收盘后，runner 只合并冻结历史和该 vintage，生成 target，并在下一 canonical observation 之前向 [observations.csv](../shadow/s2_r1/observations.csv)追加 `decision` 行。执行完成后只能追加新的 `execution` evidence 行；不得修改原 decision，也不得复制 RQAlpha 的会计或撮合。当前记录只有表头。

## 预注册复核与失效条件

- 12 个日历月及真实前瞻决策后才可进行中期完整性/执行/维护负担/定性一致性复核；它不能批准生产。
- 至少 18 个日历月且至少 10 个真实 target-change 执行事件后，才有资格进行 production-candidate review。
- 不预设利润、CAGR、Sharpe 或相对收益阈值；届时综合收益/风险一致性、回撤、signal 行为、执行偏离、换手、维护负担和意外失败。
- 早期 `CANDIDATE_INVALIDATED` 只适用于 manifest/实现完整性失败、canonical 语义变化、资产不可用导致语义失效、RQAlpha 语义不兼容或确认实现 bug。短期亏损、回撤和跑输基准是 `STRATEGY_PERFORMANCE_WEAK` 的潜在证据，不能修改 R1。

## 变更、验证与边界

- 新增 manifest、协议、append-only schema、一个 as-of 手工 runner 和针对候选身份、hash、历史保护、future leakage、空记录与重复写入的测试。
- 永久方法已写入 [研究规则](../../docs/RESEARCH_RULES.md)，冻结结论和活动协议分别追加至 RL-016/RL-017。
- 未修改策略、适配器、`ARCHITECTURE.md`、`AGENTS.md` 或 historical canonical；未重新运行任何 CLOSED 历史调查、参数搜索或 RQAlpha 回放；未新增依赖、平台、scheduler、daemon、候选注册表、治理框架或 S3 实现。
- 已执行 `uv run python research/experiments/run_s2_r1_shadow.py --verify-candidate`；它校验 manifest 与所有冻结输入，且确认当前前瞻记录数为 0。完整仓库测试与静态检查结果见本次提交验证记录。

## 尚未证明与下一方向

**No prospective performance conclusion exists yet.** 当前日期尚未形成合法的前瞻月末 decision；没有伪造数据、收益、成交或 observation。S2 R1 只能等待市场并按协议积累 evidence。下一活动研究方向为 S3 透明基线/假设研究，须在独立 Goal 中进行。

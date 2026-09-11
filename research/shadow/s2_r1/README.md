# S2 R1 前瞻影子协议 V1

## 身份与边界

本目录只服务冻结的 `S2_R1`。候选的机器可验证身份见 [candidate_manifest.json](candidate_manifest.json)：历史基线截止 `2026-08-31`，真正前瞻数据从 `2026-09-01` 开始。任何更改趋势窗口、有效观测定义、信号/执行时点、`SIGNAL_CHANGE_ONLY`、资产池、防御资产、分配规则、缺失值口径、成本或 RQAlpha 原生执行政策的工作，均不得继续称为 S2 R1，必须创建下一顺序候选版本（R2、R3……），并保留 R1 文件不改写。

`data/canonical/` 始终是 R1 的冻结历史证据，不能为后续下载覆盖。每次前瞻拉取都使用现有 downloader 的 `--start-date`、`--end-date`、`--output-dir`，写入 `vintages/YYYY-MM-DD/`；该目录在首次真实拉取时才创建。vintage 应包含 `etf_adjusted_close.csv`、`trading_calendar.csv` 与 `provenance.json`。如果与历史区间重叠，重叠价格和日历必须逐值一致；不一致是数据事件，不能静默覆盖或修订 R1 历史。

## 月度决策时序

```text
月末 canonical 观测日收盘
  → 只用该时点可得的冻结历史 + 单一 prospective vintage
  → 计算 R1 target
  → 立刻追加一条 decision record
  → 下一 canonical 观测日才可观察/回放 RQAlpha 6.3 原生执行
  → 另追加 execution evidence；不得回写 decision record
```

决策必须在其后续执行或组合结果可见前形成。不得回填、重建或改写旧决策，也不得在旧前瞻期间替换数据 vintage。手工运行器要求显式 `--as-of`，拒绝 `<= 2026-08-31` 的时点、含有 `as-of` 后行情的 vintage，以及未覆盖完整 signal 月的交易日历；日历若延至该月自然月末，只用于确认最后一个交易日，绝不参与价格信号，因此不会使用未来市场数据。

示例（仅在月末收盘后、且已有真实 vintage 时）：

```bash
uv run python research/experiments/run_s2_r1_shadow.py \
  --as-of 2026-09-30 \
  --vintage-dir research/shadow/s2_r1/vintages/2026-09-30
```

`observations.csv` 是 append-only 的 Git-friendly 事件表。`decision` 行先写身份、数据 vintage、signal、目标和待执行状态；执行完成后以新的 `execution` 行写框架原生结果引用/压缩字段。不得自行重建 RQAlpha 的会计、撮合或成交数据。当前只有表头，表示尚无真实前瞻月末决策，而非零收益。

## 复核与失效

- 中期完整性复核不得早于 12 个日历月且必须已有真实前瞻决策；只检查完整性、执行、维护负担和定性一致性，不能据此批准生产。
- 只有达到至少 18 个日历月且至少 10 个真实 target-change 执行事件后，才有资格进入 production-candidate review。该 review 不预设 CAGR、Sharpe 或超额收益门槛；应综合收益/风险一致性、回撤、信号行为、执行偏离、换手、维护负担和意外失败。
- 在最短复核期前只能因候选完整性失败而标记 `CANDIDATE_INVALIDATED`：manifest 校验失败、实现不再匹配 manifest、canonical 语义变化、资产不可用而使候选语义失效、RQAlpha 原生语义不兼容，或确认实现 bug 使记录并非 R1。连续亏损、短期回撤或跑输基准只可能是 `STRATEGY_PERFORMANCE_WEAK`，不是修改或提前失效 R1 的理由。

禁止调度器、daemon、通知、券商下单、数据库、候选注册表和 S3 实现。本协议等待未来市场时间；S3 是下一 Goal 可独立启动的研究方向。

# FREE_DATA_CONTRACT_V1 预注册协议

状态：**预注册**。本文件在运行任何等价性比较之前提交。提交后，判据、容差、资产映射、复权口径与裁决规则不得修改；如需修改，只能另建 V2 并说明原因。

授权：所有者 2026-11-25 指令「删除TuShare相关，已经使用包括通达信在内的各种免费数据源，你全面切换，不考虑后向兼容性」。Tushare 已从现行代码中移除（commit `985fb89`）。`S2_R1` / `S4C_R1` 的前瞻 vintage 路径依赖 Tushare，已无法再产生合规前瞻决策，按「数据源退役」处理；R1 身份、manifest、observations 与所有冻结证据保持字节不变。

本协议只回答一个问题：**用免费源重建的历史价格，在完全相同的策略语义下，是否复现 R1 冻结目标日程**。它不改变任何策略参数，不产生任何前瞻 observation，不评价收益。

## 1. External Evidence Gate（8 项）

- **Canonical mapping**：`S2_R1` → time-series trend following（200 日有效观测均线，月度，等额 sleeve + 国债 ETF fallback）；`S4C_R1` → equal risk contribution / risk budgeting（skfolio `RiskBudgeting`，60 条对齐日收益，≥6 合格资产，否则整组合 fallback）。两者的 canonical 证据层级沿用各自冻结时的记录，不在此重评。
- **External tier**：不变。本协议不是新策略提案，只是数据契约替换的等价性检验（`DATA_CONTRACT_SUBSTITUTION`）。
- **External conclusion**：外部文献不回答「两个数据供应商的后复权价格是否给出同一离散决策」；这只能由本地复现裁决。
- **Relevant contradictions**：免费源（通达信）与 Tushare 的原始收盘价都来自交易所行情，但复权因子由各自从分红/扩缩股事件独立推导，因子的小数精度、事件覆盖与缺失观测可能不同；ERC 权重对收益率微小差异连续敏感，而 S2 的离散趋势状态只在价格贴近均线时敏感。
- **Upstream implementation**：目标日程只调用既有冻结实现：S2 `research/experiments/run_s2_rqalpha_validation.py:build_frozen_target_schedule`（内部 `tacticore/strategies/multi_asset_trend.py`）；S4C `research/experiments/run_s4c_rqalpha_execution_review.py:build_frozen_schedule`（内部 skfolio `RiskBudgeting` 与 `freeze_pit_legal_schedule`）。本协议不重写任何策略、求解或 PIT 逻辑。
- **Existing TactiCore evidence**：`research/results/s2_v2_frozen_targets.csv`（103 个执行日）与 `research/results/s4c_pit_corrected_frozen_targets_v1.csv`（161 个执行日）是冻结参照；`research/batches/prospective_evidence_foundation/PORTABLE_REPRODUCTION_CONTRACT_V1.md` 已为 S4C 冻结 `SCHEDULE_WEIGHT_ABS_TOL = 1e-4`。
- **Remaining local gap**：免费源历史价格下，两个冻结日程能否在本协议第 4 节判据内被精确复现。
- **Research action**：`LOCAL_ADJUDICATION`。`EQUIVALENT` 的候选才可建立数据契约后继版本（`S2_R1F` / `S4C_R1F`）；`NOT_EQUIVALENT` 的候选只报告差异来源，不调参、不换源硬凑、不建后继。

## 2. PIT Tradability Gate（6 要素）

1. **Date-aware universe**：沿用 `config/universe.csv`（hash `190aacbc…8829`）的 12 只 ETF 与各自上市日期；不增删资产。
2. **Asset lifetime metadata**：`AssetLifetime` 由同一 universe 的 `start_date` 生成（`tacticore/data/tradability.py`，不修改）；上市日前的任何免费源价格丢弃为缺失。
3. **Fallback 上市前处理**：沿用冻结语义——S2 只对已有 200 个有效观测且信号日有价的风险资产分 sleeve；S4C 少于 6 个合格资产时整组合持有 `511010.SS`。`511010.SS` 上市（2013-03-25）前的行为由冻结 `freeze_pit_legal_schedule` 的 inception 裁剪决定，不另写规则。
4. **Execution price 缺失处理**：无成交日不产生行；缺失保持缺失，不前向填充、插值、置零或猜测。S4C 正目标仍须通过 `validate_execution_targets`。
5. **Strategy inception**：与冻结参照一致——S2 首执行日 `2013-04-01`；S4C 首执行日 `2013-04-01`、末执行日 `2026-08-03`。比较只使用 `<= 2026-08-31`（R1 `historical_cutoff`）的价格行。
6. **每个正目标可执行**：S4C 由 `freeze_pit_legal_schedule` → `validate_execution_targets` 零容忍校验；S2 冻结参照不含 PIT 修正层，本协议照原样复现其生成函数，不添加新检查。

## 3. 免费数据契约

- **来源**：通达信（TDX）公开行情主站 TCP 协议，日线 K 线（category 9）原始 OHLC 与除权除息事件（xdxr）。FinanceMCP 现有 research-export 快照（`v3_snapshot_20261113`）只覆盖 `2026-01-05` 起，不足以重建 2012 年起的历史，因此按架构师裁决写一个最小直连研究脚本（仅标准库 socket/zlib，不新增依赖），协议格式对齐 FinanceMCP `src/ashare/providers/tdxClient.ts`。
- **资产映射**：`xxxxxx.SS` → TDX market 1（上交所），`xxxxxx.SZ` → TDX market 0（深交所），代码取前 6 位；不做任何替代资产。
- **复权口径**：后复权。逐资产以首个有效交易日因子 1.0 起算；在 xdxr category 1（除权除息）的除权日 `t`，因子乘以 `prev_close / ref`，其中 `ref = (prev_close × 10 − fenhong + peigu × peigujia) / (10 + songzhuangu + peigu)`，`prev_close` 为前一有成交日原始收盘价（与 FinanceMCP `xdxrReferencePreClose` 同式，不做四舍五入）。后复权收盘价 = 原始收盘价 × 累计因子。category 11/12（扩缩股）若落在上市日后则**拒绝产出**（fail closed），不按猜测公式建因子；上市日前的事件忽略。两个策略对逐资产正常数缩放不变（S2 比较同一序列与其均线；S4C 使用 `pct_change`），因此锚点选择不影响决策。
- **可得时间语义**：`trade_date` 收盘价只在该日 15:00（Asia/Shanghai）收盘后可用；xdxr 事件按除权日生效。免费源历史为 2026-11-25 检索的**当前视图**，供应商修订历史未知；后复权从起点累计，因而 cutoff 之后的分红事件不改变 cutoff 之前的价格。
- **manifest**：快照目录写 `manifest.json`，记录来源、主站、请求参数、下载时间、逐资产行数/首末日/xdxr 事件、复权公式、可得时间语义与每个文件的 SHA-256。

## 4. 等价性判据（预先写死）

对照（control，必须先通过）：同一比较代码用 `data/canonical/etf_adjusted_close.csv` 重推两个日程，必须满足下述判据；若对照不通过，裁决为 `BLOCKED_CONTROL`，不对免费源下任何结论。

`S2_R1`：
- 执行日集合与顺序与 `s2_v2_frozen_targets.csv` **精确一致**；
- 资产列集合与顺序精确一致；
- 逐元素 `|Δw| <= S2_WEIGHT_ABS_TOL = 1e-8`（冻结文件以 8 位小数存储；sleeve 为 1/n 有理数）。

`S4C_R1`：
- 执行日集合与顺序与 `s4c_pit_corrected_frozen_targets_v1.csv` **精确一致**（161 行，2013-04-01 .. 2026-08-03）；
- 资产列集合与顺序精确一致；逐行 support 集合精确一致；逐行最大权重资产身份精确一致；逐行和 round(12) == 1；
- 逐元素 `|Δw| <= S4C_WEIGHT_ABS_TOL = 1e-4`，`REL_TOL = 0`（与 `PORTABLE_REPRODUCTION_CONTRACT_V1` 相同，不放宽）。

裁决：一个候选全部条件满足 → `EQUIVALENT`；任一不满足 → `NOT_EQUIVALENT`，并报告首个/最大差异的日期、资产与价格层诊断（逐资产日收益差、缺失观测差异、因子事件差异）。不允许以更换主站、调整容差、剔除日期或修改策略参数的方式重试；仅当下载本身失败（网络/协议错误，未产出快照）时允许重跑下载。

## 5. 产物

```text
research/batches/free_data_contract_v1/PROTOCOL_V1.md           本协议（先提交）
research/batches/free_data_contract_v1/fetch_tdx_history.py     最小 TDX 直连下载脚本
research/batches/free_data_contract_v1/run_equivalence.py       等价性比较
data/free_v1/tdx_<UTC 时间戳>/                                  价格快照 + manifest.json
research/batches/free_data_contract_v1/EQUIVALENCE_RESULT_V1.json 裁决结果
```

不新建调度；不修改 `research/shadow/s2_r1`、`research/shadow/s4c_r1`、`data/canonical`、`research/batches/transfer_v1`、`tacticore/engines`、`tacticore/data/tradability.py`、`research/ashare/v3_data.py`、已签 release 与既有 `research/results` 产物。

# Batch 03 冻结协议：已获阶段推进

状态：**待 Commit A 冻结**。本文件不含任何 Batch 03 真实绩效或 RQAlpha 结果。起始提交为 `cb4d05d52658489de13d6c2e5df6c1c8ec6b9c50`。

## 共同边界

- canonical 价格 SHA-256：`0ab40b9cf12cb900fa1c3ff53afc35f9963e44e10f67157a007f3fd7e15d8e93`；S2 R1 manifest：`e280c60b9a0698e6fd19a2f268913dbb7ac42492b2062e5f3268d2a61bc4326f`。
- RQAlpha 固定为项目的 `>=6.3,<6.4` 路径，使用原生 `order_target_portfolio`、`partial_fill_on_insufficient_cash=true`、撮合、成本、滑点和账户；不重算任一策略信号。
- skfolio 研究 extra 解析为 1.0.6；以本项目依赖集隔离 dry-run 验证 Python 3.10/3.11/3.12 均可解析。它仅计算 ERC 目标权重，VectorBT 始终负责模拟。
- 结果后不得改变参数、时点、比较器或门槛；明确 correctness defect 才能按 INVALID_RUN → Protocol V2 → 新冻结 → 重跑受影响 track 的顺序处理。

## Track A：S27A authoritative execution review

冻结配置 SHA-256：`config/s27_trend_inverse_vol.toml` `4d5f96a7d1e1c7b38df18d53157601fc6055b18091cab1702f74b129e63e517c`；策略源 SHA-256：`trend_inverse_vol.py` `83f52203617af70284db3e0b9df0bf6d4d1702a914344c107528508dc2d3d203`。

使用现有 canonical 数据、冻结 200 trend / 60 vol、S2 risk universe、511010 fallback、10/5 bps、月末信号与下一观测日执行。先以 frozen strategy 的 `build_month_end_targets` 和 `build_execution_weights` 产生 `s27a_v1_frozen_targets.csv`；它保留每月 target 提交，而非 S2 的 `SIGNAL_CHANGE_ONLY`。目标必须非负、和为一、日期唯一递增。将同一表交回 VectorBT，须在 `1e-12` 内重现 Batch 02 的 CAGR 7.7866589700%、MaxDD -12.5033896200%、Sharpe 1.0150327702；否则为 `BLOCK_S27A_EXECUTION_REPRODUCTION`，不得运行 RQAlpha。

RQAlpha 回调只查 execution date 的冻结行，不计算趋势、波动、风险预算或 inverse-vol。记录原生指标、订单/失败/现金/成交量事件、现金路径、每个 execution date 与月度 review 的目标跟踪、所有 material difference 原生证据。material threshold 是 5pp，不得有 `UNEXPLAINED_EXECUTION_DIFFERENCE`。

唯一决策为 `ADVANCE_S27A_TO_CANDIDATE_FREEZE_REVIEW`、`DO_NOT_ADVANCE_S27A_EXECUTION`、`BLOCK_S27A_EXECUTION_REPRODUCTION` 或 `BLOCK_S27A_EXECUTION_ENVIRONMENT`。advance 要求：所有 schedule dates 回放且无额外信号；cash rejection 为零；平均 execution-date total-absolute deviation <=3%，materially off-target dates <=10%；平均现金 <=2%；RQAlpha CAGR >0 且不低于 VectorBT 2pp，MaxDD 不比 VectorBT 差超过 5pp。

## Track B：S10A robustness

冻结配置 SHA-256：`config/s10a_vol_targeting.toml` `4ef87e42e130b14b8174f391a412969f5543af37c807d3e2930c8c89015d5f0f`；策略 SHA-256：`volatility_targeting.py` `cac1639220e610f50d8b00a29e2d100de44fedf357c1a6d5987db0770730cfbd`。冻结中心为 20 个 valid aligned returns、10% target、[0,1] scale、无杠杆，并且始终使用 `pct_change(fill_method=None)`。

实验层只运行：window `(10,10%)`、`(20,10%)`、`(40,10%)`；target `(20,8%)`、`(20,10%)`、`(20,12%)`。中心 20/10 不会因结果改选；无 Cartesian grid。每例的 primary comparator 是相同 signal/execution dates、成本、资金和 canonical 数据的 `MONTHLY_STATIC_25_25_25_25`，S30 只作 context。固定分期为 2013-03-29–2016-12-31、2017–2019、2020–2022、2023–2026-08-31；rolling 沿用既有月末 3Y/5Y；中心成本仅 15/30/50 bps fee-only、slippage=0。

中心 experiment targets 与合法 V2 基线的 CAGR、MaxDD、Sharpe、Calmar、turnover 必须以 `1e-12` 重现，否则 `BLOCK_S10A_ROBUSTNESS_REPRODUCTION`。advance 要求：全部五例 CAGR>0、Sharpe>0、MaxDD>-20%；window 与 target 两个维度各至少 2/3 相对月频静态满足 CAGR 不差超过1.5pp、MaxDD 严格更好、Sharpe 或 Calmar 更好；中心 `0.40 < average scale < 0.95`，target 维至少 2/3 不退化；中心四分期 CAGR 均正且至少 3/4 MaxDD 不差、至少 3/4 Sharpe 或 Calmar 更好；3Y/5Y 正 CAGR share 分别 >=90%/>=95%，3Y 至少60%窗口 Sharpe 或 MaxDD 改善；50bps CAGR>0 且 Sharpe>=0.70。决策仅 `ADVANCE_S10A_TO_EXECUTION_REVIEW`、`REJECT_S10A_ROBUSTNESS`、`BLOCK_S10A_ROBUSTNESS_REPRODUCTION`；不运行 S10 RQAlpha。

## Track C：S4C canonical ERC via skfolio

S4B 的 Riskfolio 阻塞历史保持不变。S4C 是新的 upstream route，不是新金融策略：E2 `ERC_RISK_PARITY`、`UPSTREAM_COMPARE`。每个 month-end 先筛选当前有价且已有至少 61 个有效价格的风险资产；只在该 eligible set 的共同非缺失价格行取最后 61 个价格，再以 `pct_change(fill_method=None)` 得到恰好 60 个 aligned returns。至少六个资产，否则 100% fallback。禁止填充、pairwise covariance、杠杆、期望收益目标、custom budget 或其它 risk measure。

唯一优化调用为 `skfolio.optimization.RiskBudgeting(risk_measure=RiskMeasure.VARIANCE, min_weights=0, max_weights=1)`，默认等风险预算；无有限、非负、和为一的解即 `BLOCK_S4C_UPSTREAM_EXECUTION`，不得伪装成 fallback。primary controls 使用同一 aligned window/eligible set/signal/execution/cost：`SAME_ELIGIBLE_EQUAL_WEIGHT` 与 `SAME_ELIGIBLE_INVERSE_VOL`。月末估计、下一 canonical 日执行；10/5 bps、初始资金 1,000,000。

coverage 要求 >=6 eligible 的 evaluated month ends >=80%，否则 `BLOCK_S4C_DATA_COVERAGE`。否则 absolute：CAGR>0、Sharpe>=.50、MaxDD>-35%；relative inverse-vol：CAGR 不差超过1.5pp、MaxDD 不差超过2pp、Sharpe 高至少.03 或 Calmar 高至少.05、turnover <=1.5×。记录最大权重的 median/P95、effective number 和任一资产>50%的月份。决策仅 `ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS`、`DO_NOT_ADVANCE_S4C_ERC_TRANSFER`、`BLOCK_S4C_SKFOLIO_DEPENDENCY`、`BLOCK_S4C_DATA_COVERAGE`、`BLOCK_S4C_UPSTREAM_EXECUTION`。

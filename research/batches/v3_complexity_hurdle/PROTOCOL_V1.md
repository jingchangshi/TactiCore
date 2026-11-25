# V3_COMPLEXITY_HURDLE_V1 预注册协议

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-25。本文件在任何本研究结果产生或被查看之前提交；runner 与测试在本文件之后、唯一一次授权运行之前单独提交。本研究是**只读历史诊断**：不创建候选、不签发或修改任何 release、不改 EXP-V3-0x 脚本或既有 `research/results` 产物、不写 FinanceMCP 生产目录、不使用 Tushare（只读已存在的 `v3_snapshot_20261113` 快照与本地 RQAlpha bundle，不新增任何 Tushare import，不重新下载数据）。

## 0. 问题

`docs/PORTFOLIO_OBJECTIVE.md` 把"简单 beta / 静态分散已接近目标量级"作为复杂度门槛。`EXP-V3-01`（双锚三档 85/60/15 + 超级 ETF 风格轮动 + 511010 蓄水池）只对比了沪深300死拿与 60/40，且 511010 按超级 ETF 费率（万0.5 免五）计费，但 511010 不在已核验超级 ETF 白名单内。S30（9.92%）与 S4C（11.6%）来自不同窗口与资产池，不可直接比较。本研究在**同一窗口、同一账户规模、同一真实分层费率、同一原生执行引擎**下回答：V3 ETF 底盘的复杂择时是否挣过静态分散（S30 式）与 ERC（S4C 式）门槛。

## 1. External Evidence Gate

| 字段 | 预登记 |
|---|---|
| Canonical mapping | A → `V3_DUAL_ANCHOR_SUPER_ETF`；B → `STATIC_DIVERSIFICATION`（S30 结构）；C → `ERC_RISK_PARITY`（S4C 构造，skfolio `RiskBudgeting`）；D → 静态股债 60/40 参照（`EXP-V3-01` 原基准）。 |
| External tier | A：`E3_MIXED_CONDITIONAL`；B：`E1_MATURE`（复杂度基准，非 alpha 主张）；C：`E2_ESTABLISHED_METHOD`（构造方法，非收益异常）。 |
| External conclusion | 1/N 与静态分散是估计误差下的强基准（DeMiguel/Garlappi/Uppal 2009）；ERC 是成熟构造（Maillard/Roncalli/Teiletche 2010）而非 alpha；GTAA/趋势择时需与简单静态比较（registry `GTAA_MA`："需要简单静态比较"）。 |
| Relevant contradictions | Kim/Tse/Wald (2016)、Cederburg 等 (2020)：择时/波动管理样本外折损、换手吞噬；`RL-053` 否证了本账户 ±10% 趋势倾斜对静态基座的增益；`RL-043` 给出静态/beta 已接近 10% 量级的历史诊断。 |
| Upstream implementation | 目标权重：A/D 直接 import `EXP-V3-01` 的 `build_v3_execution_weights` / `build_benchmark_weights`（不修改原脚本）；C 直接 import `run_s4c_erc_skfolio_transfer.erc_weights`（skfolio 1.0.6）。粗算 `tacticore/engines/vectorbt_adapter.py:run_target_weights`；权威结果原生 RQAlpha 6.3.0 `run_func` + `order_target_percent`。分层费率经 RQAlpha 官方扩展点 `Environment.set_transaction_cost_decider` 注入，内部复用原生 `StockTransactionCostDecider`（只按代码分派费率档，不自写会计/撮合）。 |
| Existing TactiCore evidence | `EXP_V3_01_REGIME_SUPER_ETF.json`（A 的冻结 VBT 与 RQAlpha 结果，作复现锚）；`S30_STATIC_STRATEGIC_ALLOCATION_V1.md`；`S4C_ERC_SKFOLIO_TRANSFER_V1.md`；`RL-043`、`RL-053`、`RL-054`。 |
| Remaining local gap | 同窗口 2018-01-02..2026-08-31、¥69,000 / ¥100,000、真实分层费率下，A 相对 B、C 的风险调整后表现。 |
| Research action | `LOCAL_ADJUDICATION`（只读诊断；裁决只影响 V3 目标定位的表述，不触发任何参数修改、候选或 release）。外部文献已回答静态分散/ERC 的存在性，本地账本未回答 V3 底盘对二者的同窗 transfer，故不是 `DO_NOT_PURSUE`。 |

## 2. PIT Tradability Gate

1. **Date-aware universe**：A 使用 `EXP-V3-01` 的 33 只白名单 + 替补 ETF 面板与 `_available_bucket` 规则；B/C 使用第 4 节固定的四个袖子，每个袖子在每个调仓执行日按"超级 ETF 已上市且有效价 ≥ 20 根，否则替补"决定执行代码。
2. **Asset lifetime metadata**：全部来自 `load_stitched_panels` 的 `AssetLifetime`（RQAlpha `instruments.pk` / 快照 `fund_basic`）；518880.SH 用同一 bundle 读取函数补入并绑定 `AssetLifetime`（bundle 上市 2013-07-29）。上市前、退市后价格为 `NaN`。
3. **Pre-listing fallback**：EQ_VALUE 袖子 159330.SZ（2024-08-19 上市）前用 510300.SH；EQ_GROWTH 袖子 159337.SZ（2024-09-20 上市）前用 510500.SH；只在调仓执行日迁移（B 年度、C 月度），不倒灌未来。GOLD/BOND 袖子全窗单一代码（2013 年上市）。
4. **Missing execution price / suspension**：`NaN` 不转 0；`tradability_mask = lifetime ∧ price_available`；任一正目标在执行日不可交易即 `UntradableTargetError`，本次运行 `INVALID_RUN`。
5. **Strategy inception**：所有臂 2018-01-02 以现金起步；首个信号日 2018-01-02 收盘，首个执行日 2018-01-03（与 `EXP-V3-01` 一致）；指标起点 2018-01-02。窗口终点 2026-08-31（RQAlpha bundle 截止）；2026-09-01 以后的快照拼接数据不进入任何指标。
6. **Executability of every positive target**：每个 VectorBT 运行前 `validate_execution_targets` 零容忍；每个 RQAlpha 运行核对实际下单日 = 计划日、`ORDER_CREATION_REJECT` 计数、整手（100 份）与分层佣金审计（第 6 节）。

## 3. 固定窗口与本金

- 窗口：`2018-01-02..2026-08-31`；IS `2018-01-02..2023-12-29`，OOS `2024-01-02..2026-08-31`（同 `EXP-V3-01` 的 IS/OOS 划分，OOS 终点受 bundle 截止限制）。OOS 指标以 2023-12-29 收盘净值为基。
- 本金：¥69,000 与 ¥100,000 两档，全部臂相同。现金收益按 0 建模（RQAlpha 原生），不建模逆回购/货基收益，此偏差对持有更多现金的臂不利，结果中披露。

## 4. 对照臂（运行前写死）

| 臂 | 目标生成 | 调仓 |
|---|---|---|
| A `V3_ETF_CHASSIS` | `build_v3_execution_weights(panels, regime_df, include_bond_reserve=True)`，全部默认参数（即 `EXP-V3-01` 主变体 `V3_SUPER_ETF_BOND_RESERVE`）；无 L2 熔断、无个股卫星 | 原规则（体制切换 / ≥10 日且 L1≥0.08） |
| B `STATIC_S30_STYLE` | 四袖子各 25% | 年度：首日 + 每年最后交易日收盘信号，次日执行 |
| C `ERC_S4C_STYLE` | 同四袖子，skfolio `RiskBudgeting(VARIANCE, min 0, max 1)` 无杠杆，61 个对齐价格（60 个收益） | 月度：首日 + 每月最后交易日收盘信号，次日执行 |
| D `STATIC_60_40` | `build_benchmark_weights(panels, "STATIC_60_40")`：510300 60% / 511010 40% | 季度（原函数） |

B/C 的四袖子：

| 袖子 | 执行代码（PIT 替补链） | C 的风险估计序列 |
|---|---|---|
| EQ_VALUE（沪深300） | 159330.SZ（超级 ETF）若可交易且有效价 ≥ 20 根，否则 510300.SH | 510300.SH |
| EQ_GROWTH（中证500） | 159337.SZ（超级 ETF）若可交易且有效价 ≥ 20 根，否则 510500.SH | 510500.SH |
| GOLD | 518880.SH | 518880.SH |
| BOND | 511010.SH | 511010.SH |

**选取理由（不使用任何收益数据）**：S30 结构为"两类权益 + 黄金 + 国债"各 25%。S30 的海外权益袖子 513500 为 QDII，按 `RL-052/RL-053` 资产池契约不可执行；以 V3 自身的第二锚（成长锚 `000905` 中证500）替代，使 B/C 恰好持有 A 所择时的两个锚指数，比较只剩"择时 + 风格轮动"这一差异。黄金与国债沿用 S30 原代码 518880 / 511010（511010 同时是 A 的蓄水池代码）。超级 ETF 替补顺序取 `EXP-V3-01` 的 VALUE/GROWTH 列表中跟踪同一指数的成员（159330 跟踪沪深300、159337 跟踪中证500），替补取其列表中跟踪同一指数的第一个替补。白名单无实物黄金 ETF（159321.SZ 为黄金产业股票），故黄金不替换。不评估任何备选映射、权重、窗口或资产。

C 的协方差用全窗可得的替补代码收益估计（同指数 ETF 风险近似相同，且 2013 年起全部可得，避免新上市 ETF 短历史）；执行用 PIT 映射代码。skfolio 任一月求解失败即 `INVALID_RUN`，不回退。

## 5. 费率与执行

- 白名单：`super_etf_whitelist_20261115.json`，SHA-256 `d0c30ecc2c4f18de21827b02bff1db78cc29b853fe40481a17ad8d9facbb07c0`。
- `SUPER_ETF`（白名单内）：佣金万0.5，最低 0 元。`NORMAL_ETF`（其他全部，含 510300、510500、518880、511010、512890、159915）：佣金万2.5，单笔订单最低 ¥5（`normal_etf_20261111.json`）。ETF 无印花税、无过户费。
- 滑点：全部臂单边 `0.0002`（PriceRatioSlippage），与 `EXP-V3-01` 主变体及其基准一致。
- RQAlpha：`build_rqalpha_config`（未修改）+ `partial_fill_on_insufficient_cash=True`；每个执行日按"目标 − 当前权重"升序先卖后买，逐证券 `order_target_percent`（同 `EXP-V3-01` 回放）；ETF 交易成本 decider 换成按代码分派到两个原生 `StockTransactionCostDecider`（万0.5/0 元、万2.5/5 元）的分派器。
- VectorBT 粗算：逐列比例佣金（0.00005 / 0.00025），**不含 ¥5 最低佣金、允许碎股**，因此与本金无关，只跑一次；仅作粗算参照，不参与裁决。

## 6. 运行完整性门槛（任一不满足 → `INVALID_RUN`，不得改协议重跑挽救）

1. `verify_v3_provenance(verify_content=True)` 通过；体制缓存 `v3_regime_daily.csv` 的 SHA-256 在运行前后均为 `e3127d6bd13517b6762386f5886e161548e8489de781875223cedd82ea48bbfa`（运行不得写入生产目录）。`compute_v3_market_regime_series` 在缓存未命中时会重算并**写回**缓存，因此 runner 在调用前先独立核对缓存的 `snapshot_id`、`cache_version` 与日历覆盖；不命中即中止，不允许触发写回。
2. A 的 VBT 复现：用 `EXP-V3-01` 原成本（0.00005 / 0.0002、¥100,000、全窗 `2018-01-02..2026-11-13`）重算，`full.cagr = 0.047949955359549046`、`full.max_drawdown = -0.1379056110690038`（绝对误差 ≤ 1e-9），调仓事件数 199。
3. A 的原生复现：RQAlpha、统一万0.5/0 元、¥100,000，`cagr = 0.04306911643401823`（绝对误差 ≤ 1e-6）。
4. 所有 VBT 运行通过 `validate_execution_targets`。
5. 每个 RQAlpha 运行：实际下单日集合 = 计划执行日集合。
6. 分层佣金审计：每个普通 ETF 订单的佣金合计 ≥ ¥5 − 1e-6；每笔超级 ETF 成交佣金 = 成交额 × 0.00005（相对误差 ≤ 1e-6）。

拒单（`ORDER_CREATION_REJECT`）与因整手取整为 0 的目标是真实执行结果，如实计数报告，不构成 `INVALID_RUN`。

## 7. 指标（权威：RQAlpha 日终总资产；全部基于 2018-01-02 起的同一曲线切片）

CAGR（365.25 日年化）；signed MaxDD；Sharpe（日收益、rf=0、√252）；Calmar = CAGR/|MaxDD|；CVaR5（最差 5% 日收益均值，负数）；worst year（2018–2025 完整自然年最差收益；2026-01..08 单独列示）；年化单边换手 = Σ|成交额| / 2 / 平均总资产 / 年数（初始建仓计 0.5）；成交笔数；`ORDER_CREATION_REJECT` 数；佣金合计（¥ 与占初始本金比例）；IS/OOS 分段 CAGR/MaxDD/Sharpe/Calmar；3Y 滚动（756 交易日窗口逐日滑动）：各臂 3Y CAGR 最小/中位、最差 3Y 窗口 MaxDD，A 相对 B 的 3Y CAGR 胜率与 3Y Calmar 胜率。另报告 RQAlpha 原生 `summary.sharpe` 供对照。

## 8. 预注册裁决（只用全窗 RQAlpha 指标；两档本金同时判断）

定义 A 在指标 m 上"优于" X：Sharpe_A ≥ Sharpe_X + 0.10；Calmar_A ≥ Calmar_X + 0.10。"MaxDD 显著更好"：MaxDD_A ≥ MaxDD_B + 0.05（回撤浅 5 个百分点以上）。阈值是重要性门槛，不是统计显著性声明。

1. `V3_REGIME_CLEARS_HURDLE`：两档本金下，A 的 Sharpe 与 Calmar 均优于 B，且均优于 C。
2. `V3_REGIME_IS_RISK_OVERLAY_NOT_RETURN_SOURCE`：两档本金下，A 的 Sharpe 与 Calmar 均不优于 B，且 A 的 MaxDD 不显著好于 B。
3. 其他 → `MIXED`。

第 6 节任一失败时裁决为 `INVALID_RUN`，以上规则不适用。IS/OOS、3Y 滚动、VBT、D 与统一万0.5 诊断（即第 6 节第 3 条的 A 原生复现运行：511010 也按万0.5/0 元计费，对应 `EXP-V3-01` 原口径）只作解释，不改变裁决。

RQAlpha 运行清单（共 9 次）：A 原生复现 1 次（¥100,000、统一万0.5）+ {A, B, C, D} × {¥69,000, ¥100,000} 分层费率 8 次。

## 9. 唯一一次授权运行

- 命令（worktree 根）：`nice -n 10 /home/jcshi/workspace/TactiCore/.venv/bin/python -m research.batches.v3_complexity_hurdle.run_v3_complexity_hurdle`
- 产物：`research/results/V3_COMPLEXITY_HURDLE_V1.md` 与 `.json`。runner 若发现任一产物已存在即拒绝运行（单次运行护栏）。
- runner 与测试在本协议之后、运行之前单独提交；运行记录 runner commit、退出码与输入哈希。运行失败（异常退出）若发生在任何指标计算之前，可修复实现缺陷后重跑并在报告中披露；一旦任何指标已产生，不得重跑。

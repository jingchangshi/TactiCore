# EXP-V3-10：进攻先导替代探索——23 只超级行业 ETF 动量先导与短窗高股息 QualityCore 主板研究（预注册协议）

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-26。严格区分两条先导研究线的样本长度与推广门槛：**Line 10A（23 只超级行业 ETF 趋势轮动先导）**覆盖完整 8.9 年历史（`2018-01-02..2026-11-26`），而 **Line 10B（高股息低波 QualityCore 主板股波段）**受 `daily_basic.dv_ttm`（`2024-01-02..2026-11-17`）与当次财务公告快照限制，预注册为 **`BOUNDED_SHORT_WINDOW_PRE_STUDY`（`2024-02-01..2026-10-30`）**，严禁跨周期直接推广。

## 1. External Evidence Gate

- **Canonical mapping**:
  - `10A` → `CHINA_INDUSTRY_ETF` / `CHINA_THEME_ETF`（`E4_OPEN_LOCAL`，超级 ETF 免 5 元低摩擦新物理条件下重测行业轮动）。
  - `10B` → `LOW_VOL` + `VALUE` + `V3_MAINBOARD_SWING_BREAKOUT_PULLBACK`（高股息质量因子叠加回踩买点）。
- **External tier**: `10A = E4_OPEN_LOCAL`；`10B = E3_MIXED_CONDITIONAL`。
- **External conclusion**: 行业动量（Moskowitz & Grinblatt 1999; Boubaker/Du/Liu 2022）在 A 股长期存在，但此前 `S3A`（等权固定 11 行业无超级免 5）未过成本与静默基准门槛；高股息低波在中国熊市防御段具结构性优势，但短窗统计自由度有限。
- **Relevant contradictions**: 坚决区隔于已拒 `S3A/S3B/S3C`（固定 11 只普通行业 ETF 万 2.5 最低 5 元）；`10A` 使用东财 23 只超级行业/主题 ETF（万 0.5 免 5、无印花税）在 `OFFENSIVE/STRUCTURAL` 20% 机动先导槽位内轮动，并与 `EXP-V3-02` `BP1_PULLBACK` 同窗对比。
- **Upstream implementation**: `VectorBT`（`10A` `2018-01-02..2026-11-26`）+ 原生 `RQAlpha 6.3.0`（`10A` `2018-01-02..2026-10-30`，`10B` `2024-02-01..2026-10-30`，真实分层费率与印花税）。
- **Existing TactiCore evidence**: `S3_SECTOR_BASELINE_V1`、`EXP_V3_02_MAINBOARD_STOCK_SWING`、`EXP_V3_05B`。
- **Remaining local gap**: (1) 23 只超级行业 ETF + PIT 上市前老牌行业替补在 `MA60` 趋势过滤与 Top-1/Top-2 轮动下的真实分层费率收益；(2) OOS 高股息（`dv_ttm >= 3.5%`）+ 低波回踩 `MA20` vs `BP1_PULLBACK` 在 6.9 万/10 万账户下的交易频率、5 元佣金占比与净数学期望。
- **Research action**: `NEW_HYPOTHESIS`（10A）；`BOUNDED_SHORT_WINDOW_PRE_STUDY`（10B）。

## 2. PIT Tradability Gate

1. **Date-aware universe**:
   - `10A`：白名单 23 只 `SECTOR` 超级 ETF，在各只超级 ETF 2023–2026 上市满 20 交易日前，严格按同赛道老牌高流动性行业 ETF（`512480/515790/512170/512880/515030/512660/512400/512800/159928/512690`）PIT 替补，绝不回填未上市品种；仅在 `Close > MA60` 且宏观非 `DEFENSIVE` 时允许进入 Top-1 / Top-2。
   - `10B`：沪深主板非 ST、上市 `>= 250` 日、20 日均额 `>= 1.5 亿`、PIT `circ_mv >= 500,000` 万元（50 亿元）、PIT `QualityCore`（`ann_date <= T`）、精确当日 PIT `dv_ttm >= 3.5%`（严禁前向填充，覆盖审计至 `2026-11-17`）、60 日波动率不高于横截面中位数。
2. **Asset lifetime metadata**: `bundle_202611` + `v3_snapshot_20261126`。
3. **Pre-listing fallback**: 明示于每条行业映射表。
4. **Missing execution price / suspension**: 股票高开 `>+2%`、涨停/跌停或停牌跳过或顺延。
5. **Strategy inception**: `10A` 为 `2018-01-02..2026-11-26`（RQAlpha `..2026-10-30`）；`10B` 为 `2024-02-01..2026-10-30`（附至 `2026-11-17` `dv_ttm` 覆盖统计）。
6. **Executability of every positive target**: 10A 在 20% 机动先导仓（与 40% 底盘合并净值）下跑完整 RQAlpha 6.3.0；10B 在 ¥69k/¥100k 下跑原生 `open_auction` 撮合与完整费用审计。

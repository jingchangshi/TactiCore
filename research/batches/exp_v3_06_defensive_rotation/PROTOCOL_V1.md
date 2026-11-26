# EXP-V3-06：防御蓄水池降摩擦与趋势过滤防御资产轮动（预注册协议）

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-26。针对当前 A 股空头防守档（85% 防御仓位）暴露的三大实盘痛点——① `511010.SH` 非免五且单手约 ¥14,138 推高小账户佣金损耗（占 6.9 万本金 4.52%）；② 黄金 ETF（`518880.SH`）在 `2026-09~11` 同步暴跌 `-38.9%`；③ 现行回测现金收益按 0% 计算——检验低门槛债券蓄水池与趋势过滤防御轮动的净改进效果。

## 1. External Evidence Gate

- **Canonical mapping**: `CHINA_DEFENSIVE_ETF` & `DEFENSIVE_MOM`（`STRATEGY_EVIDENCE_REGISTRY.yaml` 既有 `NOT_STARTED` / `E4_OPEN_LOCAL` 本地缺口）。
- **External tier**: `E4_OPEN_LOCAL`（中国场内债券/货基/黄金/红利 ETF 的单手金额、免五差异与流动性均属高度本地化约束）。
- **External conclusion**: Faber (2007) GTAA 与一般趋势文献仅给出绝对趋势过滤原则，未回答中国 7–10 万账户在 `511010` 高单手门槛、货币 ETF `511880` 收益及黄金急跌期间的具体工具选择。
- **Relevant contradictions**: 过短趋势窗口会放大债券/黄金震荡磨损；与已关闭 `RL-053`（静态 50% 现金 + 15% 511360 ±10% 倾斜）及 `S8A`（单一 510300/511010 200 日择时）在防御桶资产池与 V3 双锚框架上完全正交。
- **Upstream implementation**: `VectorBT` 全窗粗筛与参数高原（`2018-01-02..2026-11-26`）+ 原生 `RQAlpha 6.3.0`（`2018-01-02..2026-10-30`，¥69,000 & ¥100,000，真实分层费率与 100 份整手）。
- **Existing TactiCore evidence**: `EXP_V3_01_REGIME_SUPER_ETF.*`（证实 `511010` 优于 0% 现金）、`V3_COMPLEXITY_HURDLE_V1.*`（揭示 `511010` 高手续费摩擦）。
- **Remaining local gap**: 低单手国债/政金债 ETF（`159649.SZ` / `511260.SH`）与银华日利货币底座（`511880.SH`）对佣金损耗的削减幅度，以及防御档内【红利低波 + 黄金 + 利率债】引入单资产趋势过滤（`MA60`）能否在 2026 H2 躲避黄金暴跌并提升全期卡玛比率。
- **Research action**: `NEW_HYPOTHESIS`。

## 2. PIT Tradability Gate

1. **Date-aware universe**: 仅使用目标执行日已上市满 20 交易日的 ETF：`511010.SH`（2013-03-25）、`511260.SH`（2017-08-24）、`159649.SZ`（2022-10-24）、`511880.SH`（2013-04-18）、`518880.SH`（2013-07-29）、`159549.SZ`/`159207.SZ`（PIT 替补 `512890.SH`/`510880.SH`）及 V3 宽基超级 ETF 桶。
2. **Asset lifetime metadata**: 来自 `bundle_202611` 与 `v3_snapshot_20261126/fund_basic.csv`。
3. **Pre-listing fallback**: `159649.SZ`（2022-10-24 上市）前使用 `511260.SH`（2017-08-24 上市），此前使用 `511010.SH`；红利超级 ETF 上市前使用 `512890.SH`（2019-01-18 上市）或 `510880.SH`。
4. **Missing execution price / suspension**: `NaN != 0`，严格经 `validate_execution_targets` 校验。
5. **Strategy inception**: `2018-01-02..2026-11-26`（IS `..2023-12-29`、OOS `2024-01-02..2026-11-26`、极端切片 `2026-07-01..2026-11-26`）；RQAlpha 原生窗至 `2026-10-30`。
6. **Executability of every positive target**: 非免五债券 ETF 严格执行 5 元最低佣金与 ≥¥5,000 单笔主动买入门槛（避免小额频繁倒腾交 10 元往返佣金）。

## 3. 对照臂与参数高原

- `D0_BASELINE_511010`：现行 V3（`511010.SH` 蓄水池 + `DEFENSIVE` 15% 红利）；
- `D1_LOW_TICKET_RESERVE`：低单手债券蓄水池（`159649.SZ` / `511260.SH`，单手 ~¥1,000–¥1,400，且仅当防御缺口 ≥¥5,000 时调仓；对照附 `D1B_MMF_IDLE_SWEEP` 将剩余现金计入 `511880.SH` 货基/逆回购收益代理）；
- `D2_TREND_DEFENSIVE_ROTATION`：`DEFENSIVE` 档 15% 风险预算 + 10% 机动黄金在【红利低波、实物黄金 `518880`】之间启用趋势过滤（仅 `Close > MA_w` 且 `MA20 > MA_w` 时持有，破位全部自动归入利率债蓄水池），测试 `MA_w ∈ {40, 60, 90}` 粗粒度高原；
- `D3_UNFILTERED_GOLD_CTRL`：无趋势过滤固定配置 10% 黄金对照。

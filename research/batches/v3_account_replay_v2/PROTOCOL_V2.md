# EXP-V3-05B：解锁 PIT `circ_mv` 个股先锋腿的完整单账户原生回放（预注册协议）

状态：`FROZEN_PROTOCOL_V2 / PRE_RESULT`。日期：2026-11-26。针对 `EXP-V3-05`（`RL-063`）因快照缺失逐日流通市值 `circ_mv` 而被限制为 `ETF-only PARTIAL_DATA` 的遗留缺口，接入 `v3_snapshot_20261126` 与 `v3_aux_20261126/daily_basic_pit.csv`（覆至 `2026-11-26`）及新下载 `RQAlpha 2026-11` 数据包（覆盖至 `2026-10-30`，首次囊括 `2026-09~10` 深熊主跌段），完成含 `BP1_PULLBACK` 主板个股先锋腿的完整 V3 单账户原生回放。

## 1. External Evidence Gate

- **Canonical mapping**: 完整 V3 组合（双锚三档 + `BOTTOM_GRIND_25` + `BP1_PULLBACK` 质量动量个股先锋 + 前置 L2 回撤保护）。
- **External tier**: `E3` / `E4_OPEN_LOCAL`。
- **External conclusion**: 单策略（如 `EXP-V3-02` 独立个股或 `EXP-V3-04` 独立磨底）的正期望不能自动外推至共享现金、共享 12%/15% 高水位熔断与优先级抢占的单一实盘账户。
- **Relevant contradictions**: `EXP-V3-05` ETF-only 路径中，OOS 70% 集中起手触发 5 次 L2 锁并穿 `-15%` 红线；同时高集中仓限制了资金分配给个股先锋腿的实际能力。
- **Upstream implementation**: 原生 `RQAlpha 6.3.0`（`open_auction`、`stock_t1=True`、分层佣金 decider + 股票卖出万 5 印花税 + 双边万 1‰ 过户费 + 显式万 5 股票滑点）。
- **Existing TactiCore evidence**: `EXP-V3-02`（`BP1` OOS `+2.329%`）、`EXP-V3-05`（ETF-only `REDLINE_BREACHED`）。
- **Remaining local gap**: 加入 PIT `circ_mv >= 50 亿` 与 `v3.2.1` 语义（无行业前 30% 硬门控、收盘跌破 `MA20` 无条件次日开盘离场、`+15%` 仅上移保本、`-8%` 硬止损、以损定仓 `1.3%` / `18%` / `≥¥8,000`）后的完整 V3 OOS 单账户真实表现、穿线与个股贡献。
- **Research action**: `LOCAL_ADJUDICATION`（OOS 完整 V3；IS 因仍缺 2017–2023 当次公告版 PIT 财务保持 `IS_STOCK_BLOCKED_DATA`，本实验专注 OOS `2024-07-01..2026-10-30`）。

## 2. PIT Tradability Gate

1. **Date-aware universe**: 沪深主板非 ST 个股（含退市历史）、上市 `>= 250` 日、20 日均额 `>= 1.5 亿`、当日 PIT `circ_mv >= 50 亿元`、`0 < raw_close <= 90`、非停牌非一字板；ETF 池沿用 `EXP-V3-05` 白名单及替补。
2. **Asset lifetime metadata**: 来自 `bundle_202611_root/bundle` `instruments.pk`。
3. **Pre-listing fallback**: `159558.SZ` 无上市前代理；宽基超级 ETF 上市前用同指数老牌 ETF。
4. **Missing execution price / suspension**: 停牌/涨跌停/高开 `>+2%` 跳过买入，跌停顺延卖出；严禁未来函数。
5. **Strategy inception**: OOS `2024-07-01..2026-10-30`（`CORE25` 与 `HEAVY70` 两种初始集中度 × `¥69,000` / `¥100,000` × `LOCK` / `NEVER_L2` 共 8 格），另附全期无集中起始 `OOS_CASH_2024`（`2024-02-01..2026-10-30`）以独立观测个股+底盘完整协同。
6. **Executability of every positive target**: 全部订单经原生 `order_shares` 撮合、严格 100 股整手、T+1 可卖校验，逐笔核对费用与现金。

# EXP-V3-12：V3.3.1 精简架构验证（关闭行业先导 + 取消降浓状态机 + 无状态平滑过渡 + 简单基准对照）

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-27。

## 1. 研究目的与前置审计背景

针对 `2026-11-27` 对 `v3.3.0` 的只读策略与架构审计（`AShareInvestor/docs/v3-offensive-system/HANDOFF_20261127_V331.md` 及执行架构联合裁决）：
1. 验证 **关闭 20% 超级行业动量先导（`sector_pioneer_enabled = false`）** 并将预算并回免五底盘核心（`OFFENSIVE` 85% / 含 BP1 留白 65%、`STRUCTURAL` 60% / 50%；无条件 `1+1+2` ≤4 只底盘 + `hold_sticky=true`；`P1` ETF 移动止盈仅覆盖 `SECTOR_PIONEER`），在 `2018..2026-10` 全窗底盘（IS `2018-2023` 与 OOS `2024-2026` 显式分拆）及 `2024..2026-10` 统一账户重演（含此前漏列的 `CORE25_100000`）中，相比 `v3.3.0`（含行业先导）的净收益、最大回撤、Sharpe、Calmar 与摩擦损耗变化。
2. 验证 **取消 `159558.SZ` `BOTTOM_GRIND_25` 降浓状态机 + 档位目标对存量持仓双向生效 + 无状态 2 日收敛与统一 `align_due`**（`align_glide_carryover_bps = 3500`：若超额 `excess <= cap + 2%` 全卖，否则卖 `max(cap, excess - cap)`；当日总卖出 `max(P0, glide)`；`P3-BUY` 严格约束买后总风险权益 `<= router_effective_cap`；无状态 `align_due` 含非目标持仓/档位风格切换/解锁或 P0 触发/权益偏离 `>= 500 bps`/债基偏离 `>= 1000 bps`）在 70% 遗留高波重仓起步场景（`LEGACY70_ALIGN`）及 `OOS_CASH` / `CORE25` 下，对比 `v3.3.0` 原逻辑的回撤保护与收益效率。
3. 检验 **敏感性臂 `M2_EARLY_RELEASE`**：在 `L2_LOCKED` 锁定满 5 个交易日且 `M2` 刚触发宽度推力事件时，允许提前解锁重锚并以 20% 试探上限进入 `RECOVERY`，确认其是否有净增量价值（若无明显增益则维持标准锁定）。
4. 同引擎同窗口对照简单基准 **Shadow B（静态四桶 25%×4 年度再平衡）** 及 **Shadow B + `TWO_STAGE_GRADUAL` 风控叠加层**，显式披露 `IS / OOS` 分拆、样本量及摩擦成本。

## 2. 数据与物理约束

- 只读加载 `v3_snapshot_20261126`、`v3_aux_20261126` 与 `bundle_202611_root/bundle`（RQAlpha 截至 `2026-10-30`，VectorBT 拼接至 `2026-11-26`；绝不宣称 RQAlpha 覆盖 2026-11）。
- 严格执行东方财富阶梯费率（33 只超级 ETF 万 0.5 免五；普通 ETF 含 `159649.SZ`/`511260.SH`/`511010.SH` 万 2.5 最低 5 元；主板个股万 2.5 最低 5 元 + 卖出万 5 印花税 + 十万分之 1 过户费 + 5bp 显式滑点）、100 股整手、T+1 制度与次日开盘撮合。

## 3. 预注册验收与选型规则

- 完整性门槛：全部 RQAlpha 回放 `dates_pass = True`、`fill_capture_pass = True`、`fees_pass = True`、`illegal_non_lot_fills = 0`、`violation_count = 0`。
- `V3_3_1_CLEAN_NO_PIONEER` 采纳条件：
  1. 全窗底盘 `¥69k` / `¥100k` MaxDD 严格 `> -15%`；
  2. 统一账户 6 组核心重演（`OOS_CASH_{69k,100k}`、`CORE25_{69k,100k}`、`LEGACY70_ALIGN_{69k,100k}`）中，`V3_3_1_CLEAN` 相比 `V3_3_0_WITH_PIONEER` 在至少多数场景取得更高或持平的 Calmar/更低摩擦，且 `LEGACY70_ALIGN_69000` 穿 `-15%` 天数 `<= 5` 天、真实 Peak DD 优于或持平；
  3. 若 `V3_3_1_M2_EARLY_RELEASE` 未在全窗 Calmar 提升 `>= +0.02` 且回撤不恶化，则维持标准锁定（`l2_lock_allow_m2_early_release = false`）以防过度参数化。

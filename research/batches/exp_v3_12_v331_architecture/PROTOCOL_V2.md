# EXP-V3-12 R2：V3.3.1 新粘性规则与行业先导严格消融（预注册方案 V2）

状态：`FROZEN_PROTOCOL_V2 / PRE_RESULT`。日期：2026-11-27。

> 本协议严格遵循 `@architect-opus` 与 `@coordinator` 联合终审要求（消息 #10），保留 V1 产物（`EXP_V3_12_V331_ARCHITECTURE.{json,md}`）不变以便审计，使用新产物前缀 `EXP_V3_12_V331_ARCHITECTURE_R2` 进行预注册重跑。

## 1. 修订内容（相对 PROTOCOL_V1）

1. **修正 `hold_sticky` 为“只向高优先级粘性保留”（Upward-Only Sticky）**：
   - 每个底盘桶按优先级从高到低遍历，选择**第一只满足 `(已持有且可持有) 或 (当前可买)`** 的成员（`LOW_VOL` 依次填满 2 个名额；回测优先级序列含 PIT 备选如 `510300.SH`/`512890.SH`）。
   - 若高优先级标的暂时受阻（如实盘溢价拦截），保留已持有的该高优先级成员；当更高优先级新标的上市可买时，仅升级一次，彻底避免 V1 中“绝对粘性将 2024 起步账户永久锁死在旧备选 ETF”导致 `-3pp` 年化损失的缺陷。
2. **严格单开关消融对比三组**：
   - **(a) `V3_3_1_CLEAN_UPWARD_STICKY`（最终候选）**：`use_sector_pioneer=False` + 20% 预算并回底盘、`deconcentration_enabled=False`、`align_glide_carryover_w=0.35`（`excess<=cap+2%` 全卖 else `max(cap, excess-cap)`、`max(P0, glide)`）、`p1_etf_trailing_sleeves=("SECTOR_PIONEER",)`、新粘性规则、无状态 `align_due`（`equity_drift_band=0.05` / `bond_drift_band=0.10`）。
   - **(b) `V3_3_1_WITH_PIONEER_ABLATION`（严格单开关对照）**：同一 V3.3.1 新引擎，**仅打开 `use_sector_pioneer=True`**（20% 行业动量先导独立分配，`P1` 覆盖 `SECTOR_PIONEER`）。
   - **(c) `V3_3_1_NO_STICKY_REF`（粘性关闭参照）**：同一 V3.3.1 新引擎，粘性关闭（`sticky_mode="none"`）。
   - **基线参照**：`V3_3_0_WITH_PIONEER` / `V3_3_0_GRIND25` 直接引用 V1 已核验（与 `EXP-V3-11` 一致）的原版结果。
3. **关闭 `l2_lock_allow_m2_early_release`**：V1 全窗 0 次触发，确认不引入无法验证的分支。
4. **范围与归因披露**：覆盖全部 6 个统一账户场景（`OOS_CASH` / `CORE25` / `LEGACY70` @ `¥69k` / `¥100k`）及 RQAlpha 全窗底盘 `69k / 100k`（`(a)` 与 `(b)`），并显式输出每组 `BP1` 个股交易笔数与盈亏。

## 2. 预注册 R2 放行门槛（先写死、后看数）

- **完整性硬门禁**：全部 RQAlpha 底盘回放 `dates_pass=True`、`fill_capture_pass=True`、`fees_pass=True`、`illegal_non_lot_fills=0`；全部统一账户回放 `violation_count=0`。
- **决策锚点说明**：决策以 **`¥69k` 组**为准（实盘净值约 6.3 万元，`BP1` 门槛 10 万元处于休眠）；`¥100k` 组仅作参考（因 `BP1` 单股路径依赖极强：`LEGACY70_100k` 中 `BP1` 盈亏在 `¥23.0k` 与 `¥6.7k` 间剧烈摆动，`OOS_CASH_100k` 仅改粘性即从 `11.7%` 波动至 `3.3%`，不适合作为核心决策判据）。
- **`V3_3_1_CLEAN_APPROVED` 采纳条件（须同时满足）**：
  1. 全部 6 个统一账户场景的真实峰值回撤（`true_max_dd`）均不劣于 `v3.3.0`（且 `LEGACY70` 穿 `-15%` 天数 `<= 5` 天）；
  2. `¥69k` 三组统一账户场景（`OOS_CASH_69000`、`CORE25_69000`、`LEGACY70_69000`）中，至少 2 组满足 `Calmar >= v3.3.0_Calmar - 0.05`；
  3. 全窗底盘 RQAlpha `¥69k` 与 `¥100k` 两档 `MaxDD` 均严格 `> -15%`。
- **行业先导保留原则**：所有者已拍板在 `v3.3.1` 关闭 `sector_pioneer`。除非 `(b)` 在 `¥69k` 组的 Calmar 与真实回撤上**同时明显占优**，否则维持关闭；即便占优也仅上报所有者，不自行改回。

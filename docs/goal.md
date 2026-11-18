# TactiCore — 当前执行指令（Dual-Domain: Frozen S2/S4C Prospective + Owner-Authorized V3 Account Validation）

状态：
1. **既有冻结域（`data/canonical/`、`research/shadow/s2_r1/`、`research/shadow/s4c_r1/`）**：Foundation V1 完成并通过独立 revalidation，继续保持开发冻结，等待真实前瞻时间窗口，**本轮绝不触碰**。
2. **账户实盘研究域（`research/ashare/` — FinanceMCP V3 进取型低频攻防系统 Phase 2）**：依据仓库所有者（用户）2026-11-15 对 `AShareInvestor/docs/v3-offensive-system/MASTER_PLAN_V3.md` 与 `SERVER_EXECUTION_WORK_ORDER.md` 的明确授权及 2026-11-18 对 `159558.SZ` 留存 25% 底仓震荡磨底降本模式的升级授权，在隔离域 `research/ashare/` 内执行 `EXP-V3-01`、`EXP-V3-02`、`EXP-V3-03`、`EXP-V3-04` 四大样本内/外对照实验，并在通过门控后签发带 `APPROVED_FOR_ACCOUNT` 的版本化 `StrategyRelease` 契约文件（`v3.1.0` / `v3.2.0`）。

---

## 强制前置门控 1：External Evidence Gate（8 项必填）

- **Canonical mapping**:
  - `EXP-V3-01` -> `V3_DUAL_ANCHOR_SUPER_ETF`（time-series / GTAA breadth regime + Eastmoney Super ETF `0.5bp` zero-min rotation）
  - `EXP-V3-02` -> `V3_MAINBOARD_SWING_BREAKOUT_PULLBACK`（China main-board quality + RPS momentum pullback `BP1` vs tight breakout `BP2` under realistic ¥5 floor friction）
  - `EXP-V3-03` -> `V3_CONCENTRATED_SECTOR_EXIT`（asymmetric 4-tranche deconcentration state machine for ~70% high-volatility sector ETF positions）
  - `EXP-V3-04` -> `V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION`（25% strategic core + 4-guard 10% bottom-grind reload/take-profit + overweight drift harvest for `159558.SZ`）
- **External tier**:
  - `EXP-V3-01`: `E3_MIXED_CONDITIONAL`（Faber GTAA 与趋势跟踪虽成熟，但 A 股双锚广度 + 万 0.5 免五费率结构属于成本敏感型局部迁移判定）
  - `EXP-V3-02`: `E3_MIXED_CONDITIONAL`（质量与动量在美股成熟，但 Yang/Gebka/Hudson 等指出中国 A 股动量高度受频率、跌停与小资金最低佣金摩擦影响）
  - `EXP-V3-03`: `E4_OPEN_LOCAL`（重仓半导体/光伏/医药 ETF 的四批换马路径与 `MA60` 防守保护属于高度本地化账户工程假设）
  - `EXP-V3-04`: `E4_OPEN_LOCAL`（重仓半导体 ETF 深跌磨底期 25% 底仓与四门槛单槽 `+10%` 降本规则属于高波低频账户负期望防控局部实盘假设）
- **External conclusion**:
  - 纯静态 60/40 或无摩擦回测均不足以证明约 7–10 万元实盘 A 股账户的可持续净期望；必须按费率分层（Super ETF 万 0.5 免五 vs 主板股票万 2.5 最低 5 元+卖出万 5 印花税+双边万 5 滑点）、T+1 与涨跌停撮合实测裁决。
- **Relevant contradictions**:
  - Kim/Tse/Wald (2016) 与 Cederburg 等 (2020) 指出趋势/波动率择时在多头阶段或样本外易出现收益折损与换手税费反噬；`RL-053`（`ACCOUNT_TRANSFER_V1`）亦否证了"50% 现金 + 15% 单手短债 + ±10% 200日线静态基座倾斜（A2 vs A0）"。
  - 与 `RL-053` 的正交边界：本轮 V3 研究与已关闭的 `RL-053` 在资产池（33 只东财万 0.5 免五超级 ETF 与主板强趋势股 vs 4 只传统高佣金 ETF+50%现金）、仓位振幅（`85% / 60% / 15%` 攻防切档 vs `±10%` 倾斜）、信号机制（双锚+全市场站上 `MA60` 占比+成交量+2日滞回+L0 `-15%` 熔断 vs 单纯 200 日线）以及单票重仓换马均完全正交，不构成旧问题改名重开。
- **Upstream implementation**:
  - 组合级研究与消融严格复用 `VectorBT`（`tacticore/engines/vectorbt_adapter.py:run_target_weights`），事件驱动撮合、T+1、涨跌停拒单、整手（100 股/份）与最低 5 元佣金+印花税严格复用 **原生 RQAlpha 6.3.0**（`rqalpha.run_func` / `research/ashare/engines/rqalpha_replay.py`），**禁止另写第三套回测或记账引擎**。
- **Existing TactiCore evidence**:
  - `S2_R1` / `S4C_R1` 仅作历史研究基线参照；`RL-053`（`ACCOUNT_TRANSFER_V1`）保留 `REJECT` 作为边界反证；`research/ashare/data/contract.py` 与 `adapter.py` 提供 `FinanceMCP research-export` 内容寻址快照契约。
- **Remaining local gap**:
  1. `EXP-V3-01`：`2018–2023` 样本内锁定参数在 `2024–2026` 样本外盲测是否同时守住 `MaxDD > -15%`、牛市年化捕获 `>= 75%` 与年化换手 `< 12x`；
  2. `EXP-V3-02`：在 7 万与 10 万账户下，`BP1`（回踩缩量）与 `BP2`（窄幅平台突破）谁能取得正的 OOS 净数学期望，以及单笔费率拖累百分比；
  3. `EXP-V3-03`：四批换马状态机在高波动行业 ETF 泡沫破裂期是否在不放弃反弹兑现的前提下避免击穿账户 `-15%` HWM 熔断线；
  4. `EXP-V3-04`：`159558.SZ` 留存 25% 底仓并启用四门槛 `+10%` 战术降本后，能否稳定跑赢 25% 静态持有并证伪低位月度强卖、无门控网格与窄止损。
- **Research action**:
  - `LOCAL_ADJUDICATION`（`EXP-V3-01`、`EXP-V3-02`）与 `NEW_HYPOTHESIS`（`EXP-V3-03`、`EXP-V3-04`）。凡 `EXP-V3-02` 中 OOS 净期望 `<= 0` 的买点直接 `REJECTED_DROP` 禁用，不得事后调参挽救；凡 `EXP-V3-04` 中被证伪的负期望操作禁止接入实盘。

---

## 强制前置门控 2：PIT Tradability Gate（6 要素全覆）

1. **Date-aware universe（时点感知资产池）**：
   - `EXP-V3-01` 使用按日检验 `tradability_mask` 的 33 只东财超级 ETF 白名单及其历史可交易指数替补链（见下条）；
   - `EXP-V3-02` 仅在每个信号日 `T` 纳入当时已上市满 180 个自然日、非 ST（RQAlpha `is_st_stock`）、非停牌、20 日均成交额 `>= 1.5 亿元` 的沪深主板 A 股，财务指标严格按 `ann_date <= T` 过滤（含季报累计 ROE 年化换算），绝不使用未来年报或今日成分表。
2. **Asset lifetime metadata（生命周期元数据）**：
   - 所有标的均绑定 `AssetLifetime(listed_date, delisted_date)`（源自 RQAlpha `instruments.pk` 与 `FinanceMCP stock_basic/fund_basic`），任何早于 `listed_date` 或晚于 `delisted_date` 的价格均强制置为 `NaN` 并在 `tradability_mask` 标记为 `False`。
3. **Pre-listing fallback handling（上市前替补链，禁止零填充与未来泄漏）**：
   - 由于部分东财超级 ETF 于 2023–2026 年上市（如 `159330.SZ` 2024-08-19、`159337.SZ` 2024-09-20、`159205.SZ` 2025-06-12），在 2018–2025 年期间严格通过显式 PIT 替补链映射至同期可交易同类宽基 ETF（`510300.SH` / `512890.SH` / `510500.SH` / `159915.SZ` / `511010.SH`），且仅在替补/目标 ETF 上市满 20 个交易日后才允许获批正权重，由 `validate_execution_targets` 强制阻断任何非法正权重。
4. **Missing execution price / suspension & limit-up/down handling（停牌、缺失价与涨跌停处理）**：
   - `NaN` 永远保持 `NaN`（绝不转为 `0`）；停牌日（`suspend` / RQAlpha `is_suspended` / `volume == 0`）标记不可交易；`EXP-V3-02` 次日开盘集合竞价严格校验证券涨跌停板：涨停开盘或高开超 `+3%` 跳过买入，跌停开盘顺延至次日卖出，绝不虚构不可成交的涨跌停成交。
5. **Strategy inception（策略生效边界与样本划分）**：
   - 统一主样本窗口：`2018-01-02` 至 `2026-11-13`（其中 RQAlpha native `bundle` 覆盖至 `2026-08-31`，`2026-09-01` 至 `2026-11-13` 由已校验内容哈希的 `FinanceMCP v3_snapshot_20261113` 只读快照按日收益率链式无跳变衔接）。IS 为 `2018-01-02`–`2023-12-29`，OOS 盲测为 `2024-01-02`–`2026-11-13`；`EXP-V3-02` OOS 期分设全期与 `fina_indicator`（`ann_date >= 2024-01-20`）完整财务覆盖窗口透明对照。
6. **Executability of every positive target（每笔正目标可执行性校验）**：
   - 所有 VectorBT 运行前均经过 `validate_execution_targets` 零容忍检查；所有 RQAlpha 运行核对 `order_creation_rejected`、现金不足、整手（100 股/份）约束与含 ¥5 最低佣金+印花税+滑点后的真实成交成本。

---

## 既有冻结域硬边界（本轮严格保持不变）

```text
不得修改 research/shadow/s2_r1/、research/shadow/s4c_r1/、data/canonical/、research/batches/transfer_v1/
不得修改 tacticore/engines/vectorbt_adapter.py 与 rqalpha_adapter.py 的核心撮合/会计逻辑
不得在 2026-09-30/10-30 等既有 S2/S4C 影子台账中伪造或回填 prospective observation
不得复活 V1/V2 过度防御教条（NO_ACTION 清零 / 未导入流水阻断 / 18 个月全自动封印锁定）
```

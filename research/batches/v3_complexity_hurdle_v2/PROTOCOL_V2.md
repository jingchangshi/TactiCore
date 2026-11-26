# V3_COMPLEXITY_HURDLE_V2 预注册协议

状态：`FROZEN_PROTOCOL_V2 / PRE_RESULT`。日期：2026-11-26。本协议继承并修正 `V3_COMPLEXITY_HURDLE_V1`（因 `510500.XSHG` 2022-08-29 折算因子留存零股在一次性清仓卖出时触发整手 veto 而判 `INVALID_RUN`），将评估窗口升级至最新 `RQAlpha 2026-11` 隔离数据包（`2018-01-02..2026-10-30`）及 `VectorBT 2026-11-26` 全窗（含 2026 H2 熊市与黄金暴跌切片）。本文件不修改任何已签发 `v3.2.0`/`v3.2.1` release 或既有 `V3_COMPLEXITY_HURDLE_V1` 归档。

## 1. External Evidence Gate

- **Canonical mapping**: A (`V3_ETF_CHASSIS`) → `V3_DUAL_ANCHOR_SUPER_ETF`；B (`STATIC_S30_STYLE`) → `STATIC_DIVERSIFICATION`；C (`ERC_S4C_STYLE`) → `ERC_RISK_PARITY`（skfolio `RiskBudgeting`）；D (`STATIC_60_40`) → 静态股债 60/40。
- **External tier**: A 为 `E3_MIXED_CONDITIONAL`；B 为 `E1_MATURE`；C 为 `E2_ESTABLISHED_METHOD`。
- **External conclusion**: 静态分散（1/N / S30）与风险平价（ERC）在真实小账户最低 5 元佣金下的成本显著低于高频择时；动态择时必须证明在扣除真实分层佣金与整手摩擦后超越简单基准。
- **Relevant contradictions**: Kim/Tse/Wald (2016)、Cederburg 等 (2020)、`RL-053`、`V3_COMPLEXITY_HURDLE_V1` 中 `A_69000` 佣金达本金 4.52% 且 Sharpe 低于静态 B 与 ERC C。
- **Upstream implementation**: 原生 `RQAlpha 6.3.0`（`~/.rqalpha/bundle_202611_root/bundle`，覆盖至 `2026-10-30`）+ `TieredCosts` 官方成本扩展点 + `VectorBT`（延展至 `2026-11-26`）。
- **Existing TactiCore evidence**: `EXP_V3_01_REGIME_SUPER_ETF.*`、`V3_COMPLEXITY_HURDLE_V1.json`。
- **Remaining local gap**: 合法放行“公司行动余股随全仓清仓一次卖出”后，同窗同本金（¥69,000 / ¥100,000）真实分层费率下 `A` vs `B` / `C` 的 §8 正式裁决，以及包含 2026-07..11 黄金 `-38.9%` 暴跌冲击下的真实排名。
- **Research action**: `LOCAL_ADJUDICATION`（只读诊断，给出明确裁决）。

## 2. PIT Tradability Gate

1. **Date-aware universe**: A 使用 33 只白名单 + `EXP-V3-01` PIT 替补链；B/C 使用固定四袖子（`159330/510300`、`159337/510500`、`518880`、`511010`）。
2. **Asset lifetime metadata**: 来自 `/home/jcshi/.rqalpha/bundle_202611_root/bundle` 与 `v3_snapshot_20261126/fund_basic.csv`。
3. **Pre-listing fallback**: `159330.SZ`（2024-08-19 上市）前用 `510300.SH`，`159337.SZ`（2024-09-20 上市）前用 `510500.SH`；满 20 交易日后只在调仓日迁入。
4. **Missing execution price / suspension**: `NaN` 保持 `NaN`，`validate_execution_targets` 零容忍校验。
5. **Strategy inception**: `2018-01-02` 起步；RQAlpha 原生窗 `2018-01-02..2026-10-30`（IS `..2023-12-29`，OOS `2024-01-02..2026-10-30`）；VectorBT 全窗至 `2026-11-26`，另报告 `2026-07-01..2026-11-26` 深熊黄金杀跌切片。
6. **Executability of every positive target**: 主动买卖严格 100 份整手；仅当持仓因基金拆分/折算产生非整百零股且本次为一次性全仓清仓（`target == 0`）时合法放行并单独计数，禁止任何非整百主动买入或部分非整百卖出。

## 3. 预注册裁决规则

沿用 V1 §8：`Sharpe_A >= Sharpe_X + 0.10` 且 `Calmar_A >= Calmar_X + 0.10` 视为优于 X；`MaxDD_A >= MaxDD_B + 0.05` 视为 MaxDD 显著更好。两档本金（¥69,000 与 ¥100,000）同时判断：`V3_REGIME_CLEARS_HURDLE` / `V3_REGIME_IS_RISK_OVERLAY_NOT_RETURN_SOURCE` / `MIXED`。

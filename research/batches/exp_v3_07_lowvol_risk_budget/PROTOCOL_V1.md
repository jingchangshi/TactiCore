# EXP-V3-07：红利低波常驻底盘迁移与 V3 底盘内风险预算定权（预注册协议）

状态：`FROZEN_PROTOCOL_V1 / PRE_RESULT`。日期：2026-11-26。针对当前市场双创 20 日年化波动率达 47%–58%（沪深 300 仅 14%）引发的“名义等权 = 80% 风险押注高波成长”失衡问题，在保持 V3 三档总权益水位（85/60/15）的前提下，检验将红利低波纳入常驻底盘及用逆波动率/ERC 定权底盘桶的风险调整收益改进。

## 1. External Evidence Gate

- **Canonical mapping**: `LOW_VOL`（`E1_MATURE` 本地迁移，`NOT_STARTED`）+ `ERC_RISK_PARITY` / `VOL_SCALED_TREND`（`E2`/`E3`）。
- **External tier**: `LOW_VOL` 为 `E1_MATURE`（Blitz/Pang/van Vliet 2013 证实中国低波与高股息异象存在）；风险预算定权为 `E2_ESTABLISHED_METHOD`。
- **External conclusion**: 低波股票异象存在但不自动等价于中国低波 ETF 在 V3 动态仓位框架内的增量；ERC 是风险构造方法，需检验在三档择时内部能否降低尾部回撤。
- **Relevant contradictions**: 坚决区隔于已关闭 `S4A`（全池无趋势逆波未通过相对等权的 3pp MaxDD 改善门槛）；本文只在 V3 三档动态权益预算内部重新分配风格桶，且保留静态 `S30` 与纯 `ERC` 作为同窗复杂度标尺。
- **Upstream implementation**: `VectorBT`（`2018-01-02..2026-11-26`）+ 上游 `skfolio` `RiskBudgeting(VARIANCE)` + 原生 `RQAlpha 6.3.0`（`2018-01-02..2026-10-30`，¥69k / ¥100k 分层费率）。
- **Existing TactiCore evidence**: `S4A`（`REJECTED`）、`S4C`（ERC `PROSPECTIVE_SHADOW_ACTIVE`）、`S27A`（`ADVANCE_TO_CANDIDATE_FREEZE_REVIEW`）。
- **Remaining local gap**: `LOW_VOL` 免五超级 ETF（`159549.SZ`/`159207.SZ`，PIT 替补 `512890.SH`/`510880.SH`）全周期常驻底盘，及在 V3 底盘内用 `40/60/80` 日逆波或 ERC 替换名义权重能否超越现行 V3 与静态标尺。
- **Research action**: `TRANSFER_VALIDATE` & `UPSTREAM_COMPARE`。

## 2. PIT Tradability Gate

1. **Date-aware universe**: 价值桶（`159330/530050/510140`，替补 `510300`）、成长桶（`159205/159337/589850`，替补 `510500/159915`）、红利低波桶（`159549/159207`，替补 `512890/510880`）、蓄水池 `511010.SH`。
2. **Asset lifetime metadata**: `bundle_202611` 与 `v3_snapshot_20261126`。
3. **Pre-listing fallback**: 严格上市满 20 交易日才替换老牌同类 ETF，绝不回填。
4. **Missing execution price / suspension**: `NaN != 0`，严格经 `validate_execution_targets` 校验。
5. **Strategy inception**: `2018-01-02..2026-11-26`（RQAlpha `..2026-10-30`）。
6. **Executability of every positive target**: 真实分层费率与 100 份整手执行。

## 3. 对照臂与参数高原

- `R0_V3_EQUAL_BUCKET`：现行 V3 价值/成长两桶名义配比；
- `R1_V3_WITH_LOWVOL_CORE`：OFFENSIVE/STRUCTURAL 底盘均分纳入第三桶红利低波（价值/成长/红利按 `35/35/30` 或风格倾斜 `50/25/25` 预声明固定配比）；
- `R2_V3_INVVOL_BUCKET`：底盘三桶（价值/成长/红利）采用过去 `W ∈ {40, 60, 80}` 日实现波动率倒数定权（`sum = 1` 乘以档位权益上限）；
- `R3_V3_SKFOLIO_ERC_BUCKET`：底盘三桶采用上游 `skfolio` `RiskBudgeting(VARIANCE)` 对齐 `W ∈ {40, 60, 80}` 日收益定权。

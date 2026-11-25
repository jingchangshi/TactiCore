# EXP-V3-04B: V32 磨底回补门②（折价门）消融报告

## External Evidence Gate

- Canonical mapping: `EXP-V3-04B` -> `V3_SECTOR_BOTTOM_GRIND_COST_REDUCTION`（registry 既有条目；四门槛之门②单因素消融）。
- External tier: `E4_OPEN_LOCAL`。
- External conclusion: 外部证据只支持深跌低吸需过滤的一般结论，不回答门②在其余三门存在时是否冗余。
- Relevant contradictions: `EXP-V3-04` 3×3 高原 `disc = 6%/7%/8%` 结果逐位相同，与“>=7% discount 为独立护栏”的规格表述矛盾。
- Upstream implementation: VectorBT `run_target_weights`；原生 RQAlpha 6.3.0 复用原脚本 `_run_rqalpha_check`。
- Existing TactiCore evidence: `RL-055`、`EXP_V3_04_BOTTOM_GRIND_COST_REDUCTION.*`。
- Remaining local gap: 门②是否曾为唯一否决条件；去掉它的影响。
- Research action: `BOUNDED_ABLATION`。

## PIT Tradability Gate

1. Date-aware universe: 与 `EXP-V3-04` 相同 9 窗口与标的，`etf_tradability_mask` 原样传入。
2. Asset lifetime metadata: `v3_data.py` `etf_lifetimes`（只读）。
3. Pre-listing fallback handling: 不回填；`159558.SZ` 自 `2024-07-16` 起。
4. Missing execution price / suspension: `NaN` 不补零；`T` 收盘信号、`T+1` 执行。
5. Strategy inception: 每窗 25% 目标 ETF + 75% `511010.SH`。
6. Executability of every positive target: VectorBT `validate_execution_targets`；RQAlpha 4 窗口拒单计数（bundle 截至 2026-08-31）。

## 裁决

- **Verdict**: `GATE2_BINDING_RETAIN`（gate 2 binding; pre-registered not-worse test applied）
- production_admission: `NOT_APPROVED`；协议 `research/batches/exp_v3_04b/PROTOCOL_V1.md`
- Snapshot ID: `ca43f6393393056d6b318bba792c3f6c70c7c5d786f72a7ec6beab366d5b5a78`
- 复写等价（V32_REPRO == V32，9 窗口）: `True`
- 门② binding count 合计: `36`
- VectorBT 消融逐位一致: `False`；原生 RQAlpha 逐位一致: `False`

## 一、门②约束诊断（V32 路径）

| 窗口 | 评估日 | 候选日(①③④通过) | binding | 近卖出分支 | 60日高点分支 | 门②失败(任意) | V32 入场 | 去门②入场 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| IS_512480_19_23 | 785 | 11 | 8 | 3 | 5 | 563 | 3 | 4 |
| IS_512480_BEAR | 366 | 6 | 4 | 0 | 4 | 217 | 2 | 1 |
| IS_515790_BEAR | 306 | 3 | 2 | 0 | 2 | 110 | 1 | 1 |
| IS_512170_BEAR | 503 | 4 | 3 | 0 | 3 | 300 | 1 | 1 |
| OOS_512480_24_26 | 502 | 6 | 3 | 2 | 1 | 439 | 3 | 6 |
| OOS_159558_24_26 | 518 | 10 | 6 | 6 | 0 | 438 | 4 | 6 |
| OOS_159558_2026 | 178 | 7 | 4 | 3 | 1 | 122 | 3 | 4 |
| OOS_515790_24_26 | 500 | 3 | 2 | 1 | 1 | 336 | 1 | 3 |
| OOS_512170_24_26 | 691 | 4 | 4 | 0 | 4 | 608 | 0 | 2 |

## 二、消融对照（相对静态 25% 的均值）

| 臂 | IS 超额 | IS MDD 差 | OOS 超额 | OOS MDD 差 | 胜/负 | 调仓数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v32 | +0.47pp | +1.42pp | +3.90pp | +7.73pp | 15/0 | 38 |
| v32_no_gate2 | -4.19pp | -3.36pp | +5.55pp | +7.50pp | 21/2 | 54 |

## 三、逐窗口（VectorBT）

| 窗口 | 静态25% 收益/MDD | V32 收益/MDD | 去门② 收益/MDD | V32 胜/负 | 去门② 胜/负 | 权重一致 |
| --- | --- | --- | --- | ---: | ---: | --- |
| IS_512480_19_23 | +18.84% / -21.37% | +24.86% / -12.71% | +20.49% / -16.60% | 2/0 | 3/0 | False |
| IS_512480_BEAR | -6.66% / -10.34% | -9.32% / -10.88% | -12.11% / -15.62% | 1/0 | 0/0 | False |
| IS_515790_BEAR | -10.21% / -13.04% | -10.28% / -13.23% | -15.73% / -19.05% | 1/0 | 0/0 | False |
| IS_512170_BEAR | -8.75% / -10.15% | -10.16% / -12.42% | -16.19% / -17.09% | 1/0 | 0/0 | False |
| OOS_512480_24_26 | +32.11% / -28.37% | +34.46% / -18.70% | +38.00% / -20.24% | 2/0 | 5/0 | False |
| OOS_159558_24_26 | +42.71% / -33.45% | +49.10% / -14.46% | +50.53% / -14.49% | 4/0 | 5/1 | False |
| OOS_159558_2026 | +8.97% / -24.49% | +17.70% / -14.46% | +17.26% / -14.49% | 3/0 | 3/1 | False |
| OOS_515790_24_26 | +1.92% / -11.69% | +3.97% / -11.72% | +6.65% / -9.93% | 1/0 | 3/0 | False |
| OOS_512170_24_26 | +3.86% / -5.36% | +3.86% / -5.36% | +4.86% / -6.70% | 0/0 | 2/0 | False |

## 四、原生 RQAlpha 6.3.0 复核

| 窗口 | 区间 | V32 免五 收益/MDD | 去门② 免五 收益/MDD | V32 5元 | 去门② 5元 | 拒单(V32/去门②) | 一致 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IS_512480_19_23 | 2019-09-02..2023-12-29 | +26.94% / -12.80% | +19.44% / -15.83% | +26.93% | +19.42% | 0/0 | False |
| OOS_512480_24_26 | 2024-01-02..2026-08-31 (partial, bundle cutoff 2026-08-31) | +46.24% / -10.88% | +44.82% / -12.44% | +46.23% | +44.80% | 0/0 | False |
| OOS_159558_24_26 | 2024-07-16..2026-08-31 (partial, bundle cutoff 2026-08-31) | +55.78% / -11.07% | +56.40% / -11.48% | +55.76% | +56.19% | 0/0 | False |
| OOS_159558_2026 | 2026-01-05..2026-08-31 (partial, bundle cutoff 2026-08-31) | +23.57% / -11.15% | +23.27% / -11.43% | +23.55% | +23.25% | 0/0 | False |

## 边界

- 结果仅为新版本候选（`NOT_APPROVED`）；不修改 `v3.2.0` / `v3.2.1`、FinanceMCP 运行参数或 `EXP-V3-04` 原产物。
- 诊断只覆盖原 9 窗口的 V32 路径；未覆盖窗口外的未来行情。

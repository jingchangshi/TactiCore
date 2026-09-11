#!/usr/bin/env python3
# ruff: noqa: E501
"""在冻结 canonical 数据上执行 S2 多资产趋势基线经济筛选。"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import pandas as pd

from research.experiments.run_s1_evidence_closure import (
    PERIODS,
    annual_returns,
    build_static_portfolio,
    period_metrics,
    realized_turnover,
    rolling_table,
)
from tacticore.data.prices import load_price_csv
from tacticore.engines.vectorbt_adapter import ResearchResult, run_target_weights, run_vectorbt
from tacticore.strategies.global_dual_momentum import load_strategy_config
from tacticore.strategies.multi_asset_trend import (
    MultiAssetTrendConfig,
    build_execution_weights,
    build_strict_month_end_targets,
    load_trend_config,
)

ROOT = Path(__file__).resolve().parents[2]
COST_BPS = (15, 30, 50)


def assert_frozen_baseline(config: MultiAssetTrendConfig) -> None:
    if config.trend_window != 200:
        raise ValueError("S2 经济筛选必须冻结为 200 个交易日")
    if config.rebalance_frequency != "monthly":
        raise ValueError("S2 经济筛选必须保持月频")


def run_s2(
    prices: pd.DataFrame,
    config: MultiAssetTrendConfig,
    *,
    total_cost_bps: int | None = None,
    metric_start: pd.Timestamp | None = None,
) -> ResearchResult:
    targets = build_strict_month_end_targets(prices, config)
    execution = build_execution_weights(prices, targets)
    return run_target_weights(
        prices,
        execution,
        fees=config.fees if total_cost_bps is None else total_cost_bps / 10_000,
        slippage=config.slippage if total_cost_bps is None else 0.0,
        initial_cash=config.initial_cash,
        metric_start=metric_start,
    )


def benchmark_table(
    prices: pd.DataFrame,
    s2: ResearchResult,
    config: MultiAssetTrendConfig,
    evaluation_start: pd.Timestamp,
) -> pd.DataFrame:
    """复用 S1 的 VectorBT 静态组合构造，对每个较短历史做同区间比较。"""
    s1_config = load_strategy_config(ROOT / "config/strategy.toml")
    s1 = run_vectorbt(prices, s1_config, metric_start=evaluation_start)
    rows: list[dict[str, Any]] = []

    def add_result(
        series: str,
        group: str,
        equity: pd.Series,
        weights: pd.DataFrame,
        start: pd.Timestamp,
        end: pd.Timestamp,
        turnover: float | None = None,
        note: str = "",
    ) -> None:
        metrics = period_metrics(equity, weights, start, end)
        if turnover is not None:
            metrics["turnover"] = turnover
        rows.append(
            {
                "series": series,
                "comparison_group": group,
                "evaluation_start": start.date().isoformat(),
                "evaluation_end": end.date().isoformat(),
                "availability_note": note,
                **metrics,
            }
        )

    end = prices.index[-1]
    add_result("S2_完整基线", "FULL", s2.equity, s2.execution_weights, evaluation_start, end)
    add_result("S1_拒绝基线_同区间", "S1", s1.equity, s1.execution_weights, evaluation_start, end)
    add_result("S2_同区间_S1", "S1", s2.equity, s2.execution_weights, evaluation_start, end)

    specs = (
        ("B1_沪深300买入持有", {"510300.SS": 1.0}, "buy_hold", evaluation_start, "主评价期"),
        ("B2_美国宽基买入持有", {"513500.SS": 1.0}, "buy_hold", None, "从标的上市日开始"),
        (
            "B3_当前风险资产等权_全员上市后",
            {symbol: 1 / len(config.risk_symbols) for symbol in config.risk_symbols},
            "annual",
            None,
            "所有风险资产共同有行情后开始；不回填",
        ),
        (
            "B4_股债金60_20_20",
            {"510300.SS": 0.6, "511010.SS": 0.2, "518880.SS": 0.2},
            "quarterly",
            None,
            "黄金 ETF 上市后开始",
        ),
    )
    for name, allocation, rebalance, min_start, note in specs:
        source = prices.loc[min_start:] if min_start is not None else prices
        equity, weights, portfolio = build_static_portfolio(
            source, allocation, s1_config, rebalance=rebalance
        )
        start = equity.index[0]
        add_result(
            name,
            name.split("_")[0],
            equity,
            weights,
            start,
            equity.index[-1],
            realized_turnover(portfolio, start, equity.index[-1]),
            note,
        )
        add_result(
            f"S2_同区间_{name.split('_')[0]}",
            name.split("_")[0],
            s2.equity,
            s2.execution_weights,
            start,
            equity.index[-1],
            note="冻结 S2 同区间对照",
        )
    return pd.DataFrame(rows)


def period_table(result: ResearchResult) -> pd.DataFrame:
    rows = []
    for name, start, end in PERIODS:
        window = result.equity.loc[start:end]
        metrics = period_metrics(
            result.equity, result.execution_weights, window.index[0], window.index[-1]
        )
        rows.append(
            {
                "period": name.replace("（伪样本外）", ""),
                "start": window.index[0].date().isoformat(),
                "end": window.index[-1].date().isoformat(),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def cost_table(
    prices: pd.DataFrame,
    config: MultiAssetTrendConfig,
    evaluation_start: pd.Timestamp,
) -> pd.DataFrame:
    rows = []
    for bps in COST_BPS:
        result = run_s2(prices, config, total_cost_bps=bps, metric_start=evaluation_start)
        rows.append(
            {
                "total_per_side_bps": bps,
                **{
                    name: result.metrics[name]
                    for name in (
                        "cagr",
                        "max_drawdown",
                        "sharpe",
                        "calmar",
                        "turnover",
                        "trade_count",
                        "average_holding_days",
                    )
                },
            }
        )
    return pd.DataFrame(rows)


def trading_effort(
    result: ResearchResult, targets: pd.DataFrame, evaluation_start: pd.Timestamp
) -> dict[str, float]:
    executions = result.execution_weights.dropna(how="all").loc[evaluation_start:]
    orders = result.portfolio.orders.records_readable
    orders = orders.loc[orders["Timestamp"] >= evaluation_start]
    order_counts = orders.groupby("Timestamp").size().reindex(executions.index, fill_value=0)
    elapsed_years = (executions.index[-1] - executions.index[0]).days / 365.25
    target_changes = targets.diff().abs().fillna(targets.abs()).gt(1e-12).sum(axis=1)
    return {
        "annualized_rebalance_count": len(executions) / elapsed_years,
        "annualized_action_months": int(order_counts.gt(0).sum()) / elapsed_years,
        "asset_level_order_count": float(len(orders)),
        "framework_trade_count": result.metrics["trade_count"],
        "turnover": result.metrics["turnover"],
        "average_holding_days": result.metrics["average_holding_days"],
        "months_without_actual_orders": float(order_counts.eq(0).sum()),
        "months_without_target_change": float(target_changes.eq(0).sum()),
        "average_changed_positions_per_rebalance": float(order_counts.mean()),
        "maximum_changed_positions_one_rebalance": float(order_counts.max()),
    }


def failure_mode(
    prices: pd.DataFrame,
    config: MultiAssetTrendConfig,
    targets: pd.DataFrame,
    s2: ResearchResult,
) -> dict[str, Any]:
    moving_average = (
        prices[list(config.risk_symbols)]
        .rolling(config.trend_window, min_periods=config.trend_window)
        .mean()
    )
    signal_dates = targets.loc["2015-01-01":"2016-03-31"].index
    below_dates = {}
    unavailable_dates = {}
    for symbol in ("510300.SS", "510500.SS"):
        valid = moving_average.loc[signal_dates, symbol].notna()
        below = signal_dates[
            valid & (prices.loc[signal_dates, symbol] <= moving_average.loc[signal_dates, symbol])
        ]
        below_dates[symbol] = below[0].date().isoformat() if len(below) else "未触发"
        unavailable = signal_dates[~valid]
        unavailable_dates[symbol] = (
            unavailable[0].date().isoformat() if len(unavailable) else "始终可用"
        )
    start = pd.Timestamp("2015-06-12")
    end = pd.Timestamp("2016-01-28")
    s2_metrics = period_metrics(s2.equity, s2.execution_weights, start, end)
    s1 = run_vectorbt(
        load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv"),
        load_strategy_config(ROOT / "config/strategy.toml"),
    )
    s1_metrics = period_metrics(s1.equity, s1.execution_weights, start, end)
    episode = targets.loc[start:end, ["510300.SS", "510500.SS", config.fallback_symbol]]
    return {
        "510300_below_date": below_dates["510300.SS"],
        "510500_below_date": below_dates["510500.SS"],
        "510300_unavailable_date": unavailable_dates["510300.SS"],
        "510500_unavailable_date": unavailable_dates["510500.SS"],
        "first_defensive_weight": float(episode[config.fallback_symbol].iloc[0]),
        "maximum_defensive_weight": float(episode[config.fallback_symbol].max()),
        "s2_episode_max_drawdown": s2_metrics["max_drawdown"],
        "s1_episode_max_drawdown": s1_metrics["max_drawdown"],
        "s2_episode_return": float(s2.equity.loc[end] / s2.equity.loc[start] - 1),
        "s1_episode_return": float(s1.equity.loc[end] / s1.equity.loc[start] - 1),
    }


def universe_evidence(
    prices: pd.DataFrame, config: MultiAssetTrendConfig, targets: pd.DataFrame
) -> dict[str, Any]:
    moving_average = (
        prices[list(config.risk_symbols)]
        .rolling(config.trend_window, min_periods=config.trend_window)
        .mean()
    )
    year_ends = moving_average.groupby(moving_average.index.year).tail(1)
    counts = year_ends.notna().sum(axis=1)
    counts.index = counts.index.year
    late = {}
    for symbol in ("513520.SS", "159980.SZ"):
        eligible_signals = targets.index[
            targets.index >= moving_average[symbol].first_valid_index()
        ]
        held = targets.loc[eligible_signals, symbol].gt(0).sum()
        late[symbol] = {
            "first_eligible": moving_average[symbol].first_valid_index().date().isoformat(),
            "held_months": int(held),
            "eligible_months": len(eligible_signals),
        }
    return {"annual_eligible_counts": counts.to_dict(), "late_assets": late}


def _table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.select_dtypes(include="number"):
        display[column] = display[column].map(lambda value: f"{value:.4f}")
    return display.to_markdown(index=False)


def build_report(
    s2: ResearchResult,
    benchmarks: pd.DataFrame,
    periods: pd.DataFrame,
    annual: pd.Series,
    rolling: pd.DataFrame,
    costs: pd.DataFrame,
    effort: dict[str, float],
    failure: dict[str, Any],
    universe: dict[str, Any],
) -> str:
    rolling_summary = rolling.groupby("window_years").agg(
        cagr_min=("cagr", "min"),
        cagr_median=("cagr", "median"),
        cagr_max=("cagr", "max"),
        sharpe_min=("sharpe", "min"),
        maxdd_worst=("max_drawdown", "min"),
    )
    annual_frame = annual.rename("return").reset_index()
    s1_row = benchmarks.loc[benchmarks["series"].eq("S1_拒绝基线_同区间")].iloc[0]
    s2_b4_row = benchmarks.loc[benchmarks["series"].eq("S2_同区间_B4")].iloc[0]
    drawdowns = s2.portfolio.drawdowns.records_readable.copy()
    drawdowns["drawdown"] = drawdowns["Valley Value"] / drawdowns["Peak Value"] - 1
    worst_drawdown = drawdowns.sort_values("drawdown").iloc[0]
    counts = ", ".join(
        f"{year}:{count}" for year, count in universe["annual_eligible_counts"].items()
    )
    late = universe["late_assets"]
    decision = "REJECT_S2"
    return f"""# S2 多资产趋势基线经济筛选 V1

## 执行结论

冻结的 200 日独立趋势基线将最大回撤从 S1 同区间的 {s1_row["max_drawdown"]:.2%} 降至 {s2.metrics["max_drawdown"]:.2%}，Sharpe 从 {s1_row["sharpe"]:.3f} 提高到 {s2.metrics["sharpe"]:.3f}。在股债金共同区间，S2 CAGR {s2_b4_row["cagr"]:.2%}、最大回撤 {s2_b4_row["max_drawdown"]:.2%}，也具备竞争力。但 2015 年对 510500.SS 的提前退出实际由缺失数据导致“不可用”，不能归功于趋势；实际订单又几乎每月发生，每次平均涉及 {effort["average_changed_positions_per_rebalance"]:.2f} 个标的。关键改善证据受数据可用性混杂，且操作负担不符合低触达目标，因此最终决策为 **{decision}**。

## 策略规则

每月末用连续 200 个交易日均有效的收盘价计算简单移动平均。每只有完整历史的风险资产拥有 `1 / 当期合格资产数` 的独立 sleeve；价格高于均线时持有该风险资产，否则把该 sleeve 配给 511010.SS。无横截面排名、Top-K、波动率配置或杠杆。月末产生信号，下一交易日执行。总单边成本基线为 15 bps。

## 完整样本指标

| 指标 | 结果 |
| --- | ---: |
| CAGR | {s2.metrics["cagr"]:.2%} |
| 最大回撤 | {s2.metrics["max_drawdown"]:.2%} |
| Sharpe | {s2.metrics["sharpe"]:.3f} |
| Calmar | {s2.metrics["calmar"]:.3f} |
| 最差年度 | {annual.min():.2%} |
| 累计单边换手 | {s2.metrics["turnover"]:.2f} |
| VectorBT 交易记录 | {s2.metrics["trade_count"]:.0f} |
| 平均持有期 | {s2.metrics["average_holding_days"]:.1f} 天 |

## 基准比较

{_table(benchmarks, ["series", "evaluation_start", "evaluation_end", "cagr", "max_drawdown", "sharpe", "calmar", "worst_year", "turnover"])}

所有较晚上市的基准均从共同有行情的日期开始，并用同区间 S2 对照；没有回填不存在的 ETF 历史。S2 明显优于被拒绝的 S1 的回撤和风险调整表现，但没有形成对静态多资产配置的一致优势。

## 2015–2016 失败机制对照

510300.SS 在 {failure["510300_below_date"]} 月末跌破均线，并于下一交易日退出。510500.SS 并未在暴跌前给出可计算的负趋势：canonical 数据在 2015-04-13/14 缺失，使其从 {failure["510500_unavailable_date"]} 到 2016-01-29 都没有完整 200 日窗口；恢复可计算后到 {failure["510500_below_date"]} 才确认低于均线。按照冻结规则，它是“不可用”而非“负趋势”，因此提前移除不能归功于趋势过滤。该阶段防御权重从 {failure["first_defensive_weight"]:.0%} 上升至最高 {failure["maximum_defensive_weight"]:.0%}。2015-06-12 至 2016-01-28，S1 收益 {failure["s1_episode_return"]:.2%}、最大回撤 {failure["s1_episode_max_drawdown"]:.2%}；S2 收益 {failure["s2_episode_return"]:.2%}、最大回撤 {failure["s2_episode_max_drawdown"]:.2%}。S2 确实降低损失，但核心对照受到缺失数据可用性规则的重大混杂，不能作为纯趋势假设的干净证据。

## 时间与滚动稳定性

{_table(periods, ["period", "start", "end", "cagr", "max_drawdown", "sharpe", "calmar", "turnover"])}

{_table(annual_frame, ["year", "return"])}

滚动汇总：

{_table(rolling_summary.reset_index(), list(rolling_summary.reset_index().columns))}

2013 和 2026 是不完整年度。3 年滚动 CAGR 最低仍为 {rolling_summary.loc[3, "cagr_min"]:.2%}，5 年最低为 {rolling_summary.loc[5, "cagr_min"]:.2%}，说明除初期外时间稳定性较好；滚动结果只用于判断经济失效，不用于选择更好均线参数。

## 成本敏感性

{_table(costs, ["total_per_side_bps", "cagr", "max_drawdown", "sharpe", "calmar", "turnover"])}

成本全部通过 VectorBT 原生 `fees` 参数实现，未编写成本模拟器。50 bps 下 CAGR 仍为 {costs.loc[costs["total_per_side_bps"].eq(50), "cagr"].iloc[0]:.2%}，成本削弱但未单独否定策略。

## 用户交易负担

- 年化计划调仓次数：{effort["annualized_rebalance_count"]:.1f}；
- 年化实际需要操作月份：{effort["annualized_action_months"]:.1f}；
- 资产级订单数：{effort["asset_level_order_count"]:.0f}，VectorBT 交易记录数：{effort["framework_trade_count"]:.0f}；
- 无实际订单月份：{effort["months_without_actual_orders"]:.0f}；目标完全不变月份：{effort["months_without_target_change"]:.0f}；
- 每次计划调仓平均涉及 {effort["average_changed_positions_per_rebalance"]:.2f} 个订单，单月最多 {effort["maximum_changed_positions_one_rebalance"]:.0f} 个；
- 平均持有期：{effort["average_holding_days"]:.1f} 天，累计单边换手：{effort["turnover"]:.2f}。

人类含义是：虽然信号为月频且单项持有期较长，但组合漂移再平衡使用户几乎每月都要处理约 6 个标的，并非低触达策略。

## Universe 偏差

状态保持 **BIAS_NOT_FULLY_RESOLVED**。年度末具备 200 日均线的风险资产数为：{counts}。完整样本最大回撤始于 {pd.Timestamp(worst_drawdown["Start Timestamp"]).date()}、谷底为 {pd.Timestamp(worst_drawdown["Valley Timestamp"]).date()}；当时仅 510300.SS 具备趋势历史并获得 100% sleeve，因此早期并不是真正多资产分散。513520.SS 自 {late["513520.SS"]["first_eligible"]} 可用后，在 {late["513520.SS"]["eligible_months"]} 个合格月份中持有 {late["513520.SS"]["held_months"]} 个月；159980.SZ 自 {late["159980.SZ"]["first_eligible"]} 可用后，在 {late["159980.SZ"]["eligible_months"]} 个合格月份中持有 {late["159980.SZ"]["held_months"]} 个月。晚加入资产实质参与后期结果，本轮没有 PIT ETF master，无法排除事后选择和幸存者偏差。

## 框架复用与局限

VectorBT 负责目标百分比订单、组合价值、费用、订单、交易和 drawdown records；S1 有界脚本的分期、滚动和静态基准函数被直接复用。新增的本地代码只生成 S2 趋势状态、sleeve 目标和本次报告。保留本地 CAGR/Sharpe 年化，是因为交易日索引直接声明 `freq=1D` 时 VectorBT 默认日历日年化与项目 252 交易日口径不一致。

本结果不证明生产可交易性、真正样本外有效性、PIT universe 无偏性或其他均线窗口稳健性；也没有实现 RQAlpha S2、波动率目标、S3 或实时系统。

## 架构漂移审计

- 是否复制 VectorBT 功能：否，组合、费用、订单、交易和回撤均由 VectorBT 提供；
- 是否复制 RQAlpha 功能：否，本轮没有实现 RQAlpha S2 或替代其职责；
- 是否无阻塞地编写通用基础设施：否，只抽出两个真实策略完全相同的目标权重执行函数；
- 是否创建策略框架：否，S2 是单一具体模块，没有基类、注册表或插件；
- 是否引入新数据抽象：否，直接复用现有 canonical 数据；
- S1 结果是否意外改变：否，真实数据回归测试逐项匹配冻结 JSON；
- 基础设施复杂度是否增长快于研究能力：否，新增代码直接产生 S2 决策证据。

## 下一步与最终决定

不要为了通过筛选而搜索均线窗口，也不要自动增加波动率配置。下一项候选可单独评估 S3 中国行业/主题轮动，但必须由新的 Goal 批准。

{decision}
"""


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_trend_config(ROOT / "config/strategy.toml")
    assert_frozen_baseline(config)
    targets = build_strict_month_end_targets(prices, config)
    executions = build_execution_weights(prices, targets)
    first_execution = executions.dropna(how="all").index[0]
    first_location = prices.index.get_loc(first_execution)
    evaluation_start = prices.index[max(first_location - 1, 0)]
    s2 = run_s2(prices, config, metric_start=evaluation_start)
    benchmarks = benchmark_table(prices, s2, config, evaluation_start)
    periods = period_table(s2)
    annual = annual_returns(s2.equity.loc[evaluation_start:])
    rolling = rolling_table(s2)
    costs = cost_table(prices, config, evaluation_start)
    effort = trading_effort(s2, targets, evaluation_start)
    failure = failure_mode(prices, config, targets, s2)
    universe = universe_evidence(prices, config, targets)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "s2_benchmark_comparison.csv": benchmarks,
        "s2_period_performance.csv": periods,
        "s2_annual_returns.csv": annual.rename("return").reset_index(),
        "s2_cost_sensitivity.csv": costs,
        "s2_rolling_performance.csv": rolling,
    }
    for filename, frame in outputs.items():
        frame.to_csv(
            args.output_dir / filename, index=False, float_format="%.8f", lineterminator="\n"
        )
    report = build_report(
        s2, benchmarks, periods, annual, rolling, costs, effort, failure, universe
    )
    (args.output_dir / "S2_BASELINE_ECONOMIC_SCREEN_V1.md").write_text(report, encoding="utf-8")
    print(f"指标区间: {evaluation_start.date()} 至 {prices.index[-1].date()}")
    print(f"S2 CAGR: {s2.metrics['cagr']:.6f}")
    print(f"S2 最大回撤: {s2.metrics['max_drawdown']:.6f}")
    print("最终决策: REJECT_S2")


if __name__ == "__main__":
    main()

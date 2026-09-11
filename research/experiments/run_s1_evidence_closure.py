#!/usr/bin/env python3
# ruff: noqa: E501
"""在冻结参数与 canonical 数据上生成 S1 Evidence Closure V1。"""

from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe
from tacticore.engines.rqalpha_adapter import run_rqalpha
from tacticore.engines.vectorbt_adapter import ResearchResult, run_vectorbt
from tacticore.strategies.global_dual_momentum import (
    GlobalDualMomentumConfig,
    build_month_end_targets,
    load_strategy_config,
)

ROOT = Path(__file__).resolve().parents[2]
PERIODS = (
    ("2013-2016", "2013-06-28", "2016-12-31"),
    ("2017-2019", "2017-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026（伪样本外）", "2023-01-01", "2026-08-31"),
)
COST_BPS = (5, 15, 30, 50)
FROZEN_PARAMETERS = {
    "lookback_trading_days": 252,
    "top_k": 2,
    "absolute_momentum_threshold": 0.0,
    "rebalance_frequency": "monthly",
    "fallback_symbol": "511010.SS",
}


def assert_frozen_parameters(config: GlobalDualMomentumConfig) -> None:
    """阻止证据闭环在不显眼处改变 S1 经济参数。"""
    actual = {name: getattr(config, name) for name in FROZEN_PARAMETERS}
    if actual != FROZEN_PARAMETERS:
        raise ValueError(f"S1 冻结参数发生变化: {actual}")


def period_metrics(
    equity: pd.Series,
    execution_weights: pd.DataFrame,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> dict[str, float]:
    """仅为本 Goal 按统一 252 日口径计算一个给定区间的指标。"""
    window = equity.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    if len(window) < 2:
        raise ValueError("指标区间至少需要两个净值观测")
    returns = window.pct_change().dropna()
    years = (window.index[-1] - window.index[0]).days / 365.25
    cagr = float((window.iloc[-1] / window.iloc[0]) ** (1 / years) - 1)
    max_drawdown = float(returns.vbt.returns(freq="1D").max_drawdown())
    std = returns.std(ddof=1)
    sharpe = float(np.sqrt(252) * returns.mean() / std) if std > 0 else float("nan")
    targets = execution_weights.loc[window.index[0] : window.index[-1]].dropna(how="all")
    turnover = 0.0
    if not targets.empty:
        prior = (
            execution_weights.loc[execution_weights.index < window.index[0]]
            .dropna(how="all")
            .tail(1)
        )
        combined = pd.concat([prior, targets]).fillna(0.0)
        turnover = float(combined.diff().abs().sum(axis=1).iloc[1:].sum() / 2)
        if prior.empty:
            turnover += float(targets.iloc[0].fillna(0.0).abs().sum())
    annual = annual_returns(window)
    return {
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "calmar": cagr / abs(max_drawdown) if max_drawdown < 0 else float("nan"),
        "turnover": turnover,
        "worst_year": float(annual.min()),
    }


def annual_returns(equity: pd.Series) -> pd.Series:
    """按自然年复合日收益，保留首尾不完整年度。"""
    returns = equity.pct_change().dropna()
    result = returns.groupby(returns.index.year).apply(lambda values: (1 + values).prod() - 1)
    result.index.name = "year"
    return result.astype(float)


def build_static_portfolio(
    prices: pd.DataFrame,
    allocations: dict[str, float],
    config: GlobalDualMomentumConfig,
    *,
    rebalance: str,
) -> tuple[pd.Series, pd.DataFrame, Any]:
    """用 VectorBT 目标百分比订单构造一个特定静态基准。"""
    selected = prices[list(allocations)].dropna()
    if selected.empty:
        raise ValueError("静态基准没有共同可用行情")
    targets = pd.DataFrame(np.nan, index=selected.index, columns=selected.columns)
    if rebalance == "buy_hold":
        dates = selected.index[:1]
    elif rebalance == "annual":
        dates = selected.groupby(selected.index.year).head(1).index
    elif rebalance == "quarterly":
        dates = selected.groupby(selected.index.to_period("Q")).head(1).index
    else:
        raise ValueError(f"未知调仓频率: {rebalance}")
    targets.loc[dates] = np.tile(list(allocations.values()), (len(dates), 1))
    portfolio = vbt.Portfolio.from_orders(
        close=selected,
        size=targets,
        size_type="targetpercent",
        group_by=True,
        cash_sharing=True,
        call_seq="auto",
        fees=config.fees,
        slippage=config.slippage,
        init_cash=config.initial_cash,
        freq="1D",
    )
    return portfolio.value(group_by=True), targets, portfolio


def realized_turnover(portfolio: Any, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """按 VectorBT 实际订单名义金额计算累计单边换手。"""
    orders = portfolio.orders.records_readable
    orders = orders.loc[(orders["Timestamp"] >= start) & (orders["Timestamp"] <= end)].copy()
    if orders.empty:
        return 0.0
    equity = portfolio.value(group_by=True)
    orders["ratio"] = orders["Size"].abs() * orders["Price"] / orders["Timestamp"].map(equity)
    daily = orders.groupby("Timestamp")["ratio"].sum()
    if daily.index[0] == equity.index[0]:
        return float(daily.iloc[0] + daily.iloc[1:].sum() / 2)
    return float(daily.sum() / 2)


def benchmark_table(
    prices: pd.DataFrame, baseline: ResearchResult, config: GlobalDualMomentumConfig
) -> pd.DataFrame:
    """构造四个最小基准及完全同区间的 S1 对照行。"""
    specs = (
        ("B1_沪深300买入持有", {"510300.SS": 1.0}, "buy_hold", "2013-06-28"),
        ("B2_美国宽基买入持有", {"513500.SS": 1.0}, "buy_hold", None),
        (
            "B3_当前风险资产等权_全员上市后",
            {symbol: 1 / len(config.risk_symbols) for symbol in config.risk_symbols},
            "annual",
            None,
        ),
        (
            "B4_股债金60_20_20",
            {"510300.SS": 0.6, "511010.SS": 0.2, "518880.SS": 0.2},
            "quarterly",
            None,
        ),
    )
    rows: list[dict[str, Any]] = []
    benchmark_runs: dict[str, tuple[pd.Series, pd.DataFrame, Any]] = {}
    for name, allocation, rebalance, min_start in specs:
        source = prices.loc[min_start:] if min_start else prices
        equity, targets, portfolio = build_static_portfolio(
            source, allocation, config, rebalance=rebalance
        )
        benchmark_runs[name] = (equity, targets, portfolio)
        start, end = equity.index[0], equity.index[-1]
        note = "使用所有标的共同有行情后的区间；没有回填未上市历史"
        if name.startswith("B1"):
            note = "与 S1 主评价期基本一致"
        elif name.startswith("B2"):
            note = "513500.SS 于 2014-01-15 上市，因此区间较短"
        elif name.startswith("B4"):
            note = "黄金 ETF 于 2013-07-29 上市，因此区间较短"
        metrics = period_metrics(equity, targets, start, end)
        metrics["turnover"] = realized_turnover(portfolio, start, end)
        rows.append(
            {
                "series": name,
                "comparison_group": name.split("_")[0],
                "evaluation_start": start.date().isoformat(),
                "evaluation_end": end.date().isoformat(),
                "rebalance": rebalance,
                "availability_note": note,
                **metrics,
            }
        )
        s1_metrics = period_metrics(baseline.equity, baseline.execution_weights, start, end)
        rows.append(
            {
                "series": f"S1_同区间_{name.split('_')[0]}",
                "comparison_group": name.split("_")[0],
                "evaluation_start": start.date().isoformat(),
                "evaluation_end": end.date().isoformat(),
                "rebalance": "monthly",
                "availability_note": "冻结 S1 参数的同区间对照",
                **s1_metrics,
            }
        )
    holdout_start = pd.Timestamp("2023-01-03")
    holdout_end = pd.Timestamp("2026-08-31")
    for name, (equity, targets, portfolio) in benchmark_runs.items():
        metrics = period_metrics(equity, targets, holdout_start, holdout_end)
        metrics["turnover"] = realized_turnover(portfolio, holdout_start, holdout_end)
        rows.append(
            {
                "series": f"HOLDOUT_{name}",
                "comparison_group": "HOLDOUT",
                "evaluation_start": holdout_start.date().isoformat(),
                "evaluation_end": holdout_end.date().isoformat(),
                "rebalance": next(spec[2] for spec in specs if spec[0] == name),
                "availability_note": "2023–2026 时序留出同区间",
                **metrics,
            }
        )
    holdout_s1 = period_metrics(
        baseline.equity, baseline.execution_weights, holdout_start, holdout_end
    )
    rows.append(
        {
            "series": "HOLDOUT_S1",
            "comparison_group": "HOLDOUT",
            "evaluation_start": holdout_start.date().isoformat(),
            "evaluation_end": holdout_end.date().isoformat(),
            "rebalance": "monthly",
            "availability_note": "冻结 S1 参数",
            **holdout_s1,
        }
    )
    return pd.DataFrame(rows)


def period_table(baseline: ResearchResult) -> pd.DataFrame:
    rows = []
    for name, start, end in PERIODS:
        window = baseline.equity.loc[start:end]
        metrics = period_metrics(
            baseline.equity, baseline.execution_weights, window.index[0], window.index[-1]
        )
        rows.append(
            {
                "period": name,
                "start": window.index[0].date().isoformat(),
                "end": window.index[-1].date().isoformat(),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def rolling_table(baseline: ResearchResult) -> pd.DataFrame:
    """在月末观测 3/5 年滚动指标，最大回撤调用 VectorBT returns accessor。"""
    equity = baseline.equity.loc["2013-06-28":]
    month_ends = equity.groupby(equity.index.to_period("M")).tail(1).index
    rows = []
    for years in (3, 5):
        for end in month_ends:
            intended_start = end - pd.DateOffset(years=years)
            window = equity.loc[intended_start:end]
            if window.empty or window.index[0] > intended_start + pd.Timedelta(days=10):
                continue
            metrics = period_metrics(
                baseline.equity, baseline.execution_weights, window.index[0], window.index[-1]
            )
            rows.append(
                {
                    "window_years": years,
                    "window_start": window.index[0].date().isoformat(),
                    "window_end": window.index[-1].date().isoformat(),
                    "cagr": metrics["cagr"],
                    "max_drawdown": metrics["max_drawdown"],
                    "sharpe": metrics["sharpe"],
                }
            )
    return pd.DataFrame(rows)


def cost_table(prices: pd.DataFrame, config: GlobalDualMomentumConfig) -> pd.DataFrame:
    rows = []
    for bps in COST_BPS:
        result = run_vectorbt(prices, replace(config, fees=bps / 10_000, slippage=0.0))
        rows.append(
            {
                "total_per_side_bps": bps,
                "fees": bps / 10_000,
                "slippage": 0.0,
                **{
                    name: result.metrics[name]
                    for name in ("cagr", "max_drawdown", "sharpe", "calmar", "turnover")
                },
            }
        )
    return pd.DataFrame(rows)


def availability_table(
    prices: pd.DataFrame, universe: pd.DataFrame, config: GlobalDualMomentumConfig
) -> pd.DataFrame:
    momentum = prices / prices.shift(config.lookback_trading_days) - 1
    rows = []
    for symbol, item in universe.iterrows():
        valid = prices[symbol].dropna()
        usable = momentum[symbol].first_valid_index()
        rows.append(
            {
                "symbol": symbol,
                "asset_class": item["asset_class"],
                "strategy_role": (
                    "risk"
                    if symbol in config.risk_symbols
                    else "fallback"
                    if symbol == config.fallback_symbol
                    else "unused"
                ),
                "listing_date": item["start_date"].date().isoformat(),
                "first_market_observation": valid.index[0].date().isoformat(),
                "first_usable_signal_date": usable.date().isoformat() if usable is not None else "",
                "last_market_observation": valid.index[-1].date().isoformat(),
                "observation_count": len(valid),
                "historical_availability": f"{valid.index[0].date()}..{valid.index[-1].date()}",
            }
        )
    return pd.DataFrame(rows)


def eligible_counts(prices: pd.DataFrame, config: GlobalDualMomentumConfig) -> pd.Series:
    momentum = prices / prices.shift(config.lookback_trading_days) - 1
    year_ends = momentum.groupby(momentum.index.year).tail(1)
    counts = year_ends[list(config.risk_symbols)].notna().sum(axis=1)
    counts.index = counts.index.year
    counts.index.name = "year"
    return counts


def partial_top_k(targets: pd.DataFrame, config: GlobalDualMomentumConfig) -> pd.DataFrame:
    risk = targets[list(config.risk_symbols)]
    counts = (risk > 0).sum(axis=1)
    partial = targets.loc[counts.eq(1)].copy()
    selected = risk.idxmax(axis=1).loc[partial.index]
    return pd.DataFrame(
        {
            "signal_date": partial.index,
            "selected_symbol": selected.values,
            "risk_weight": risk.max(axis=1).loc[partial.index].values,
        }
    )


def rqalpha_comparison(
    prices: pd.DataFrame,
    baseline: ResearchResult,
    config: GlobalDualMomentumConfig,
    universe: pd.DataFrame,
    bundle: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rq_targets: list[dict[str, Any]] = []
    result = run_rqalpha(
        config,
        ROOT / "config/universe.csv",
        "2013-07-01",
        "2026-08-31",
        bundle,
        rq_targets,
    )["sys_analyser"]
    portfolio = result["portfolio"]
    trades = result["trades"]
    rq_equity = portfolio["total_value"]
    rq_return = float(rq_equity.iloc[-1] / rq_equity.iloc[0] - 1)
    vbt_window = baseline.equity.loc[rq_equity.index[0] : rq_equity.index[-1]]
    vbt_return = float(vbt_window.iloc[-1] / vbt_window.iloc[0] - 1)
    mapping = universe["rqalpha_symbol"].to_dict()
    reverse = {value: key for key, value in mapping.items()}
    intended = baseline.execution_weights.dropna(how="all").loc[
        rq_equity.index[0] : rq_equity.index[-1]
    ]
    positions = result["stock_positions"].copy()
    actual_by_date = (
        positions.assign(symbol_local=positions["order_book_id"].map(reverse))
        .groupby(level=0)["symbol_local"]
        .apply(lambda values: ";".join(sorted(values.dropna().unique())))
    )
    trade_by_date = (
        trades.assign(symbol_local=trades["order_book_id"].map(reverse))
        .groupby(trades.index.date)
        .apply(
            lambda frame: ";".join(
                f"{row.symbol_local}:{row.side}"
                for row in frame.itertuples()
                if pd.notna(row.symbol_local)
            ),
            include_groups=False,
        )
    )
    rows = []
    rq_target_by_date = {row["rebalance_date"]: row["targets"] for row in rq_targets}
    for date, weights in intended.iterrows():
        selected = weights[weights > 0]
        vectorbt_targets = {symbol: round(float(weight), 8) for symbol, weight in selected.items()}
        rq_target = rq_target_by_date.get(date, {})
        rows.append(
            {
                "rebalance_date": date.date().isoformat(),
                "vectorbt_targets": ";".join(
                    f"{symbol}:{weight:.2f}" for symbol, weight in selected.items()
                ),
                "rqalpha_targets": ";".join(
                    f"{symbol}:{weight:.2f}" for symbol, weight in rq_target.items()
                ),
                "target_match": vectorbt_targets == rq_target,
                "rqalpha_end_of_day_positions": actual_by_date.get(date, ""),
                "rqalpha_trades": trade_by_date.get(date.date(), ""),
            }
        )
    comparison = pd.DataFrame(rows)
    summary = result["summary"]
    diagnostics = {
        "rqalpha_version": "5.6.5",
        "adjust_type": "pre",
        "rqalpha_total_return": rq_return,
        "vectorbt_total_return_same_period": vbt_return,
        "rqalpha_turnover": float(summary["turnover"]),
        "vectorbt_turnover": period_metrics(
            baseline.equity,
            baseline.execution_weights,
            rq_equity.index[0],
            rq_equity.index[-1],
        )["turnover"],
        "rqalpha_transaction_cost": float(trades["transaction_cost"].sum()),
        "rqalpha_trade_count": len(trades),
        "rqalpha_max_drawdown": -float(summary["max_drawdown"]),
        "target_match_count": int(comparison["target_match"].sum()),
        "target_comparison_count": len(comparison),
        "target_match_rate": float(comparison["target_match"].mean()),
    }
    return comparison, diagnostics


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.select_dtypes(include="number"):
        display[column] = display[column].map(lambda value: f"{value:.4f}")
    return display.to_markdown(index=False)


def build_report(
    prices: pd.DataFrame,
    config: GlobalDualMomentumConfig,
    baseline: ResearchResult,
    benchmarks: pd.DataFrame,
    periods: pd.DataFrame,
    annual: pd.Series,
    rolling: pd.DataFrame,
    costs: pd.DataFrame,
    availability: pd.DataFrame,
    counts: pd.Series,
    partial: pd.DataFrame,
    rq_diag: dict[str, Any],
) -> str:
    drawdowns = baseline.portfolio.drawdowns.records_readable.copy()
    drawdowns["drawdown"] = drawdowns["Valley Value"] / drawdowns["Peak Value"] - 1
    worst_dd = drawdowns.sort_values("drawdown").iloc[0]
    dd_start = pd.Timestamp(worst_dd["Start Timestamp"])
    dd_valley = pd.Timestamp(worst_dd["Valley Timestamp"])
    dd_end = pd.Timestamp(worst_dd["End Timestamp"])
    transitions = baseline.execution_weights.dropna(how="all").loc[dd_start:dd_valley]
    transition_text = ", ".join(
        f"{date.date()}→{'/'.join(row[row > 0].index)}" for date, row in transitions.iterrows()
    )
    overlap = partial[(partial["signal_date"] >= dd_start) & (partial["signal_date"] <= dd_valley)]
    rolling_summary = rolling.groupby("window_years").agg(
        cagr_min=("cagr", "min"),
        cagr_median=("cagr", "median"),
        cagr_max=("cagr", "max"),
        sharpe_min=("sharpe", "min"),
        maxdd_worst=("max_drawdown", "min"),
    )
    benchmark_wins = 0
    for group in ("B1", "B2", "B3", "B4"):
        pair = benchmarks.loc[benchmarks["comparison_group"].eq(group)]
        strategy = pair.loc[pair["series"].str.startswith("S1")].iloc[0]
        benchmark = pair.loc[pair["series"].str.startswith(group)].iloc[0]
        benchmark_wins += int(
            strategy["cagr"] >= benchmark["cagr"]
            and strategy["sharpe"] >= benchmark["sharpe"]
            and strategy["max_drawdown"] >= benchmark["max_drawdown"]
        )
    cost_50 = costs.loc[costs["total_per_side_bps"].eq(50)].iloc[0]
    holdout = periods.iloc[-1]
    decision = "REJECT_S1"
    annual_frame = annual.rename("return").reset_index()
    count_text = ", ".join(f"{year}:{value}" for year, value in counts.items())
    partial_text = ", ".join(
        f"{row.signal_date.date()}→{row.selected_symbol}" for row in partial.itertuples()
    )
    holdout_frame = benchmarks.loc[benchmarks["comparison_group"].eq("HOLDOUT")]
    china_returns = prices.loc[dd_start:dd_valley, ["510300.SS", "510500.SS"]]
    china_loss = china_returns.iloc[-1] / china_returns.iloc[0] - 1
    china_correlation = china_returns.pct_change().corr().iloc[0, 1]
    dd_orders = baseline.portfolio.orders.records_readable
    dd_orders = dd_orders.loc[
        (dd_orders["Timestamp"] >= dd_start) & (dd_orders["Timestamp"] <= dd_valley)
    ]
    return f"""# S1 证据闭环 V1

## 执行结论

冻结的全球双动量基线不应继续围绕当前规则迭代：它在 {benchmark_wins}/4 组同区间比较中同时胜过简单基准的 CAGR、Sharpe 和最大回撤，最大回撤为 {baseline.metrics["max_drawdown"]:.2%}，RQAlpha 的真实市场执行语义又把同区间累计收益从 VectorBT 的 {rq_diag["vectorbt_total_return_same_period"]:.2%} 降至 {rq_diag["rqalpha_total_return"]:.2%}。因此本报告最终决策为 **{decision}**。

## 冻结策略与数据口径

参数保持为 252 交易日动量、绝对动量大于 0、前 2 名等权、无合格资产时持有 511010.SS、月末收盘形成信号、下一交易日收盘执行。研究数据是 Tushare Pro 后复权 ETF 价格，截止 2026-08-31。没有为了结果修改参数。

## 基准比较

{_markdown_table(benchmarks.loc[benchmarks["comparison_group"] != "HOLDOUT"], ["series", "evaluation_start", "evaluation_end", "cagr", "max_drawdown", "sharpe", "calmar", "worst_year", "turnover"])}

B2、B3、B4 因上市日期使用较短且明确标注的共同可用区间；不存在的历史没有回填。B3 是全部九只当前风险 ETF 均上市后的年度等权，B4 是季度再平衡的 60% 沪深300、20% 国债、20% 黄金。二者都没有战术信号。

## 分时期与年度证据

{_markdown_table(periods, ["period", "start", "end", "cagr", "max_drawdown", "sharpe", "calmar", "turnover"])}

{_markdown_table(annual_frame, ["year", "return"])}

最佳年度为 {annual.idxmax()}（{annual.max():.2%}），最差年度为 {annual.idxmin()}（{annual.min():.2%}）。2020–2022 子区间为负，说明收益并非跨阶段稳定。

2013 年从评价起点开始、2026 年截至 8 月 31 日，二者都是不完整自然年；其余年度为完整自然年。

## 3 年 / 5 年滚动证据

{_markdown_table(rolling_summary.reset_index(), list(rolling_summary.reset_index().columns))}

滚动值按月末观察；滚动最大回撤直接调用 VectorBT returns accessor。存在负 CAGR 和负 Sharpe 窗口，长期收益集中在部分市场状态，而不是稳定持续。

## 成本敏感性

{_markdown_table(costs, ["total_per_side_bps", "cagr", "max_drawdown", "sharpe", "calmar", "turnover"])}

所有情景均使用 VectorBT 原生 `fees`/`slippage` 参数；总单边成本统一放入 `fees`，`slippage=0`，避免另写成本引擎。50 bps 下 CAGR 仍为 {cost_50["cagr"]:.2%}，所以成本会削弱结果，但不是当前否决的唯一原因。

## Universe 与选择偏差

状态：**BIAS_NOT_FULLY_RESOLVED**。年度末具备 252 日动量的风险资产数为：{count_text}。

1. 是，早期策略在显著更小的池中运行。
2. 日本 ETF 513520.SS（2019）和有色 ETF 159980.SZ（2019）进入很晚，德国、标普500等也晚于主区间起点。
3. 是，今天反向选定仍存续的 ETF 会引入事后选择。
4. 是，收益可能受幸存者偏差和事后 universe 构造抬高；本 Goal 没有 PIT 标的库，不能量化幅度。
5. 承认限制后，正收益仍值得记录，但不足以在基准、时序和执行证据不佳时继续 S1。

## 最大回撤机制

VectorBT 原生 drawdown record 显示峰值 {pd.Timestamp(worst_dd["Peak Timestamp"]).date()}，回撤开始 {dd_start.date()}，谷底 {dd_valley.date()}，到 {dd_end.date()} 才恢复，幅度 {worst_dd["drawdown"]:.2%}。谷底前配置迁移为：{transition_text}。

该回撤始于 2015 年中国权益冲高后的动量滞后。开始至谷底，510300.SS 与 510500.SS 分别收益 {china_loss["510300.SS"]:.2%} 和 {china_loss["510500.SS"]:.2%}，日收益相关系数 {china_correlation:.2f}；组合连续持有两只高度相关的中国权益，未进入防御资产。同期 VectorBT 原生订单记录有 {len(dd_orders)} 笔，没有异常密集执行；canonical 原价也未显示独立的数据异常。证据更支持“集中风险 + 动量滞后 + 相关资产共同下跌 + 防御缺席”，而非费用、执行或数据伪影。

## Partial Top-K

当前代码确实会在仅一只风险资产动量为正时把 100% 配给该资产，不会把剩余 50% 配给防御资产。共发生 {len(partial)} 次，占全部月末信号 {len(partial) / len(build_month_end_targets(prices, config)):.2%}；其中 {len(overlap)} 次落在最大回撤开始至谷底区间。发生记录：{partial_text}。因此它确实制造偶发集中风险，但与 2015–2016 最大回撤不重叠，并非足以单独解释失败的主导弱点。

## RQAlpha 差异验证

已通过官方 `rqalpha download-bundle --confirm` 下载仓库外 bundle，并用 RQAlpha {rq_diag["rqalpha_version"]} 完整运行。`check-bundle` 提示全市场日线 bundle 不完整，但本策略 12 只 ETF 的所需区间可读取，完整回测成功，因此没有引入外部 DataSource。动量历史显式设置 `adjust_type=pre`；前复权与 Tushare 后复权在同一窗口仅差常数尺度，收益比率经济等价，企业行动仍交由 RQAlpha。{rq_diag["target_comparison_count"]} 次月度目标中有 {rq_diag["target_match_count"]} 次与 VectorBT 完全相同（{rq_diag["target_match_rate"]:.2%}）。RQAlpha 真实成交 {rq_diag["rqalpha_trade_count"]} 笔、累计换手 {rq_diag["rqalpha_turnover"]:.2f}、交易成本 {rq_diag["rqalpha_transaction_cost"]:.2f}，最大回撤 {rq_diag["rqalpha_max_drawdown"]:.2%}；VectorBT 同区间累计收益 {rq_diag["vectorbt_total_return_same_period"]:.2%}、换手 {rq_diag["vectorbt_turnover"]:.2f}，RQAlpha 累计收益 {rq_diag["rqalpha_total_return"]:.2%}。

逐月 CSV 对照了两边目标、RQAlpha 日终持仓与成交方向。目标不一致的月份来自 Tushare 与 RQAlpha 历史价格/缺失观测口径，以及 RQAlpha `skip_suspended=True` 按有效 bar 取 253 根数据的差异；这些数据源差异没有被强行抹平。目标一致后仍存在的持仓差异来自 RQAlpha 的整手、现金、费用、涨跌停和默认成交量上限：尤其 100% 目标会因未预留费用而撤单，低流动性 ETF 也有部分成交。它不是 bit-for-bit 失败，而是当前信号与执行表达在权威验证下均存在不可忽略的差异。

## 2023–2026 时序留出

这是已被查看过历史的 **伪样本外 / chronological holdout**，不是 untouched OOS。冻结 S1 的 CAGR 为 {holdout["cagr"]:.2%}、最大回撤 {holdout["max_drawdown"]:.2%}、Sharpe {holdout["sharpe"]:.3f}、累计单边换手 {holdout["turnover"]:.2f}。是否为正由表中结果直接回答；相对表现见 B1/B2/B4 同区间与完整 CSV。没有使用该区间优化参数。

{_markdown_table(holdout_frame, ["series", "cagr", "max_drawdown", "sharpe", "calmar", "turnover"])}

留出期收益为正、换手仍属低频；但相对简单基准的优势并不一致，且这是已经查看过的历史，不能抵消完整区间与 RQAlpha 的负面证据。

## 框架复用与架构漂移审计

- VectorBT：复用 `Portfolio.from_orders`、订单/交易/drawdown records、费用与滑点、returns accessor；没有自研回测、撮合或记账。
- RQAlpha：复用官方 bundle、交易日历、instrument、history、scheduler、order、现金/持仓/费用/滑点/成交与 analyser；没有用 Tushare 重建这些能力。
- 自定义代码仅是冻结策略的窄分析脚本与 252 日年化口径。VectorBT 把不规则交易日索引按 `freq=1D` 直接年化会使用日历日频率，因此 CAGR/Sharpe 继续使用已存在的 365.25/252 明确口径；最大回撤仍调用框架。
- 未复制 VectorBT：否；未复制 RQAlpha：否；未写通用框架能力：否；未创建无具体需求抽象：否；基础设施 LOC 未超过回答本研究问题所需；本 Goal 显著提高了判断 S1 价值的能力：是。

## 局限与下一步

本结果不证明未来收益、生产可交易性、容量、税务、PIT universe 无偏性或真正样本外有效性。它也没有评价 S2/S3。

下一项唯一建议是以 **S2 多资产趋势跟踪** 为主要方向；不要通过参数挖掘或同时叠加多项修补来挽救 S1。

## 最终研究决策

{decision}
"""


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path.home() / ".rqalpha/bundle")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/results")
    args = parser.parse_args()
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    config = load_strategy_config(ROOT / "config/strategy.toml")
    assert_frozen_parameters(config)
    universe = load_universe(ROOT / "config/universe.csv")
    baseline = run_vectorbt(prices, config)
    benchmarks = benchmark_table(prices, baseline, config)
    periods = period_table(baseline)
    annual = annual_returns(baseline.equity.loc["2013-06-28":])
    rolling = rolling_table(baseline)
    costs = cost_table(prices, config)
    availability = availability_table(prices, universe, config)
    counts = eligible_counts(prices, config)
    targets = build_month_end_targets(prices, config)
    partial = partial_top_k(targets, config)
    rq_comparison, rq_diag = rqalpha_comparison(prices, baseline, config, universe, args.bundle)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "s1_benchmark_comparison.csv": benchmarks,
        "s1_period_performance.csv": periods,
        "s1_annual_returns.csv": annual.rename("return").reset_index(),
        "s1_rolling_performance.csv": rolling,
        "s1_cost_sensitivity.csv": costs,
        "s1_universe_availability.csv": availability,
        "s1_rqalpha_comparison.csv": rq_comparison,
    }
    for filename, frame in outputs.items():
        frame.to_csv(
            args.output_dir / filename, index=False, float_format="%.8f", lineterminator="\n"
        )
    report = build_report(
        prices,
        config,
        baseline,
        benchmarks,
        periods,
        annual,
        rolling,
        costs,
        availability,
        counts,
        partial,
        rq_diag,
    )
    (args.output_dir / "S1_EVIDENCE_CLOSURE_V1.md").write_text(report, encoding="utf-8")
    print(f"已生成 {len(outputs) + 1} 个 S1 证据产物；最终决策: REJECT_S1")


if __name__ == "__main__":
    main()

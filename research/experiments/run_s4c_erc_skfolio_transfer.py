#!/usr/bin/env python3
# ruff: noqa: E501
"""使用 skfolio 官方 RiskBudgeting 进行预注册 S4C ERC transfer。"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from research.experiments.batch_01_common import metric_row, row
from tacticore.data.prices import load_price_csv
from tacticore.data.tradability import load_tradability_inputs
from tacticore.engines.vectorbt_adapter import run_target_weights
from tacticore.strategies.multi_asset_trend import build_execution_weights, load_trend_config

ROOT = Path(__file__).resolve().parents[2]
WINDOW = 61
MIN_ELIGIBLE = 6


class SolverFailure(RuntimeError):
    """符合数据覆盖条件但官方上游无法产生合法权重。"""


@dataclass(frozen=True)
class S4CConfig:
    fallback_symbol: str
    fees: float = 0.001
    slippage: float = 0.0005
    initial_cash: float = 1_000_000.0


def aligned_window(prices: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """返回截至信号日、所有候选资产共同可见的最后 61 个价格。"""
    candidates = prices.loc[:date].columns[prices.loc[date].notna()]
    available = [
        symbol for symbol in candidates if prices.loc[:date, symbol].notna().sum() >= WINDOW
    ]
    if len(available) < MIN_ELIGIBLE:
        return pd.DataFrame()
    return prices.loc[:date, available].dropna(how="any").tail(WINDOW)


def erc_weights(returns: pd.DataFrame) -> pd.Series:
    """唯一优化调用：官方 long-only variance equal-risk-budget API。"""
    from skfolio import RiskMeasure
    from skfolio.optimization import RiskBudgeting

    model = RiskBudgeting(risk_measure=RiskMeasure.VARIANCE, min_weights=0.0, max_weights=1.0)
    try:
        model.fit(returns)
    except Exception as error:
        raise SolverFailure(f"skfolio RiskBudgeting failed: {error}") from error
    weights = pd.Series(model.weights_, index=returns.columns, dtype=float)
    if (
        not np.isfinite(weights).all()
        or (weights < -1e-12).any()
        or not np.isclose(weights.sum(), 1.0)
    ):
        raise SolverFailure("skfolio RiskBudgeting returned invalid weights")
    return weights.clip(lower=0.0) / weights.clip(lower=0.0).sum()


def build_targets(
    prices: pd.DataFrame, risk_symbols: tuple[str, ...], config: S4CConfig
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    risk = prices.loc[:, list(risk_symbols)]
    ends = prices.groupby(pd.DatetimeIndex(prices.index).to_period("M")).tail(1).index
    erc = pd.DataFrame(0.0, index=ends, columns=prices.columns)
    equal = erc.copy()
    inverse = erc.copy()
    diagnostics: list[dict[str, object]] = []
    for date in ends:
        window = aligned_window(risk, date)
        if len(window) != WINDOW:
            for frame in (erc, equal, inverse):
                frame.loc[date, config.fallback_symbol] = 1.0
            diagnostics.append(
                {"signal_date": date, "eligible_asset_count": 0, "regime": "FALLBACK"}
            )
            continue
        returns = window.pct_change(fill_method=None).dropna(how="any")
        if len(returns) != WINDOW - 1 or len(returns.columns) < MIN_ELIGIBLE:
            raise SolverFailure("aligned 61 prices did not yield 60 valid returns")
        weights = erc_weights(returns)
        volatility = returns.std(ddof=1)
        if (volatility <= 0).any() or not np.isfinite(volatility).all():
            raise SolverFailure("aligned inverse-vol comparator has invalid volatility")
        erc.loc[date, weights.index] = weights
        equal.loc[date, weights.index] = 1.0 / len(weights)
        raw = 1.0 / volatility
        inverse.loc[date, weights.index] = raw / raw.sum()
        diagnostics.append(
            {
                "signal_date": date,
                "eligible_asset_count": len(weights),
                "regime": "RISK",
                "maximum_weight": float(weights.max()),
                "effective_number_assets": float(1.0 / (weights**2).sum()),
            }
        )
    return erc, equal, inverse, pd.DataFrame(diagnostics).set_index("signal_date")


def decision(comparison: pd.DataFrame, diagnostics: pd.DataFrame) -> str:
    if diagnostics.eligible_asset_count.ge(MIN_ELIGIBLE).mean() < 0.80:
        return "BLOCK_S4C_DATA_COVERAGE"
    candidate = row(comparison, "S4C_CANONICAL_ERC_SKFOLIO_TRANSFER_V1")
    comparator = row(comparison, "SAME_ELIGIBLE_INVERSE_VOL")
    absolute = candidate.cagr > 0 and candidate.sharpe >= 0.50 and candidate.max_drawdown > -0.35
    relative = (
        candidate.cagr >= comparator.cagr - 0.015
        and candidate.max_drawdown >= comparator.max_drawdown - 0.02
        and (
            candidate.sharpe >= comparator.sharpe + 0.03
            or candidate.calmar >= comparator.calmar + 0.05
        )
        and candidate.turnover <= 1.5 * comparator.turnover
    )
    return (
        "ADVANCE_S4C_ERC_TRANSFER_TO_ROBUSTNESS"
        if absolute and relative
        else "DO_NOT_ADVANCE_S4C_ERC_TRANSFER"
    )


def main() -> None:
    strategy = load_trend_config(ROOT / "config/strategy.toml")
    config = S4CConfig(
        strategy.fallback_symbol, strategy.fees, strategy.slippage, strategy.initial_cash
    )
    prices = load_price_csv(ROOT / "data/canonical/etf_adjusted_close.csv")
    tradability_mask, lifetimes = load_tradability_inputs(prices, str(ROOT / "config/universe.csv"))
    try:
        erc, equal, inverse, diagnostics = build_targets(prices, strategy.risk_symbols, config)
    except SolverFailure as error:
        print(f"decision=BLOCK_S4C_UPSTREAM_EXECUTION\nreason={error}")
        return
    execution = [build_execution_weights(prices, targets) for targets in (erc, equal, inverse)]
    start = execution[0].dropna(how="all").index[0]
    common = dict(
        fees=config.fees,
        slippage=config.slippage,
        initial_cash=config.initial_cash,
        metric_start=start,
    )
    results = [
        run_target_weights(prices, weights, **common, tradability_mask=tradability_mask, lifetimes=lifetimes)
        for weights in execution
    ]
    comparison = pd.DataFrame(
        [
            metric_row("S4C_CANONICAL_ERC_SKFOLIO_TRANSFER_V1", results[0], start),
            metric_row("SAME_ELIGIBLE_EQUAL_WEIGHT", results[1], start),
            metric_row("SAME_ELIGIBLE_INVERSE_VOL", results[2], start),
        ]
    )
    active = diagnostics.loc[diagnostics.index >= start]
    outcome = decision(comparison, active)
    concentration = active.loc[
        active.regime.eq("RISK"), ["maximum_weight", "effective_number_assets"]
    ]
    summary = pd.DataFrame(
        [
            {
                "median_maximum_weight": concentration.maximum_weight.median(),
                "p95_maximum_weight": concentration.maximum_weight.quantile(0.95),
                "months_any_asset_gt_50pct": int(concentration.maximum_weight.gt(0.50).sum()),
                "coverage_ratio": float(active.eligible_asset_count.ge(MIN_ELIGIBLE).mean()),
            }
        ]
    )
    output = ROOT / "research/results"
    comparison.to_csv(output / "s4c_erc_skfolio_comparison_v1.csv", index=False)
    diagnostics.to_csv(output / "s4c_erc_skfolio_diagnostics_v1.csv")
    summary.to_csv(output / "s4c_erc_skfolio_concentration_v1.csv", index=False)
    print(f"decision={outcome}\n{comparison.to_csv(index=False)}\n{summary.to_csv(index=False)}")


if __name__ == "__main__":
    main()

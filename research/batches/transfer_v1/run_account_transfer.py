"""ACCOUNT_INVESTABLE_ALLOCATION_TRANSFER_V1 A0/A2 研究执行器。

用法（真实运行必须显式给出研究快照与本地 bundle；本模块不联网）：

    python -m research.batches.transfer_v1.run_account_transfer \
        --prices data/transfer_v1/<snapshot>/etf_adjusted_close.csv \
        --calendar data/transfer_v1/<snapshot>/trading_calendar.csv \
        --bundle ~/.rqalpha/bundle

本模块不实现撮合或组合会计：目标日程交给现有
`replay_frozen_schedule`，成交、现金、整手、滑点、费用和持仓全部由
RQAlpha 原生承担。这里只做四件事：生成/校准冻结日程、读取原生结果、
计算协议 §6 指标、按预注册门槛裁决。

裁决默认是 `INCONCLUSIVE`：只有在协议已提交（调用方显式
`--protocol-committed`）、最低佣金已建模、数据/整手门控通过且日程收敛时才可
产生 REJECT / ADOPT_SHADOW。任何结果都不得被写成生产批准。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

try:  # 既支持 pytest 从批次目录导入，也支持 `python -m ...`
    from .account_transfer_policy import (
        FROZEN_CONFIG,
        ORDER_BUY,
        ORDER_SELL,
        PROTOCOL_STATUS,
        ActualState,
        PolicyError,
        TransferConfig,
        build_schedule,
        build_trend_path,
        month_end_dates,
        target_path,
    )
except ImportError:  # pragma: no cover - 脚本直接运行路径
    from account_transfer_policy import (  # type: ignore[no-redef]
        FROZEN_CONFIG,
        ORDER_BUY,
        ORDER_SELL,
        PROTOCOL_STATUS,
        ActualState,
        PolicyError,
        TransferConfig,
        build_schedule,
        build_trend_path,
        month_end_dates,
        target_path,
    )

from research.ashare.engines.rqalpha_replay import (
    RQAlphaRunResult,
    actual_weights,
    replay_frozen_schedule,
)
from tacticore.data.prices import load_price_csv

CANONICAL_DIR = Path(__file__).resolve().parents[3] / "data" / "canonical"
RISK_IMPROVEMENT_FLOOR = 0.02
CAGR_LOSS_CEILING = 0.005
TURNOVER_RATIO_CEILING = 1.5


@dataclass(frozen=True)
class ArmMetrics:
    arm: str
    cagr: float | None
    max_drawdown: float | None
    cvar_5pct: float | None
    cvar_observations: int
    turnover_total: float | None
    turnover_annualized: float | None
    mean_equity: float | None
    initial_equity: float | None
    ending_equity: float | None
    trade_count: int
    commission: float
    order_passes: int
    order_rejections: int
    cash_rejections: int
    lot_rejections: int
    volume_rejections: int
    other_rejections: int
    filtered_below_one_lot: int
    filtered_below_min_buy: int
    filtered_other: int

    @property
    def cvar_5pct_points(self) -> float | None:
        return None if self.cvar_5pct is None else self.cvar_5pct * 100.0


@dataclass(frozen=True)
class Adjudication:
    verdict: str
    blockers: tuple[str, ...]
    checks: Mapping[str, bool | None]
    risk_improvement_mdd: float | None
    risk_improvement_cvar: float | None
    cagr_loss: float | None
    turnover_ratio: float | None


@dataclass(frozen=True)
class ArmRun:
    arm: str
    schedule: pd.DataFrame
    result: RQAlphaRunResult
    actual_states: Mapping[pd.Timestamp, ActualState]
    orders: pd.DataFrame
    passes: int
    converged: bool
    metrics: ArmMetrics | None = None
    min_commission: float | None = None


def _equity(result: RQAlphaRunResult) -> pd.Series:
    portfolio = result.analyser.get("portfolio")
    if portfolio is None or "total_value" not in portfolio.columns:
        raise PolicyError("RQAlpha 结果缺少 portfolio.total_value")
    equity = pd.to_numeric(portfolio["total_value"], errors="coerce").dropna()
    equity.index = pd.to_datetime(equity.index)
    if equity.empty:
        raise PolicyError("RQAlpha 权益序列为空")
    return equity.sort_index()


def metrics_from_result(result: RQAlphaRunResult, orders: pd.DataFrame, arm: str) -> ArmMetrics:
    """按协议 §6 从 RQAlpha 原生结果计算指标；不重建净值。"""
    equity = _equity(result)
    initial_equity, ending_equity = float(equity.iloc[0]), float(equity.iloc[-1])
    days = int((equity.index[-1] - equity.index[0]).days)
    cagr = (
        (ending_equity / initial_equity) ** (365.25 / days) - 1.0
        if days > 0 and initial_equity > 0 and ending_equity > 0
        else None
    )
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = -float(drawdown.min()) if not drawdown.empty else None
    returns = equity.pct_change(fill_method=None).dropna()
    cvar_5pct: float | None = None
    cvar_observations = int(len(returns))
    if cvar_observations:
        worst_count = max(1, math.ceil(0.05 * cvar_observations))
        cvar_5pct = float((-returns).nlargest(worst_count).mean())
    mean_equity = float(equity.mean()) if not equity.empty else None

    trades = result.analyser.get("trades")
    if trades is None:
        trades = pd.DataFrame()
    notional = 0.0
    commission = 0.0
    if not trades.empty:
        quantities = pd.to_numeric(trades["last_quantity"], errors="coerce").fillna(0.0)
        prices = pd.to_numeric(trades["last_price"], errors="coerce").fillna(0.0)
        notional = float((quantities * prices).abs().sum())
        if "commission" in trades.columns:
            commission_values = pd.to_numeric(trades["commission"], errors="coerce")
            commission = float(commission_values.fillna(0.0).sum())
    turnover_total = notional / mean_equity if mean_equity and mean_equity > 0 else None
    years = days / 365.25 if days > 0 else None
    turnover_annualized = (
        turnover_total / years if turnover_total is not None and years and years > 0 else None
    )

    events = result.order_events
    if events is None or events.empty:
        events = pd.DataFrame(columns=["event", "order_id", "message"])
    rejected = events.loc[events["event"].eq("ORDER_CREATION_REJECT")].copy()
    messages = rejected["message"].fillna("").astype(str)
    cash_mask = messages.str.contains("not enough money", case=False, regex=False)
    lot_mask = messages.str.contains("0 order quantity", case=False, regex=False)
    volume_mask = messages.str.contains("current bar volume", case=False, regex=False)
    other_mask = ~(cash_mask | lot_mask | volume_mask)
    passed = events.loc[events["event"].eq("ORDER_CREATION_PASS")]
    order_passes = int(passed["order_id"].nunique()) if not passed.empty else 0
    filtered = orders.loc[~orders["submitted"]] if not orders.empty else orders
    reasons = filtered["reason"] if not filtered.empty else pd.Series(dtype=str)
    return ArmMetrics(
        arm=arm,
        cagr=cagr,
        max_drawdown=max_drawdown,
        cvar_5pct=cvar_5pct,
        cvar_observations=cvar_observations,
        turnover_total=turnover_total,
        turnover_annualized=turnover_annualized,
        mean_equity=mean_equity,
        initial_equity=initial_equity,
        ending_equity=ending_equity,
        trade_count=int(len(trades)),
        commission=commission,
        order_passes=order_passes,
        order_rejections=int(len(rejected)),
        cash_rejections=int(cash_mask.sum()),
        lot_rejections=int(lot_mask.sum()),
        volume_rejections=int(volume_mask.sum()),
        other_rejections=int(other_mask.sum()),
        filtered_below_one_lot=int(reasons.eq("below_one_lot").sum()),
        filtered_below_min_buy=int(reasons.eq("below_min_buy").sum()),
        filtered_other=int((~reasons.isin(["below_one_lot", "below_min_buy"])).sum()),
    )


def adjudicate(
    a0: ArmMetrics,
    a2: ArmMetrics,
    *,
    protocol_committed: bool,
    min_commission_modelled: bool,
    data_gate_passed: bool,
    fixed_point_converged: bool,
    samples_aligned: bool,
    allocation_executed: bool = True,
    other_rejections_explained: bool = False,
) -> Adjudication:
    """三选一结论：ADOPT_SHADOW / REJECT / INCONCLUSIVE。

    前置门控任何一项未闭合都返回 INCONCLUSIVE；只有前置全部有效时，
    A2 任一门槛失败才是 REJECT。默认调用方把协议状态和最低佣金都标为
    未闭合，因此本执行器不会声称通过。
    """
    required = ("cagr", "max_drawdown", "cvar_5pct", "turnover_total")
    metrics_complete = all(
        getattr(metrics, field) is not None for metrics in (a0, a2) for field in required
    )
    risk_mdd = (
        a0.max_drawdown - a2.max_drawdown
        if a0.max_drawdown is not None and a2.max_drawdown is not None
        else None
    )
    risk_cvar = (
        a0.cvar_5pct - a2.cvar_5pct
        if a0.cvar_5pct is not None and a2.cvar_5pct is not None
        else None
    )
    cagr_loss = a0.cagr - a2.cagr if a0.cagr is not None and a2.cagr is not None else None
    turnover_ratio = (
        a2.turnover_total / a0.turnover_total
        if a2.turnover_total is not None and a0.turnover_total is not None and a0.turnover_total > 0
        else None
    )
    risk_condition = (
        max(value for value in (risk_mdd, risk_cvar) if value is not None) >= RISK_IMPROVEMENT_FLOOR
        if risk_mdd is not None or risk_cvar is not None
        else None
    )
    cagr_condition = cagr_loss <= CAGR_LOSS_CEILING if cagr_loss is not None else None
    turnover_condition = (
        turnover_ratio <= TURNOVER_RATIO_CEILING if turnover_ratio is not None else None
    )
    rejection_condition = a2.cash_rejections == 0 and a2.lot_rejections == 0
    blockers: list[str] = []
    if not protocol_committed:
        blockers.append("PROTOCOL_NOT_COMMITTED")
    if not min_commission_modelled:
        blockers.append("MIN_COMMISSION_NOT_MODELLED")
    if not data_gate_passed:
        blockers.append("PIT_OR_DATA_GATE_NOT_CLOSED")
    if not fixed_point_converged:
        blockers.append("BAND_FEEDBACK_NOT_CONVERGED")
    if not samples_aligned:
        blockers.append("SAMPLES_NOT_ALIGNED")
    if not allocation_executed:
        blockers.append("ALLOCATION_NOT_EXECUTED")
    if not metrics_complete:
        blockers.append("METRICS_INCOMPLETE")
    if turnover_ratio is None:
        blockers.append("TURNOVER_RATIO_UNDEFINED")
    if a2.other_rejections and not other_rejections_explained:
        blockers.append("OTHER_REJECTIONS_UNEXPLAINED")
    checks = {
        "metrics_complete": metrics_complete,
        "risk_improvement_ge_2pp": risk_condition,
        "cagr_loss_le_0_5pp": cagr_condition,
        "turnover_ratio_le_1_5x": turnover_condition,
        "zero_cash_and_lot_rejections": rejection_condition,
        "other_rejections_explained": (a2.other_rejections == 0 or other_rejections_explained),
    }
    if blockers:
        return Adjudication(
            "INCONCLUSIVE", tuple(blockers), checks, risk_mdd, risk_cvar, cagr_loss, turnover_ratio
        )
    if not rejection_condition or not all(
        value is True for value in (risk_condition, cagr_condition, turnover_condition)
    ):
        return Adjudication("REJECT", (), checks, risk_mdd, risk_cvar, cagr_loss, turnover_ratio)
    return Adjudication("ADOPT_SHADOW", (), checks, risk_mdd, risk_cvar, cagr_loss, turnover_ratio)


def actual_states_from_result(
    result: RQAlphaRunResult, decisions: pd.DatetimeIndex, config: TransferConfig
) -> dict[pd.Timestamp, ActualState]:
    """读取决策日收盘的 RQAlpha 原生持仓、数量与总权益。"""
    reverse = {asset.rqalpha_symbol: asset.symbol for asset in config.assets}
    weights = actual_weights(result, local_symbols=list(config.symbols), reverse_mapping=reverse)
    portfolio = result.analyser.get("portfolio")
    positions = result.analyser.get("stock_positions")
    if portfolio is None or "total_value" not in portfolio.columns:
        raise PolicyError("RQAlpha 结果缺少 portfolio")
    portfolio = portfolio.copy()
    portfolio.index = pd.to_datetime(portfolio.index)
    if positions is not None and not positions.empty:
        positions = positions.copy()
        positions.index = pd.to_datetime(positions.index)
    states: dict[pd.Timestamp, ActualState] = {}
    for raw_date in decisions:
        date = pd.Timestamp(raw_date).normalize()
        if date not in portfolio.index:
            raise PolicyError(f"RQAlpha 权益缺少决策日: {date.date()}")
        equity = float(portfolio.at[date, "total_value"])
        weight_row = weights.loc[date] if date in weights.index else pd.Series(dtype=float)
        quantities: dict[str, int] = {}
        if positions is not None and date in positions.index and not positions.empty:
            day = positions.loc[[date]]
            for asset in config.assets:
                selected = day.loc[day["order_book_id"].eq(asset.rqalpha_symbol), "quantity"]
                quantities[asset.symbol] = int(
                    pd.to_numeric(selected, errors="coerce").fillna(0).sum()
                )
        states[date] = ActualState(
            weights={symbol: float(weight_row.get(symbol, 0.0)) for symbol in config.symbols},
            quantities={symbol: quantities.get(symbol, 0) for symbol in config.symbols},
            equity=equity,
        )
    return states


def _desired_targets(
    arm: str, prices: pd.DataFrame, decisions: pd.DatetimeIndex, config: TransferConfig
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    if arm == "A0":
        return target_path(decisions, config, confirmed=None), None
    if arm == "A2":
        _, confirmed = build_trend_path(prices, decisions, config)
        return target_path(decisions, config, confirmed=confirmed), confirmed
    raise PolicyError(f"未知研究臂: {arm}")


def replay_mapping(config: TransferConfig) -> dict[tuple[str, str], str]:
    return {
        (side, asset.symbol): asset.rqalpha_symbol
        for asset in config.assets
        for side in (ORDER_SELL, ORDER_BUY)
    }


def calibrate_arm(
    arm: str,
    *,
    prices: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    decisions: pd.DatetimeIndex,
    config: TransferConfig,
    bundle_path: str | Path,
    max_passes: int = 4,
) -> ArmRun:
    """用冻结日程回放校准偏离带所需的实际持仓。

    首次回放只使用首月建仓（后续月份假定目标已达成）；之后每一轮都用
    上一轮 RQAlpha 原生持仓生成下一版日程。日程稳定后才算收敛；未收敛
    的结果仍保留，但裁决必须是 INCONCLUSIVE。所有成交/现金/整手/费用
    仍只由 RQAlpha 计算，本函数不重建任何账户。
    """
    targets, trend_sides = _desired_targets(arm, prices, decisions, config)
    mapping = replay_mapping(config)
    actual_states: Mapping[pd.Timestamp, ActualState] | None = None
    previous: pd.DataFrame | None = None
    final: ArmRun | None = None
    for pass_number in range(1, max_passes + 1):
        schedule, orders = build_schedule(
            prices=prices,
            calendar=calendar,
            decisions=decisions,
            targets=targets,
            config=config,
            actual_states=actual_states,
            trend_sides=trend_sides,
            arm=arm,
        )
        if schedule.empty or int(schedule.notna().to_numpy().sum()) == 0:
            raise PolicyError(f"{arm} 冻结日程没有任何可执行订单")
        result = replay_frozen_schedule(
            schedule,
            mapping,
            start=config.main_start,
            end=config.main_end,
            initial_cash=config.initial_cash,
            bundle_path=bundle_path,
            min_commission=5.0,
        )
        states = actual_states_from_result(result, decisions, config)
        converged = previous is not None and previous.equals(schedule)
        final = ArmRun(
            arm=arm,
            schedule=schedule,
            result=result,
            actual_states=states,
            orders=orders,
            passes=pass_number,
            converged=converged,
            min_commission=result.min_commission,
        )
        if converged:
            return final
        previous, actual_states = schedule, states
    assert final is not None
    return final


def _samples_aligned(a0: ArmRun, a2: ArmRun) -> bool:
    """配对比较只要求权益日期完全对齐；两条权益路径本就应该不同。"""
    try:
        left, right = _equity(a0.result), _equity(a2.result)
    except PolicyError:
        return False
    return left.index.equals(right.index)


def _min_commission_modelled(run: ArmRun) -> bool:
    # 覆盖层必须把 RQAlpha 6.3 实际读取的 stock_min_commission 设为 5 元。
    return run.min_commission is not None and math.isclose(
        run.min_commission, 5.0, rel_tol=0, abs_tol=1e-12
    )


def _data_gate_passed(*runs: ArmRun) -> bool:
    for run in runs:
        if run.orders.empty:
            continue
        blocked = run.orders["reason"].isin(["no_execution_price", "untradable_sell_blocked"])
        if bool(blocked.any()):
            return False
    return True


def _allocation_executed(run: ArmRun, config: TransferConfig) -> bool:
    """每个正基准袖子至少有一笔提交订单；整袖未建仓不能当作“已检验”。"""
    for asset in config.assets:
        if asset.base_weight <= 0:
            continue
        rows = run.orders.loc[run.orders["symbol"] == asset.symbol]
        if rows.empty or not bool(rows["submitted"].any()):
            return False
    return True


def run_pair(
    *,
    prices: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: TransferConfig = FROZEN_CONFIG,
    bundle_path: str | Path,
    max_passes: int = 4,
    protocol_committed: bool = False,
) -> dict[str, Any]:
    """运行 A0/A2 配对，并返回证据与裁决；默认不会声称通过。"""
    decisions = month_end_dates(calendar, config.main_start, config.main_end)
    if decisions.empty:
        raise PolicyError("主窗口内没有月末决策日")
    a0 = calibrate_arm(
        "A0",
        prices=prices,
        calendar=calendar,
        decisions=decisions,
        config=config,
        bundle_path=bundle_path,
        max_passes=max_passes,
    )
    a2 = calibrate_arm(
        "A2",
        prices=prices,
        calendar=calendar,
        decisions=decisions,
        config=config,
        bundle_path=bundle_path,
        max_passes=max_passes,
    )
    a0 = replace(a0, metrics=metrics_from_result(a0.result, a0.orders, "A0"))
    a2 = replace(a2, metrics=metrics_from_result(a2.result, a2.orders, "A2"))
    assert a0.metrics is not None and a2.metrics is not None
    aligned = _samples_aligned(a0, a2)
    allocation_executed = _allocation_executed(a0, config) and _allocation_executed(a2, config)
    adjudication = adjudicate(
        a0.metrics,
        a2.metrics,
        protocol_committed=protocol_committed,
        min_commission_modelled=_min_commission_modelled(a0) and _min_commission_modelled(a2),
        data_gate_passed=_data_gate_passed(a0, a2),
        fixed_point_converged=a0.converged and a2.converged,
        samples_aligned=aligned,
        allocation_executed=allocation_executed,
        other_rejections_explained=False,
    )
    return {
        "protocol_status": PROTOCOL_STATUS,
        "protocol_committed_claim": protocol_committed,
        "decision_scope": "研究执行器输出；不是生产批准，也不表示协议已通过。",
        "decisions": decisions,
        "A0": a0,
        "A2": a2,
        "adjudication": adjudication,
    }


def summarize(result: Mapping[str, Any]) -> dict[str, Any]:
    """把结果压成可审计 JSON；不隐藏 blockers 与未提交过滤。"""
    a0: ArmRun = result["A0"]
    a2: ArmRun = result["A2"]
    protocol = Path(__file__).with_name("PROTOCOL_V1.md")
    return {
        "protocol_status": result["protocol_status"],
        "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
        "protocol_committed_claim": result["protocol_committed_claim"],
        "decision_scope": result["decision_scope"],
        "frozen_config": {
            "initial_cash": FROZEN_CONFIG.initial_cash,
            "main_start": FROZEN_CONFIG.main_start.date().isoformat(),
            "main_end": FROZEN_CONFIG.main_end.date().isoformat(),
            "assets": [
                {
                    "symbol": asset.symbol,
                    "sleeve": asset.sleeve,
                    "base_weight": asset.base_weight,
                    "rqalpha_symbol": asset.rqalpha_symbol,
                }
                for asset in FROZEN_CONFIG.assets
            ],
            "method": "targets via frozen rules; all execution/accounting by RQAlpha",
        },
        "decision_count": int(len(result["decisions"])),
        "A0": {
            "passes": a0.passes,
            "converged": a0.converged,
            "min_commission": a0.min_commission,
            "order_rows": int(len(a0.orders)),
            "metrics": asdict(a0.metrics) if a0.metrics else None,
        },
        "A2": {
            "passes": a2.passes,
            "converged": a2.converged,
            "min_commission": a2.min_commission,
            "order_rows": int(len(a2.orders)),
            "metrics": asdict(a2.metrics) if a2.metrics else None,
        },
        "adjudication": asdict(result["adjudication"]),
    }


def load_research_snapshot(
    prices_path: str | Path, calendar_path: str | Path | None = None
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """只读 transfer_v1 快照；拒绝 canonical 目录，避免把历史基线当本研究数据。"""
    path = Path(prices_path).resolve()
    if CANONICAL_DIR.resolve() == path.parent or CANONICAL_DIR.resolve() in path.parents:
        raise PolicyError("拒绝读取 data/canonical；RL-052 只能使用 data/transfer_v1 快照")
    prices = load_price_csv(path)
    missing = set(FROZEN_CONFIG.symbols).difference(prices.columns)
    if missing:
        raise PolicyError(f"价格快照缺少冻结资产: {sorted(missing)}")
    if calendar_path is None:
        calendar = pd.DatetimeIndex(prices.index)
    else:
        frame = pd.read_csv(calendar_path, index_col="date", parse_dates=["date"])
        if "sse_open" not in frame.columns:
            raise PolicyError("交易日历缺少 sse_open 列")
        calendar = pd.DatetimeIndex(frame.index[frame["sse_open"].astype(int) == 1])
    calendar = pd.DatetimeIndex(calendar).normalize().unique().sort_values()
    if calendar.empty:
        raise PolicyError("交易日历为空")
    outside = pd.DatetimeIndex(prices.index).difference(calendar)
    if len(outside):
        raise PolicyError(f"价格日期不在交易日历中: {outside[:3].tolist()}")
    return prices, calendar


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--calendar", type=Path, default=None)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--protocol-committed", action="store_true", help="提交声明，未自动核验")
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        prices, calendar = load_research_snapshot(args.prices, args.calendar)
        result = run_pair(
            prices=prices,
            calendar=calendar,
            bundle_path=args.bundle,
            max_passes=args.max_passes,
            protocol_committed=args.protocol_committed,
        )
    except (PolicyError, FileNotFoundError, ValueError, RuntimeError) as exc:
        payload = {"decision": "INCONCLUSIVE", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    summary = summarize(result)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["adjudication"]["verdict"] != "INCONCLUSIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

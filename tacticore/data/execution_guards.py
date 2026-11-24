"""审计补充的执行期守卫：退市生命周期与不可同日清仓。

`tacticore/data/tradability.py` 的字节哈希被 S4C R1 candidate manifest 的
`frozen_identity_artifacts` 钉死，任何修改都会破坏冻结候选身份，因此这里只新增薄模块，
复用既有的 `AssetLifetime` / `build_tradability_mask` / `validate_execution_targets`，
不复制 PIT mask、生命周期或正目标校验实现。

已记录的限制：canonical 价格契约不携带停牌/涨跌停状态，mask 只能表达 lifetime 与有限正价格。
“持仓转 0 但当日不可交易”只能按 mask 判定；真实停牌/板价语义仍由 RQAlpha native /
FinanceMCP 快照拥有，本模块不猜测。当前只有 S4C 前瞻 runner 的 signal 日校验接入
delisted-aware 生命周期；“持仓转 0”对完整 execution schedule 的接入是后续项，不改写既有
冻结实验的 replay 行为。
"""

from __future__ import annotations

from collections.abc import Mapping
from numbers import Integral

import pandas as pd

from tacticore.data.tradability import (
    AssetLifetime,
    UntradableTargetError,
    build_tradability_mask,
    price_available_at,
    validate_execution_targets,
)
from tacticore.data.universe import load_universe


def _parse_delisted_date(value: object) -> pd.Timestamp:
    try:
        return pd.Timestamp(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"universe delisted_date 不可解析: {value!r}") from error


def _parse_yyyymmdd(token: int, raw: object) -> pd.Timestamp:
    try:
        parsed = pd.to_datetime(f"{token:08d}", format="%Y%m%d", errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"universe delisted_date 不可解析: {raw!r}") from error
    return pd.Timestamp(parsed)


def optional_delisted_date(value: object) -> pd.Timestamp | None:
    """universe 的可选退市日：空值与 NaT 表示未退市；非法值 fail closed。

    整数 `YYYYMMDD`（如 20240102）按显式日期格式解析，不会被当成 1970 年纳秒时间戳。
    """
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, bool):
        raise ValueError(f"universe delisted_date 不可解析: {value!r}")
    if isinstance(value, Integral):
        parsed = _parse_yyyymmdd(int(value), value)
    elif isinstance(value, float) and value.is_integer() and 10_000_000 <= value <= 99_999_999:
        parsed = _parse_yyyymmdd(int(value), value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        parsed = (
            _parse_yyyymmdd(int(text), value)
            if len(text) == 8 and text.isdigit()
            else _parse_delisted_date(text)
        )
    elif isinstance(value, float) and pd.isna(value):
        return None
    else:
        parsed = _parse_delisted_date(value)
    return None if pd.isna(parsed) else parsed.normalize()


def lifetimes_from_universe_with_delisting(universe: pd.DataFrame) -> dict[str, AssetLifetime]:
    """冻结 lifetimes 语义 + 可选 `delisted_date` 列；无该列时行为不变。"""
    has_delisted = "delisted_date" in universe.columns
    lifetimes: dict[str, AssetLifetime] = {}
    for symbol, row in universe.iterrows():
        delisted = optional_delisted_date(row["delisted_date"]) if has_delisted else None
        lifetimes[str(symbol)] = AssetLifetime(
            str(symbol), pd.Timestamp(row.start_date).normalize(), delisted
        )
    return lifetimes


def load_tradability_inputs_with_delisting(
    prices: pd.DataFrame, universe_path: str
) -> tuple[pd.DataFrame, dict[str, AssetLifetime]]:
    """与冻结 `load_tradability_inputs` 相同，但生命周期读取可选退市日。"""
    lifetimes = lifetimes_from_universe_with_delisting(load_universe(universe_path))
    return build_tradability_mask(prices.index, list(prices.columns), lifetimes, prices), lifetimes


def validate_held_liquidations(
    execution_weights: pd.DataFrame,
    prices: pd.DataFrame,
    tradability_mask: pd.DataFrame,
    lifetimes: Mapping[str, AssetLifetime],
    *,
    tolerance: float = 1e-12,
) -> None:
    """上一目标 >tolerance 的持仓转为 ~0 时，执行日必须仍可交易。

    首发日从未持有的零权重资产不受限制；NaN 表示没有 target 观测，不改变已持仓状态。
    冻结 `validate_execution_targets` 会跳过零权重，因此这是它未覆盖的补充检查。
    """
    held: set[str] = set()
    for raw_date, weights in execution_weights.dropna(how="all").iterrows():
        date = pd.Timestamp(raw_date)  # type: ignore[arg-type]
        for raw_symbol, raw_weight in weights.items():
            if pd.isna(raw_weight):
                continue
            symbol, weight = str(raw_symbol), float(raw_weight)
            lifetime = lifetimes.get(symbol)
            tradable = (
                symbol in tradability_mask.columns
                and date in tradability_mask.index
                and bool(tradability_mask.at[date, symbol])
            )
            if weight > tolerance:
                held.add(symbol)
            elif symbol in held:
                if lifetime is None or not tradable:
                    listed = lifetime.listed_date.date().isoformat() if lifetime else "UNKNOWN"
                    raise UntradableTargetError(
                        "不可交易清仓目标: "
                        f"execution_date={date.date()} symbol={symbol} "
                        f"target_weight={weight:.12g} listed_date={listed} "
                        f"price_available={price_available_at(prices, symbol, date)}"
                    )
                held.discard(symbol)


def validate_execution_targets_with_liquidations(
    execution_weights: pd.DataFrame,
    prices: pd.DataFrame,
    tradability_mask: pd.DataFrame,
    lifetimes: Mapping[str, AssetLifetime],
    *,
    tolerance: float = 1e-12,
) -> None:
    """冻结正目标校验 + 清仓日校验；不重新实现既有校验。"""
    validate_execution_targets(
        execution_weights, prices, tradability_mask, lifetimes, tolerance=tolerance
    )
    validate_held_liquidations(
        execution_weights, prices, tradability_mask, lifetimes, tolerance=tolerance
    )

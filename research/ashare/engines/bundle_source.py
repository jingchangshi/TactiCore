"""从 RQAlpha bundle 读取一个显式 universe 的价格矩阵（WP2.2）。

存在理由：做双引擎对照时，两个引擎必须看到**同一条价格序列**。若 VectorBT 读
CSV、RQAlpha 读 bundle，两边的差异就混入了"数据来源不同"这一无法归因的成分，
WP2.4 的差异审计会失去意义。因此这里以 bundle 为唯一价格来源，
VectorBT 与 RQAlpha 都消费它产出的同一张表。

只读：本模块只调用 `BaseDataSource` 的 `history_bars` / `get_instruments` /
`is_suspended`，不写 bundle、不下单、不启动 `run_func`。

复权口径：默认 `adjust_type="none"`（原始价）。RQAlpha 内部撮合用原始价，
而 VectorBT 侧若使用复权价，两边的成交价与净值都不可比。复权因子由
`bundle_ex_factor` 单独提供，需要复权口径时由调用方显式选择，
不在这里隐式决定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol

import pandas as pd

#: RQAlpha 把 bundle 里的日期存成 YYYYMMDDHHMMSS 的 int；换回日期的唯一权威是它自己的
#: 转换函数，不自己写 `%` 运算——写错了会静默错位一整天，而错位一天在 PIT 里就是泄漏。
from rqalpha.utils.datetime_func import convert_date_to_int, convert_int_to_date

#: RQAlpha 用 2999-12-31 表示"尚未退市"。这不是一个真实日期，不能当作 delisted_date。
RQALPHA_NOT_DELISTED = pd.Timestamp("2999-12-31")


#: 本模块只用到 `BaseDataSource` 的这几个方法。声明成 Protocol 而不是
#: 直接标注 `BaseDataSource`：一是 rqalpha 的类型存根不完整，二是这样"只依赖
#: 这几个方法"的边界是显式的，将来 bundle 换实现不用改调用方。
class BundleSource(Protocol):
    """读取 bundle 所需的最小接口。"""

    def get_instruments(self, id_or_syms: Any = None, types: Any = None) -> Any: ...

    def history_bars(
        self,
        instrument: Any,
        bar_count: int | None,
        frequency: str,
        fields: Any,
        dt: Any,
        skip_suspended: bool = True,
        include_now: bool = False,
        adjust_type: str = "pre",
        adjust_orig: Any = None,
    ) -> Any: ...

    def is_suspended(self, order_book_id: str, dates: Any) -> Any: ...


@dataclass(frozen=True)
class BundleSymbol:
    """一个证券在 bundle 中的身份与生命周期。"""

    order_book_id: str
    instrument_type: str
    listed_date: pd.Timestamp
    #: None 表示未退市；RQAlpha 的 2999 哨兵值已被转换为 None。
    delisted_date: pd.Timestamp | None
    round_lot: int | None
    suspended_days: tuple[pd.Timestamp, ...]


@dataclass(frozen=True)
class BundlePriceSeries:
    """bundle 价格读取结果。

    `prices` 是**未复权**收盘价；`adjust_factors` 与它同行对齐，
    缺失（该证券当时尚未上市）处为 NaN。`suspended` 是逐日停牌标记，
    与 `prices` 同形。`symbols` 是成功读到至少一根 K 线的证券，
    顺序与 `prices.columns` 一致。
    """

    prices: pd.DataFrame
    suspended: pd.DataFrame
    symbols: tuple[BundleSymbol, ...]
    notes: tuple[str, ...]


def open_bundle_source(bundle_path: str | Path) -> BundleSource:
    """以**只读**方式打开 bundle 数据源。

    不启动 `run_func`、不写任何 bundle 文件。`BaseDataSource` 的构造只读
    `*.h5` 与 `*.json`，因此整个函数是只读的。
    """
    from rqalpha.data.base_data_source import BaseDataSource

    bundle = Path(bundle_path)
    if not bundle.is_dir():
        raise FileNotFoundError(f"RQAlpha bundle 目录不存在: {bundle}")
    # `BaseDataSource.__init__` 只读 `base_config.data_bundle_path` 与
    # `base_config.future_info` 两个字段。用 SimpleNamespace 提供它们，
    # 不必为了读一个 bundle 拉起 rqalpha 的整个配置体系。
    config = SimpleNamespace(data_bundle_path=str(bundle), future_info={})
    source = BaseDataSource(config)
    # 声明成 Protocol 后仍需确认真的提供了那几个方法，否则调用时才会炸。
    for name in ("get_instruments", "history_bars", "is_suspended"):
        if not callable(getattr(source, name, None)):
            raise TypeError(f"bundle 数据源缺少方法 {name}")
    return source


def instrument_at(source: BundleSource, order_book_id: str, date: pd.Timestamp) -> Any:
    """取指定日期有效的 instrument。

    `get_instruments(id_or_syms)` 不接受日期参数，它返回该证券的**全部历史版本**
    （退市后重新上市的证券会有多条）。因此这里自己按 `[listed_date,
    de_listed_date]` 过滤，避免取到一个在 `date` 时点还不存在的版本。
    """
    candidates = list(source.get_instruments([order_book_id]))
    if not candidates:
        raise KeyError(f"bundle 中不存在 instrument: {order_book_id}")
    target = pd.Timestamp(date).normalize()
    active = [
        instrument
        for instrument in candidates
        if pd.Timestamp(instrument.listed_date).normalize() <= target
        and pd.Timestamp(instrument.de_listed_date).normalize() >= target
    ]
    if not active:
        latest = max(candidates, key=lambda item: pd.Timestamp(item.listed_date))
        raise KeyError(
            f"{order_book_id} 在 {target.date()} 没有有效版本；"
            f"最近的上市区间是 {pd.Timestamp(latest.listed_date).date()} ~ "
            f"{pd.Timestamp(latest.de_listed_date).date()}"
        )
    return active[-1]


def to_asset_lifetime(symbol: BundleSymbol, local_symbol: str) -> Any:
    """把 bundle 生命周期转换成研究侧 `AssetLifetime`。

    复用 `tacticore.data.tradability.AssetLifetime` 而不是新建类型，
    否则 mask 与 `validate_execution_targets` 会对两套生命周期各判一次。
    """
    from tacticore.data.tradability import AssetLifetime

    return AssetLifetime(
        symbol=local_symbol,
        listed_date=symbol.listed_date,
        delisted_date=symbol.delisted_date,
    )


def _normalize_delisted(value: datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value).normalize()
    return None if stamp >= RQALPHA_NOT_DELISTED else stamp


def read_bundle_symbol(
    source: BundleSource,
    order_book_id: str,
    *,
    local_symbol: str | None = None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    calendar: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, BundleSymbol, tuple[str, ...]]:
    """读一个证券在 `[start, end]` 上的原始收盘价与停牌标记。

    返回 `(frame, symbol, notes)`。`frame` 的列是 `close` 与 `suspended`，
    索引是 `calendar`（不是 bundle 自己的交易日历）——这样多个证券拼成的矩阵
    天然对齐，缺失的 (证券, 日期) 组合为 NaN。
    """
    symbol_name = local_symbol or order_book_id
    notes: list[str] = []
    instrument = instrument_at(source, order_book_id, end)
    listed = pd.Timestamp(instrument.listed_date).normalize()
    delisted = _normalize_delisted(getattr(instrument, "de_listed_date", None))

    # `fields` 必须是 None：指定字段列表时返回的记录里**没有** datetime 字段，
    # 那就无法知道每根 K 线属于哪个交易日，只能靠位置猜。取全字段再挑列。
    bars = source.history_bars(
        instrument,
        None,
        "1d",
        None,
        pd.Timestamp(end).to_pydatetime(),
        skip_suspended=True,
        include_now=True,
        adjust_type="none",
    )
    if bars is None or len(bars) == 0:
        notes.append(f"{symbol_name}: bundle 中截至 {end.date()} 无 K 线")
        empty = pd.DataFrame(index=calendar)
        return empty, _bundle_symbol(order_book_id, instrument, listed, delisted, ()), tuple(notes)

    # history_bars 返回的是**日期值**（YYYYMMDD 的 int），不是时间戳。
    bar_dates = pd.DatetimeIndex(
        [pd.Timestamp(convert_int_to_date(int(value))).normalize() for value in bars["datetime"]]
    )
    closes = pd.Series(bars["close"].astype(float), index=bar_dates)
    # 同一交易日出现多条（理论上不应发生）时保留最后一条，并显式记录。
    if closes.index.has_duplicates:
        duplicates = int(closes.index.duplicated().sum())
        notes.append(f"{symbol_name}: bundle 中有 {duplicates} 个重复交易日的 K 线，保留最后一条")
        closes = closes[~closes.index.duplicated(keep="last")]
    in_window = closes.loc[(closes.index >= start) & (closes.index <= end)]
    aligned = in_window.reindex(calendar)

    if aligned.isna().any():
        missing = int(aligned.isna().sum())
        notes.append(
            f"{symbol_name}: 交易日历中有 {missing} 个交易日在 bundle 无收盘价"
            "（未上市、停牌或 bundle 缺口），已置为 NaN 并交给 mask 判定"
        )

    suspend_dates = tuple(
        pd.Timestamp(convert_int_to_date(int(value))).normalize()
        for value in _suspended_ints(source, order_book_id, calendar)
    )
    suspended = pd.Series(False, index=calendar)
    if suspend_dates:
        present = [date for date in suspend_dates if date in suspended.index]
        suspended.loc[present] = True
        notes.append(f"{symbol_name}: bundle 记录 {len(present)} 个停牌日，已标记为不可交易")

    frame = pd.DataFrame({"close": aligned, "suspended": suspended}, index=calendar)
    symbol = _bundle_symbol(order_book_id, instrument, listed, delisted, suspend_dates)
    return frame, symbol, tuple(notes)


def _bundle_symbol(
    order_book_id: str,
    instrument: Any,
    listed: pd.Timestamp,
    delisted: pd.Timestamp | None,
    suspend_dates: tuple[pd.Timestamp, ...],
) -> BundleSymbol:
    return BundleSymbol(
        order_book_id=order_book_id,
        instrument_type=str(getattr(instrument, "type", "")),
        listed_date=listed,
        delisted_date=delisted,
        round_lot=getattr(instrument, "round_lot", None),
        suspended_days=suspend_dates,
    )


def _suspended_ints(
    source: BundleSource, order_book_id: str, calendar: pd.DatetimeIndex
) -> list[int]:
    """bundle 的停牌日集合，以原始 int 日期返回。

    `is_suspended` 需要 `DateLike` 序列；RQAlpha 内部存的是 YYYYMMDD int，
    因此这里返回 int 而不是 `pd.Timestamp`。
    """
    if not hasattr(source, "is_suspended"):
        return []
    try:
        flags = source.is_suspended(
            order_book_id, [pd.Timestamp(date).to_pydatetime() for date in calendar]
        )
    except Exception:  # noqa: BLE001 - bundle 的停牌存储可能缺文件；缺了就当没有停牌
        return []

    return [
        convert_date_to_int(pd.Timestamp(date).to_pydatetime())
        for date, flag in zip(calendar, flags, strict=True)
        if flag
    ]


def read_bundle_prices(
    source: BundleSource,
    order_book_ids: list[str] | tuple[str, ...],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    calendar: pd.DatetimeIndex | None = None,
) -> BundlePriceSeries:
    """读多个证券，拼成一张对齐的价格矩阵与同形停牌矩阵。

    `calendar` 必须显式给出。不提供默认值：交易日历是 PIT 契约的一部分，
    悄悄用一个默认历（例如 bundle 历）会让"哪些交易日存在"变成隐式决定，
    而调用方往往有自己的日历权威。没有它就是拒绝，不猜。
    """
    if not order_book_ids:
        raise ValueError("至少要读一个证券")
    if calendar is None:
        raise ValueError("必须显式提供 calendar；交易日历是 PIT 契约，不由本模块隐式决定")
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end < start:
        raise ValueError(f"结束日 {end.date()} 早于开始日 {start.date()}")

    calendar = pd.DatetimeIndex(calendar)
    calendar = calendar[(calendar >= start) & (calendar <= end)]
    if calendar.empty:
        raise ValueError(f"交易日历在 [{start.date()}, {end.date()}] 为空")

    prices = pd.DataFrame(index=calendar, columns=list(order_book_ids), dtype=float)
    suspended = pd.DataFrame(False, index=calendar, columns=list(order_book_ids))
    symbols: list[BundleSymbol] = []
    notes: list[str] = []
    for order_book_id in order_book_ids:
        frame, symbol, frame_notes = read_bundle_symbol(
            source,
            order_book_id,
            start=start,
            end=end,
            calendar=calendar,
        )
        if frame.empty:
            notes.extend(frame_notes)
            continue
        prices[order_book_id] = frame["close"]
        suspended[order_book_id] = frame["suspended"]
        symbols.append(symbol)
        notes.extend(frame_notes)

    usable = [symbol.order_book_id for symbol in symbols]
    prices = prices.loc[:, usable]
    suspended = suspended.loc[:, usable]
    if prices.empty or prices.columns.empty:
        raise ValueError("没有任何证券读到 K 线；无法构造价格矩阵")
    if prices.isna().all().all():
        raise ValueError("价格矩阵全部为 NaN；bundle 在该区间没有数据")

    return BundlePriceSeries(
        prices=prices,
        suspended=suspended,
        symbols=tuple(symbols),
        notes=tuple(notes),
    )


def bundle_calendar(
    source: BundleSource, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DatetimeIndex:
    """从 bundle 自身读交易日历，不依赖外部日历文件。

    以 `510300.XSHG` 为锚：它是 A 股持续上市最久的 ETF 之一，若它都缺K线，
    说明区间本身超出 bundle 覆盖，应该报错而不是静默返回空历。
    """
    anchor = "510300.XSHG"
    try:
        instrument = instrument_at(source, anchor, end)
    except KeyError as error:
        raise ValueError(f"无法用 {anchor} 推导交易日历: {error}") from error
    bars = source.history_bars(
        instrument,
        None,
        "1d",
        ["datetime"],
        pd.Timestamp(end).to_pydatetime(),
        skip_suspended=False,
        include_now=True,
        adjust_type="none",
    )
    if bars is None or len(bars) == 0:
        raise ValueError("bundle 中没有可推导交易日历的 K 线")
    dates = pd.DatetimeIndex(
        [pd.Timestamp(convert_int_to_date(int(value))).normalize() for value in bars["datetime"]]
    )
    lower, upper = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    dates = dates[(dates >= lower) & (dates <= upper)]
    if dates.empty:
        raise ValueError(f"bundle 交易日历在 [{start.date()}, {end.date()}] 为空")
    return dates


__all__ = [
    "BundlePriceSeries",
    "BundleSymbol",
    "RQALPHA_NOT_DELISTED",
    "bundle_calendar",
    "instrument_at",
    "open_bundle_source",
    "read_bundle_prices",
    "read_bundle_symbol",
    "to_asset_lifetime",
]

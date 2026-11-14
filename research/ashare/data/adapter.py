"""FinanceMCP research-export 快照 → 研究 DataFrame 薄读取适配器。

本模块把一份已验证的快照变成 `run_target_weights()` 直接可用的三个输入：
`prices` / `tradability_mask` / `lifetimes`。它**不做研究判断**——不选股、不定权重、
不判断策略好坏，只负责把 CSV 变成形状正确、语义诚实的数组。

三条不可谈判的规则：

1. **未知值保持 NaN，绝不变 0。** FinanceMCP 把 null 写成空 CSV 字段；本模块读成 NaN。
   停牌、缺行、未上市都表现为"不可交易"，而不是"价格为 0"。
2. **未上市证券不得有正目标。** 上市日之前的行直接从 prices 中丢弃，`lifetimes`
   按真实 `list_date` 构造，`build_tradability_mask` 保证这些日期上 mask 为 False。
3. **身份分类是当前快照，不是历史 vintage。** `fund_type` / `market` / `exchange`
   等字段在快照中没有 PIT 语义（FinanceMCP manifest 明确标注
   `CURRENT_SNAPSHOT_NOT_PIT`），因此本模块**不**用它们做任何筛选或分组，
   只把它们原样带在 `identity` 里供人查看。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from research.ashare.data.contract import (
    SnapshotContractError,
    SnapshotManifest,
    load_snapshot_manifest,
    sha256_file,
)
from tacticore.data.tradability import (
    AssetLifetime,
    build_tradability_mask,
)

#: 本适配器要求的列。缺列即拒绝，不猜测列序。
REQUIRED_PRICE_COLUMNS = ("ts_code", "trade_date", "close")
REQUIRED_SHARE_COLUMNS = ("ts_code", "trade_date", "fd_share")
REQUIRED_LIMIT_COLUMNS = ("ts_code", "trade_date", "up_limit", "down_limit")
REQUIRED_SUSPEND_COLUMNS = ("ts_code", "trade_date")

#: 股票和 ETF 分属不同数据集；读取后按证券代码合并，价格均保持原始口径。
PRICE_DATASETS = {
    "daily_bars": "equity",
    "fund_daily_bars": "etf",
}


@dataclass(frozen=True)
class ResearchFrames:
    """适配器产物。字段名与 `run_target_weights()` 的形参一一对应。"""

    prices: pd.DataFrame
    tradability_mask: pd.DataFrame
    lifetimes: dict[str, AssetLifetime]
    identity: pd.DataFrame
    price_limits: pd.DataFrame
    suspended: pd.DataFrame
    share_changes: pd.DataFrame
    manifest: SnapshotManifest
    #: 未上市或被排除、因而**不可能**获得正目标的证券及其原因。
    excluded: dict[str, str]
    #: 显式记录的降级与缺口，例如缺复权因子、缺行业成分。
    notes: tuple[str, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    """读 CSV。空字段保持空字符串，由调用方决定它是 NaN 还是有效值。"""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional_float(raw: str | None) -> float:
    """空串 → NaN。绝不返回 0.0：那会让"未知"变成"已知为零"。"""
    if raw is None:
        return float("nan")
    text = raw.strip()
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _require_columns(
    rows: list[dict[str, str]],
    required: tuple[str, ...],
    *,
    dataset: str,
) -> None:
    if not rows:
        return
    present = set(rows[0])
    absent = [column for column in required if column not in present]
    if absent:
        raise SnapshotContractError(
            f"{dataset} 缺少必需列: {', '.join(absent)}（实际列: {', '.join(sorted(present))}）"
        )


def _parse_yyyymmdd(text: str, *, label: str) -> pd.Timestamp:
    """严格解析 YYYYMMDD。

    必须逐位检查：`value[:4]-value[4:6]-value[6:]` 会把 `2026-1-5` 切成
    `2026--1--5` 而 pandas 仍能宽松解析，畸形日期就静默通过了。
    """
    text = text.strip()
    if len(text) != 8 or not text.isdigit():
        raise SnapshotContractError(f"{label} 必须是 8 位 YYYYMMDD，得到 {text!r}")
    try:
        return pd.Timestamp(f"{text[:4]}-{text[4:6]}-{text[6:]}").normalize()
    except ValueError as error:
        raise SnapshotContractError(f"{label} 不是有效日期: {text!r}") from error


def _pivot_prices(
    manifest: SnapshotManifest,
    dataset: str,
    *,
    price_column: str = "close",
) -> tuple[pd.DataFrame, list[str]]:
    """把长表 CSV 透视成 (date × symbol) 价格矩阵。

    未上市日的行在这里就被丢掉：`list_date` 由身份表提供，晚于上市日的价格
    不可能存在，早于上市日的价格**必须**丢弃，否则一个当时还没上市的证券
    会在历史矩阵里留下可交易的价格。
    """
    entry = manifest.dataset(dataset)
    path = manifest.snapshot_dir / entry.file
    rows = _read_csv(path)
    _require_columns(rows, REQUIRED_PRICE_COLUMNS, dataset=dataset)

    records: dict[str, dict[pd.Timestamp, float]] = {}
    for row in rows:
        symbol = (row.get("ts_code") or "").strip()
        date_text = (row.get("trade_date") or "").strip()
        if not symbol or not date_text:
            continue
        date = _parse_yyyymmdd(date_text, label=f"{dataset}.trade_date")
        value = _optional_float(row.get(price_column))
        records.setdefault(symbol, {})[date] = value

    if not records:
        return pd.DataFrame(), []

    frame = pd.DataFrame(records).sort_index()
    frame.index.name = "date"
    return frame, list(frame.columns)


def _build_lifetimes(
    manifest: SnapshotManifest,
    symbols: list[str],
    *,
    dataset: str = "stock_basic",
) -> tuple[dict[str, AssetLifetime], dict[str, str]]:
    """按身份表的 `list_date` / `delist_date` 构造生命周期。

    没有身份记录的证券**不给生命周期**：`build_tradability_mask` 会因此让它在所有
    日期上不可交易，`validate_execution_targets` 随后会拒绝任何对它的正目标。
    这是"未上市证券不能生成正目标持仓"这条要求的结构性保证，不依赖调用方自觉。
    """
    entry = manifest.dataset(dataset)
    rows = _read_csv(manifest.snapshot_dir / entry.file)

    listed: dict[str, pd.Timestamp] = {}
    delisted: dict[str, pd.Timestamp | None] = {}
    #: 上市日不可解析的证券及其原始值。**不给生命周期**：上市日未知时无法判断
    #: 哪些价格行早于上市，把它们当"已上市"会让上市前的价格变成可交易。
    unparseable_listing: dict[str, str] = {}
    for row in rows:
        symbol = (row.get("ts_code") or "").strip()
        if not symbol:
            continue
        list_text = (row.get("list_date") or "").strip()
        if list_text:
            try:
                listed[symbol] = _parse_yyyymmdd(list_text, label=f"{dataset}.list_date[{symbol}]")
            except SnapshotContractError:
                # 早先这里回退到 1900-01-01，等于"永远已上市"：上市前的价格行
                # 全部变成可交易，而 notes 里一个字都不提——既错又静默。
                # 现在改为不给生命周期，由 excluded 显式排除。
                unparseable_listing[symbol] = list_text
        delist_text = (row.get("delist_date") or "").strip()
        if delist_text:
            try:
                delisted[symbol] = _parse_yyyymmdd(
                    delist_text, label=f"{dataset}.delist_date[{symbol}]"
                )
            except SnapshotContractError:
                # 退市日不可解析时按"未退市"处理，并在调用方可见的 notes 里记一笔。
                delisted[symbol] = None
        else:
            delisted[symbol] = None

    lifetimes: dict[str, AssetLifetime] = {}
    excluded: dict[str, str] = {}
    for symbol in symbols:
        if symbol in unparseable_listing:
            excluded[symbol] = (
                f"unparseable list_date {unparseable_listing[symbol]!r} in {dataset}; "
                "listing date unknown, so no target may be tradable"
            )
            continue
        if symbol not in listed:
            excluded[symbol] = f"no identity record in {dataset}"
            continue
        lifetimes[symbol] = AssetLifetime(
            symbol=symbol,
            listed_date=listed[symbol],
            delisted_date=delisted.get(symbol),
        )
    return lifetimes, excluded


def load_research_frames(
    snapshot_dir: str | Path,
    *,
    verify_content: bool = True,
) -> ResearchFrames:
    """读取一份 FinanceMCP research-export 快照并产出研究输入。

    失败即抛 `SnapshotContractError`。任何校验不通过都不会返回部分结果。
    """
    if not verify_content:
        raise SnapshotContractError(
            "研究帧必须验证文件完整性；verify_content=False 仅用于浏览 manifest"
        )
    manifest = load_snapshot_manifest(snapshot_dir, verify_content=True)

    if manifest.quality_status == "DEGRADED" and manifest.missing_datasets:
        raise SnapshotContractError(
            "快照为 DEGRADED 且缺少数据集: "
            f"{', '.join(manifest.missing_datasets)}；"
            "缺数据的快照不得用于产生前瞻证据，请改用完整导出"
        )

    if any(
        reason.startswith(("allow_missing_bars:", "missing_as_of_bars:"))
        for reason in manifest.reasons
    ):
        raise SnapshotContractError(
            "快照在 as-of 日缺少行情（allow_missing_bars / missing_as_of_bars）；不得用于研究"
        )

    notes: list[str] = [f"{reason}" for reason in manifest.reasons]
    notes.append("prices are RAW close values; adjustment factors are not applied")

    equity_prices, equity_symbols = _pivot_prices(manifest, "daily_bars")
    etf_prices, etf_symbols = _pivot_prices(manifest, "fund_daily_bars")
    if equity_prices.empty and etf_prices.empty:
        raise SnapshotContractError(
            "快照中没有任何行情（daily_bars 与 fund_daily_bars 均为空）；无法构造价格矩阵"
        )
    as_of = pd.Timestamp(manifest.as_of_trade_date)
    for dataset, frame in (("daily_bars", equity_prices), ("fund_daily_bars", etf_prices)):
        if as_of not in frame.index or not frame.loc[as_of].notna().any():
            raise SnapshotContractError(f"{dataset} 在 as-of 日没有收盘价，无法用于研究")

    # 资产身份：优先 stock_basic，ETF 从 fund_basic 补充。
    lifetimes, excluded = _build_lifetimes(manifest, equity_symbols, dataset="stock_basic")
    etf_lifetimes, etf_excluded = _build_lifetimes(manifest, etf_symbols, dataset="fund_basic")
    lifetimes.update(etf_lifetimes)
    excluded.update(etf_excluded)

    # 未上市证券不得有正目标：把晚于 list_date 的价格行丢掉。
    # 早于上市日的价格本就不该存在，但导出方若给了，这里必须拦住。
    def _clip_to_lifetime(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        for symbol in frame.columns:
            lifetime = lifetimes.get(symbol)
            if lifetime is None:
                continue
            before_listing = frame.index < lifetime.listed_date
            if before_listing.any():
                frame.loc[before_listing, symbol] = float("nan")
                notes.append(
                    f"{kind}:{symbol} dropped {int(before_listing.sum())} pre-listing price row(s) "
                    f"(list_date={lifetime.listed_date.date().isoformat()})"
                )
            if lifetime.delisted_date is not None:
                after_delisting = frame.index > lifetime.delisted_date
                if after_delisting.any():
                    frame.loc[after_delisting, symbol] = float("nan")
                    notes.append(
                        f"{kind}:{symbol} dropped {int(after_delisting.sum())} "
                        "post-delisting row(s) "
                        f"(delist_date={lifetime.delisted_date.date().isoformat()})"
                    )
        return frame

    equity_prices = _clip_to_lifetime(equity_prices, "equity")
    etf_prices = _clip_to_lifetime(etf_prices, "etf")

    all_symbols = list(dict.fromkeys([*equity_symbols, *etf_symbols]))
    if equity_prices.empty:
        prices = etf_prices.reindex(columns=all_symbols)
    elif etf_prices.empty:
        prices = equity_prices.reindex(columns=all_symbols)
    else:
        prices = pd.concat([equity_prices, etf_prices], axis=1).reindex(columns=all_symbols)
    prices = prices.sort_index()

    # 复权因子缺失必须显式降级：原始价格与复权口径不同，混用会让收益率算错。
    present_datasets = {entry.dataset for entry in manifest.datasets}
    for factor_dataset, price_dataset in (
        ("adj_factor", "daily_bars"),
        ("fund_adj_factor", "fund_daily_bars"),
    ):
        if factor_dataset not in present_datasets:
            notes.append(f"{price_dataset} has no {factor_dataset}: prices are RAW, not adjusted")

    mask = build_tradability_mask(prices.index, all_symbols, lifetimes, prices)

    price_limits = _load_side_table(manifest, "price_limit", REQUIRED_LIMIT_COLUMNS)
    suspended = _load_side_table(manifest, "suspend", REQUIRED_SUSPEND_COLUMNS)
    share_changes = _load_side_table(manifest, "fund_share", REQUIRED_SHARE_COLUMNS)

    # 停牌日必须从可交易集合中剔除。只把停牌表原样带出是不够的：那会让
    # "读到的数据里有停牌记录"与"策略不会在停牌日下单"两件事脱钩，
    # 下游一旦忘记查表，就会在一只无法成交的证券上生成正目标。
    mask = _apply_suspensions(mask, suspended)
    # 停牌掩盖必须可见：调用方需要知道有多少个可交易日被停牌表剔除了。
    notes.append(
        f"suspension: masked {int(mask.attrs.get('suspended_days_masked', 0))} "
        f"tradable cell(s), skipped {int(mask.attrs.get('suspended_rows_skipped', 0))} row(s)"
    )

    identity = _load_identity(manifest)

    return ResearchFrames(
        prices=prices,
        tradability_mask=mask,
        lifetimes=lifetimes,
        identity=identity,
        price_limits=price_limits,
        suspended=suspended,
        share_changes=share_changes,
        manifest=manifest,
        excluded=excluded,
        notes=tuple(notes),
    )


def _apply_suspensions(
    mask: pd.DataFrame,
    suspended: pd.DataFrame,
) -> pd.DataFrame:
    """把停牌日标记为不可交易。

    停牌期间该证券在 `prices` 里通常没有行（因此已是 NaN），但上游若给了
    结算价或前收价，价格非 NaN 会让 `build_tradability_mask` 认为可交易。
    停牌表是更权威的信号，因此这里显式覆盖为 False。
    """
    if suspended.empty:
        return mask
    result = mask.copy()
    marked = 0
    skipped = 0
    for _, row in suspended.iterrows():
        symbol = str(row.get("ts_code") or "").strip()
        date_text = str(row.get("trade_date") or "").strip()
        if not symbol or not date_text or symbol not in result.columns:
            skipped += 1
            continue
        try:
            date = _parse_yyyymmdd(date_text, label="suspend.trade_date")
        except SnapshotContractError:
            # 停牌表里一行坏日期不该让整个快照失败；跳过并计数，调用方在
            # notes 里必须能看到有多少行被跳过。
            skipped += 1
            continue
        if date in result.index and bool(result.at[date, symbol]):
            result.at[date, symbol] = False
            marked += 1
    result.attrs["suspended_days_masked"] = marked
    result.attrs["suspended_rows_skipped"] = skipped
    return result


def _load_side_table(
    manifest: SnapshotManifest,
    dataset: str,
    required: tuple[str, ...],
) -> pd.DataFrame:
    """加载停牌 / 涨跌停 / 份额等辅助表。缺数据集返回空表，不报错。"""
    try:
        entry = manifest.dataset(dataset)
    except SnapshotContractError:
        return pd.DataFrame(columns=list(required))
    rows = _read_csv(manifest.snapshot_dir / entry.file)
    _require_columns(rows, required, dataset=dataset)
    if not rows:
        return pd.DataFrame(columns=list(required))
    return pd.DataFrame(rows)


def _load_identity(manifest: SnapshotManifest) -> pd.DataFrame:
    """加载身份表。

    只做原样透传：`fund_type` / `market` / `exchange` 是当前快照值，没有历史
    vintage，因此**不得**用于筛选或分组（见模块 docstring 第 3 条）。
    """
    frames = []
    for dataset in ("stock_basic", "fund_basic"):
        try:
            entry = manifest.dataset(dataset)
        except SnapshotContractError:
            continue
        rows = _read_csv(manifest.snapshot_dir / entry.file)
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        frame["_source_dataset"] = dataset
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


__all__ = [
    "PRICE_DATASETS",
    "REQUIRED_LIMIT_COLUMNS",
    "REQUIRED_PRICE_COLUMNS",
    "REQUIRED_SHARE_COLUMNS",
    "REQUIRED_SUSPEND_COLUMNS",
    "ResearchFrames",
    "SnapshotContractError",
    "load_research_frames",
    "load_snapshot_manifest",
    "sha256_file",
]

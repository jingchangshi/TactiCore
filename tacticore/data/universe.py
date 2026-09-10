from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "symbol",
    "tushare_symbol",
    "rqalpha_symbol",
    "asset_class",
    "region",
    "currency",
    "role",
    "data_source",
    "start_date",
}


def load_universe(path: str | Path) -> pd.DataFrame:
    """读取最小研究 universe，并验证策略依赖的字段。"""
    universe = pd.read_csv(path, parse_dates=["start_date"])
    missing = REQUIRED_COLUMNS.difference(universe.columns)
    if missing:
        raise ValueError(f"universe 缺少字段: {sorted(missing)}")
    if universe["symbol"].duplicated().any():
        raise ValueError("universe 的 symbol 必须唯一")
    if universe["tushare_symbol"].duplicated().any():
        raise ValueError("universe 的 tushare_symbol 必须唯一")
    if not universe["role"].isin(["tradable", "reference"]).all():
        raise ValueError("role 只能是 tradable 或 reference")
    return universe.set_index("symbol", drop=False)

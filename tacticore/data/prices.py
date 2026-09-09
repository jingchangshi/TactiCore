from pathlib import Path

import pandas as pd


def load_price_csv(path: str | Path) -> pd.DataFrame:
    """读取 date × symbol 的复权收盘价宽表。"""
    prices = pd.read_csv(path, index_col="date", parse_dates=["date"])
    if prices.empty:
        raise ValueError("价格数据不能为空")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("价格日期必须唯一且严格递增")
    if prices.columns.duplicated().any():
        raise ValueError("价格列 symbol 必须唯一")
    numeric = prices.apply(pd.to_numeric, errors="coerce")
    if (numeric <= 0).any().any():
        raise ValueError("有效价格必须大于零")
    return numeric

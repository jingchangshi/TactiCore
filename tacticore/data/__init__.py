"""面向当前策略的数据读取函数。"""

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe

__all__ = ["load_price_csv", "load_universe"]

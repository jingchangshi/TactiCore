from pathlib import Path

import pandas as pd
import pytest

from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_universe_is_small_tradable_and_complete() -> None:
    universe = load_universe(ROOT / "config/universe.csv")

    assert 10 <= len(universe) <= 20
    assert set(universe["role"]) == {"tradable"}
    assert {"China", "United States", "Hong Kong", "Japan"} <= set(universe["region"])
    assert {"equity", "gold", "bond", "cash"} <= set(universe["asset_class"])


def test_price_loader_rejects_unsorted_dates(tmp_path: Path) -> None:
    price_file = tmp_path / "prices.csv"
    price_file.write_text("date,A\n2024-01-02,10\n2024-01-01,9\n", encoding="utf-8")

    with pytest.raises(ValueError, match="递增"):
        load_price_csv(price_file)


def test_price_loader_preserves_missing_values(tmp_path: Path) -> None:
    price_file = tmp_path / "prices.csv"
    price_file.write_text("date,A,B\n2024-01-01,10,\n2024-01-02,11,20\n", encoding="utf-8")

    prices = load_price_csv(price_file)

    assert pd.isna(prices.loc[pd.Timestamp("2024-01-01"), "B"])

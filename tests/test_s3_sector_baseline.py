from pathlib import Path

from research.experiments import run_s3_sector_baseline as baseline
from tacticore.data.prices import load_price_csv
from tacticore.data.universe import load_universe
from tacticore.strategies.china_sector_rotation import load_sector_rotation_config

ROOT = Path(__file__).resolve().parents[1]


def test_s3_universe_is_unique_and_fallback_is_not_a_sector() -> None:
    universe = load_universe(ROOT / "config/s3_sector_universe.csv")
    sectors = baseline.sector_symbols(universe)

    assert len(sectors) >= 8
    assert len(sectors) == len(set(sectors))
    assert "511010.SS" not in sectors


def test_s3_coverage_gate_and_targets_use_frozen_baseline() -> None:
    universe = load_universe(ROOT / "config/s3_sector_universe.csv")
    config = load_sector_rotation_config(ROOT / "config/s3_sector_rotation.toml")
    prices = load_price_csv(ROOT / "data/canonical/s3_sector_rotation_v1/etf_adjusted_close.csv")
    sectors = baseline.sector_symbols(universe)
    start = baseline.evaluation_start(prices, config, sectors)
    targets = baseline.build_month_end_targets(prices, config, sectors)

    assert config.momentum_lookback == 120
    assert config.top_k == 3
    assert start > prices.index[0]
    assert (targets.sum(axis=1) == 1.0).all()

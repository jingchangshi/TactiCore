from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

from research.experiments import run_s2_parameter_plateau as plateau
from tacticore.strategies.multi_asset_trend import load_trend_config

ROOT = Path(__file__).resolve().parents[1]


def test_parameter_set_is_coarse_predeclared_and_unique() -> None:
    assert plateau.PARAMETER_WINDOWS == (160, 180, 200, 220, 240)
    assert len(set(plateau.PARAMETER_WINDOWS)) == len(plateau.PARAMETER_WINDOWS)


def test_parameter_variants_change_only_trend_window() -> None:
    base = load_trend_config(ROOT / "config/strategy.toml")
    variants = plateau.parameter_configs(base)

    assert tuple(variants) == plateau.PARAMETER_WINDOWS
    assert base.trend_window == 200
    for window, variant in variants.items():
        assert variant.trend_window == window
        for field in fields(base):
            if field.name != "trend_window":
                assert getattr(variant, field.name) == getattr(base, field.name)


def test_parameter_output_requires_every_declared_window_once() -> None:
    valid = pd.DataFrame({"trend_window": plateau.PARAMETER_WINDOWS})

    plateau.validate_parameter_coverage(valid)
    with pytest.raises(ValueError, match="必须且只能"):
        plateau.validate_parameter_coverage(valid.iloc[:-1])
    with pytest.raises(ValueError, match="必须且只能"):
        plateau.validate_parameter_coverage(pd.concat([valid, valid.iloc[[-1]]]))

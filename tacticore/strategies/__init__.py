"""策略定义。"""

from tacticore.strategies.global_dual_momentum import (
    GlobalDualMomentumConfig,
    build_execution_weights,
    build_month_end_targets,
    load_strategy_config,
    select_assets,
)

__all__ = [
    "GlobalDualMomentumConfig",
    "build_execution_weights",
    "build_month_end_targets",
    "load_strategy_config",
    "select_assets",
]

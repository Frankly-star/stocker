"""Stocker strategy configuration system.

Usage:
    from stocker.strategy import get_strategy
    cfg = get_strategy()
    cfg.technical.rsi_window  # -> 14
"""

from stocker.strategy.manager import StrategyManager, get_strategy  # noqa: F401
from stocker.strategy.models import StrategyConfig  # noqa: F401

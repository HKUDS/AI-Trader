"""
Trading strategies module.

This module provides:
- BaseStrategy: Abstract base class for all strategies
- Built-in strategies: SMA Crossover, RSI, MACD, Bollinger Bands, etc.
- Easy framework for creating custom strategies
"""

from .base_strategy import BaseStrategy
from .sma_crossover import SMACrossoverStrategy
from .rsi_strategy import RSIStrategy
from .macd_strategy import MACDStrategy
from .bollinger_strategy import BollingerBandsStrategy
from .momentum_strategy import MomentumStrategy
from .mean_reversion import MeanReversionStrategy

__all__ = [
    "BaseStrategy",
    "SMACrossoverStrategy",
    "RSIStrategy",
    "MACDStrategy",
    "BollingerBandsStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
]

# Registry of available strategies
STRATEGY_REGISTRY = {
    "SMA Crossover": SMACrossoverStrategy,
    "RSI": RSIStrategy,
    "MACD": MACDStrategy,
    "Bollinger Bands": BollingerBandsStrategy,
    "Momentum": MomentumStrategy,
    "Mean Reversion": MeanReversionStrategy,
}


def get_strategy(name: str, **kwargs):
    """Get a strategy instance by name."""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name](**kwargs)


def list_strategies():
    """List all available strategies."""
    return list(STRATEGY_REGISTRY.keys())

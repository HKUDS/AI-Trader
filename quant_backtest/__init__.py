"""
Quant Backtest - A Free Quantitative Algorithm Tracking & Backtesting Platform

This module provides:
- Backtesting engine for trading strategies
- Portfolio tracking and management
- Performance metrics calculation
- Multiple built-in strategies
- Easy customization for user requirements

All components are free and open-source with zero cost.
"""

__version__ = "1.0.0"
__author__ = "AI-Trader Team"

from .core.backtest_engine import BacktestEngine
from .core.portfolio import Portfolio
from .core.metrics import PerformanceMetrics
from .strategies.base_strategy import BaseStrategy

__all__ = [
    "BacktestEngine",
    "Portfolio",
    "PerformanceMetrics",
    "BaseStrategy",
]

"""
Configuration module for the quant-backtest application.

Provides:
- User-configurable settings
- Strategy parameters
- Data source configuration
"""

from .settings import Settings, load_settings, save_settings

__all__ = ["Settings", "load_settings", "save_settings"]

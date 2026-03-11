"""
Settings management for the quant-backtest application.

Allows users to customize:
- Default initial capital
- Commission and slippage rates
- Risk parameters
- UI preferences
- Data sources
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import json


DEFAULT_CONFIG_PATH = Path.home() / ".quant_backtest" / "config.json"


@dataclass
class PortfolioSettings:
    """Portfolio-related settings."""
    initial_cash: float = 100000.0
    commission_rate: float = 0.001  # 0.1%
    slippage_rate: float = 0.0005  # 0.05%
    max_position_size: float = 0.25  # 25% max per position
    allow_shorting: bool = False
    risk_free_rate: float = 0.02  # 2% annual


@dataclass
class BacktestSettings:
    """Backtest-related settings."""
    default_start_date: Optional[str] = None
    default_end_date: Optional[str] = None
    trading_days_per_year: int = 252
    default_strategy: str = "SMA Crossover"


@dataclass
class DataSettings:
    """Data source settings."""
    default_source: str = "sample"  # sample, yahoo, local, ai_trader
    yahoo_symbols: List[str] = field(default_factory=lambda: ["AAPL", "GOOGL", "MSFT"])
    local_data_path: Optional[str] = None
    cache_enabled: bool = True
    cache_path: Optional[str] = None


@dataclass
class UISettings:
    """UI preferences."""
    theme: str = "dark"
    chart_height: int = 400
    show_advanced_metrics: bool = True
    decimal_places: int = 2
    currency_symbol: str = "$"


@dataclass
class Settings:
    """
    Main settings container.

    Access settings like:
        settings = load_settings()
        print(settings.portfolio.initial_cash)
        settings.portfolio.commission_rate = 0.002
        save_settings(settings)
    """
    portfolio: PortfolioSettings = field(default_factory=PortfolioSettings)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
    data: DataSettings = field(default_factory=DataSettings)
    ui: UISettings = field(default_factory=UISettings)

    # Custom strategy defaults
    strategy_defaults: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert settings to dictionary."""
        return {
            "portfolio": asdict(self.portfolio),
            "backtest": asdict(self.backtest),
            "data": asdict(self.data),
            "ui": asdict(self.ui),
            "strategy_defaults": self.strategy_defaults,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Create settings from dictionary."""
        settings = cls()

        if "portfolio" in data:
            settings.portfolio = PortfolioSettings(**data["portfolio"])
        if "backtest" in data:
            settings.backtest = BacktestSettings(**data["backtest"])
        if "data" in data:
            settings.data = DataSettings(**data["data"])
        if "ui" in data:
            settings.ui = UISettings(**data["ui"])
        if "strategy_defaults" in data:
            settings.strategy_defaults = data["strategy_defaults"]

        return settings

    def get_strategy_defaults(self, strategy_name: str) -> dict:
        """Get default parameters for a strategy."""
        return self.strategy_defaults.get(strategy_name, {})

    def set_strategy_defaults(self, strategy_name: str, params: dict) -> None:
        """Set default parameters for a strategy."""
        self.strategy_defaults[strategy_name] = params


def load_settings(filepath: Optional[str] = None) -> Settings:
    """
    Load settings from file.

    Args:
        filepath: Path to config file (defaults to ~/.quant_backtest/config.json)

    Returns:
        Settings object
    """
    if filepath is None:
        filepath = DEFAULT_CONFIG_PATH

    path = Path(filepath)

    if not path.exists():
        return Settings()

    try:
        with open(path, "r") as f:
            data = json.load(f)
        return Settings.from_dict(data)
    except Exception as e:
        print(f"Error loading settings: {e}")
        return Settings()


def save_settings(settings: Settings, filepath: Optional[str] = None) -> bool:
    """
    Save settings to file.

    Args:
        settings: Settings object to save
        filepath: Path to config file

    Returns:
        True if successful
    """
    if filepath is None:
        filepath = DEFAULT_CONFIG_PATH

    path = Path(filepath)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(settings.to_dict(), f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False


# Pre-configured profiles for different use cases
PRESET_PROFILES = {
    "conservative": {
        "portfolio": {
            "initial_cash": 100000.0,
            "commission_rate": 0.001,
            "max_position_size": 0.10,  # Max 10% per position
            "allow_shorting": False,
        },
        "strategy_defaults": {
            "SMA Crossover": {"fast_period": 20, "slow_period": 50, "position_size": 10},
            "RSI": {"oversold": 20, "overbought": 80, "position_size": 10},
        },
    },
    "moderate": {
        "portfolio": {
            "initial_cash": 100000.0,
            "commission_rate": 0.001,
            "max_position_size": 0.20,
            "allow_shorting": False,
        },
        "strategy_defaults": {
            "SMA Crossover": {"fast_period": 10, "slow_period": 30, "position_size": 20},
            "RSI": {"oversold": 30, "overbought": 70, "position_size": 20},
        },
    },
    "aggressive": {
        "portfolio": {
            "initial_cash": 100000.0,
            "commission_rate": 0.001,
            "max_position_size": 0.40,
            "allow_shorting": True,
        },
        "strategy_defaults": {
            "SMA Crossover": {"fast_period": 5, "slow_period": 15, "position_size": 30},
            "RSI": {"oversold": 40, "overbought": 60, "position_size": 30},
        },
    },
    "day_trader": {
        "portfolio": {
            "initial_cash": 25000.0,  # Pattern day trader minimum
            "commission_rate": 0.0,  # Many brokers now commission-free
            "max_position_size": 0.50,
            "allow_shorting": True,
        },
    },
}


def apply_profile(profile_name: str) -> Settings:
    """
    Load a preset profile.

    Args:
        profile_name: Name of the profile (conservative, moderate, aggressive, day_trader)

    Returns:
        Settings configured with the profile
    """
    if profile_name not in PRESET_PROFILES:
        raise ValueError(f"Unknown profile: {profile_name}. Available: {list(PRESET_PROFILES.keys())}")

    settings = Settings()
    profile = PRESET_PROFILES[profile_name]

    if "portfolio" in profile:
        for key, value in profile["portfolio"].items():
            setattr(settings.portfolio, key, value)

    if "strategy_defaults" in profile:
        settings.strategy_defaults = profile["strategy_defaults"]

    return settings

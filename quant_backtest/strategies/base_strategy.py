"""
Base Strategy class - Abstract base for all trading strategies.

Extend this class to create custom trading strategies. Override the
`on_bar()` method to implement your trading logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from ..core.backtest_engine import BacktestEngine, MarketData


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    To create a custom strategy:
    1. Inherit from BaseStrategy
    2. Define your parameters in __init__
    3. Override on_bar() with your trading logic
    4. Optionally override initialize() and finalize()

    Example:
        ```python
        class MyStrategy(BaseStrategy):
            def __init__(self, lookback: int = 20):
                super().__init__()
                self.lookback = lookback

            def on_bar(self, data: MarketData):
                for symbol in self.symbols:
                    prices = self.get_historical_prices(symbol, self.lookback)
                    if len(prices) < self.lookback:
                        continue

                    # Your trading logic here
                    avg_price = sum(prices) / len(prices)
                    current_price = data.get_price(symbol)

                    if current_price < avg_price * 0.95:
                        self.buy(symbol, amount=10000)
                    elif current_price > avg_price * 1.05:
                        self.sell(symbol, percent=100)
        ```
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        """
        Initialize the strategy.

        Args:
            symbols: List of symbols to trade (if None, trades all available)
        """
        self._engine: Optional["BacktestEngine"] = None
        self.symbols = symbols or []
        self._initialized = False

    def set_engine(self, engine: "BacktestEngine") -> None:
        """Set the backtesting engine (called internally)."""
        self._engine = engine
        if not self.symbols:
            self.symbols = list(engine.data.keys())

    @property
    def engine(self) -> "BacktestEngine":
        """Get the backtesting engine."""
        if self._engine is None:
            raise RuntimeError("Strategy not attached to an engine")
        return self._engine

    @property
    def portfolio(self):
        """Get the portfolio."""
        return self.engine.portfolio

    @property
    def cash(self) -> float:
        """Get available cash."""
        return self.portfolio.cash

    @property
    def equity(self) -> float:
        """Get total portfolio equity."""
        return self.portfolio.total_equity

    def get_position(self, symbol: str) -> float:
        """Get current position quantity for a symbol."""
        return self.portfolio.get_position_quantity(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if we have a position in a symbol."""
        return self.get_position(symbol) > 0

    def get_historical_data(self, symbol: str, lookback: int = 100) -> List[dict]:
        """
        Get historical OHLCV data for a symbol.

        Args:
            symbol: Ticker symbol
            lookback: Number of bars to retrieve

        Returns:
            List of OHLCV dictionaries
        """
        return self.engine.get_historical_data(symbol, lookback)

    def get_historical_prices(self, symbol: str, lookback: int = 100,
                              price_type: str = "close") -> List[float]:
        """
        Get historical prices for a symbol.

        Args:
            symbol: Ticker symbol
            lookback: Number of prices to retrieve
            price_type: Type of price (open, high, low, close)

        Returns:
            List of prices
        """
        data = self.get_historical_data(symbol, lookback)
        return [d.get(price_type, 0) for d in data]

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        return self.engine.get_current_price(symbol)

    # ==================== Order Methods ====================

    def buy(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        amount: Optional[float] = None,
    ):
        """
        Place a market buy order.

        Args:
            symbol: Ticker symbol
            quantity: Number of shares (mutually exclusive with amount)
            amount: Dollar amount to invest
        """
        return self.engine.buy(symbol, quantity=quantity, amount=amount)

    def sell(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        percent: Optional[float] = None,
    ):
        """
        Place a market sell order.

        Args:
            symbol: Ticker symbol
            quantity: Number of shares (mutually exclusive with percent)
            percent: Percentage of position to sell (0-100)
        """
        return self.engine.sell(symbol, quantity=quantity, percent=percent)

    def close_position(self, symbol: str):
        """Close entire position in a symbol."""
        return self.sell(symbol, percent=100)

    def close_all_positions(self):
        """Close all open positions."""
        for symbol in list(self.portfolio.positions.keys()):
            self.close_position(symbol)

    # ==================== Signal Recording ====================

    def record_signal(self, signal_type: str, symbol: str, details: dict = None):
        """Record a signal for later analysis."""
        self.engine.record_signal(signal_type, symbol, details)

    # ==================== Lifecycle Methods ====================

    def initialize(self) -> None:
        """
        Called once before the backtest starts.
        Override to set up indicators, state, etc.
        """
        self._initialized = True

    @abstractmethod
    def on_bar(self, data: "MarketData") -> None:
        """
        Called on each bar of data.
        Override this method with your trading logic.

        Args:
            data: MarketData object with current prices
        """
        pass

    def finalize(self) -> None:
        """
        Called once after the backtest completes.
        Override to clean up resources, calculate final stats, etc.
        """
        pass

    # ==================== Utility Methods ====================

    def get_parameters(self) -> dict:
        """
        Get strategy parameters as a dictionary.
        Override to include custom parameters.
        """
        return {
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """
        Get information about strategy parameters for UI.
        Override to provide parameter metadata.

        Returns:
            Dictionary of parameter_name -> {type, default, min, max, description}
        """
        return {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.get_parameters()})"


# ==================== Technical Indicator Helpers ====================

def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    """Calculate Simple Moving Average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return None

    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # Start with SMA

    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_macd(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Returns:
        Tuple of (macd_line, signal_line, histogram)
    """
    if len(prices) < slow_period + signal_period:
        return None, None, None

    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)

    if fast_ema is None or slow_ema is None:
        return None, None, None

    macd_line = fast_ema - slow_ema

    # Calculate signal line (EMA of MACD values)
    # Simplified: using current MACD as approximation
    signal_line = macd_line * 0.9  # Approximation

    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple:
    """
    Calculate Bollinger Bands.

    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    if len(prices) < period:
        return None, None, None

    sma = sum(prices[-period:]) / period

    # Calculate standard deviation
    variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
    std = variance ** 0.5

    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)

    return upper, sma, lower


def calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Optional[float]:
    """Calculate Average True Range."""
    if len(highs) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i - 1])
        low_close = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(high_low, high_close, low_close))

    if len(true_ranges) < period:
        return None

    return sum(true_ranges[-period:]) / period

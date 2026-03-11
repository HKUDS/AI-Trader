"""
MACD Strategy - Trend-following strategy using Moving Average Convergence Divergence.

Buy when MACD line crosses above signal line.
Sell when MACD line crosses below signal line.
"""

from typing import List, Optional, Dict
from .base_strategy import BaseStrategy, calculate_ema


class MACDStrategy(BaseStrategy):
    """
    MACD (Moving Average Convergence Divergence) Strategy.

    This strategy uses MACD indicator for trend-following:
    - Buy signal: When MACD line crosses above signal line
    - Sell signal: When MACD line crosses below signal line

    Parameters:
        fast_period: Period for fast EMA (default: 12)
        slow_period: Period for slow EMA (default: 26)
        signal_period: Period for signal line (default: 9)
        position_size: Percentage of portfolio per trade (default: 20%)
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.position_size = position_size

        # State tracking
        self._macd_history: Dict[str, List[float]] = {}
        self._prev_macd: Dict[str, float] = {}
        self._prev_signal: Dict[str, float] = {}

    def initialize(self) -> None:
        """Initialize state tracking."""
        super().initialize()
        self._macd_history = {}
        self._prev_macd = {}
        self._prev_signal = {}

    def _calculate_macd(self, prices: List[float]) -> tuple:
        """Calculate MACD values."""
        if len(prices) < self.slow_period:
            return None, None, None

        fast_ema = calculate_ema(prices, self.fast_period)
        slow_ema = calculate_ema(prices, self.slow_period)

        if fast_ema is None or slow_ema is None:
            return None, None, None

        macd_line = fast_ema - slow_ema
        return macd_line, fast_ema, slow_ema

    def on_bar(self, data) -> None:
        """Execute strategy logic on each bar."""
        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.slow_period + self.signal_period + 10)

            if len(prices) < self.slow_period + self.signal_period:
                continue

            # Calculate MACD
            macd_line, fast_ema, slow_ema = self._calculate_macd(prices)

            if macd_line is None:
                continue

            # Track MACD history for signal line calculation
            if symbol not in self._macd_history:
                self._macd_history[symbol] = []

            self._macd_history[symbol].append(macd_line)

            # Keep only recent history
            if len(self._macd_history[symbol]) > self.signal_period * 2:
                self._macd_history[symbol] = self._macd_history[symbol][-self.signal_period * 2:]

            # Calculate signal line (EMA of MACD)
            if len(self._macd_history[symbol]) >= self.signal_period:
                signal_line = calculate_ema(self._macd_history[symbol], self.signal_period)
            else:
                signal_line = None

            if signal_line is None:
                continue

            current_price = data.get_price(symbol)
            if current_price is None:
                continue

            histogram = macd_line - signal_line

            prev_macd = self._prev_macd.get(symbol)
            prev_signal = self._prev_signal.get(symbol)

            # Check for crossover
            if prev_macd is not None and prev_signal is not None:
                prev_histogram = prev_macd - prev_signal

                # Bullish crossover
                if prev_histogram <= 0 and histogram > 0:
                    if not self.has_position(symbol):
                        amount = self.equity * (self.position_size / 100)
                        self.buy(symbol, amount=amount)
                        self.record_signal("BUY", symbol, {
                            "reason": "MACD Bullish Crossover",
                            "macd": macd_line,
                            "signal": signal_line,
                            "histogram": histogram,
                            "price": current_price,
                        })

                # Bearish crossover
                elif prev_histogram >= 0 and histogram < 0:
                    if self.has_position(symbol):
                        self.close_position(symbol)
                        self.record_signal("SELL", symbol, {
                            "reason": "MACD Bearish Crossover",
                            "macd": macd_line,
                            "signal": signal_line,
                            "histogram": histogram,
                            "price": current_price,
                        })

            # Update previous values
            self._prev_macd[symbol] = macd_line
            self._prev_signal[symbol] = signal_line

    def get_parameters(self) -> dict:
        """Get strategy parameters."""
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "signal_period": self.signal_period,
            "position_size": self.position_size,
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """Get parameter metadata for UI."""
        return {
            "fast_period": {
                "type": "int",
                "default": 12,
                "min": 5,
                "max": 20,
                "description": "Fast EMA period",
            },
            "slow_period": {
                "type": "int",
                "default": 26,
                "min": 15,
                "max": 50,
                "description": "Slow EMA period",
            },
            "signal_period": {
                "type": "int",
                "default": 9,
                "min": 5,
                "max": 15,
                "description": "Signal line period",
            },
            "position_size": {
                "type": "float",
                "default": 20.0,
                "min": 5.0,
                "max": 100.0,
                "description": "Position size as % of portfolio",
            },
        }

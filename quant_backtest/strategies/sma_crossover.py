"""
SMA Crossover Strategy - Classic trend-following strategy.

Buy when fast SMA crosses above slow SMA (golden cross).
Sell when fast SMA crosses below slow SMA (death cross).
"""

from typing import List, Optional, Dict
from .base_strategy import BaseStrategy, calculate_sma


class SMACrossoverStrategy(BaseStrategy):
    """
    Simple Moving Average Crossover Strategy.

    This is a classic trend-following strategy that generates:
    - Buy signal: When fast SMA crosses above slow SMA
    - Sell signal: When fast SMA crosses below slow SMA

    Parameters:
        fast_period: Period for fast moving average (default: 10)
        slow_period: Period for slow moving average (default: 30)
        position_size: Percentage of portfolio per trade (default: 20%)
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.position_size = position_size

        # State tracking
        self._prev_fast_sma: Dict[str, float] = {}
        self._prev_slow_sma: Dict[str, float] = {}

    def initialize(self) -> None:
        """Initialize state tracking."""
        super().initialize()
        self._prev_fast_sma = {}
        self._prev_slow_sma = {}

    def on_bar(self, data) -> None:
        """Execute strategy logic on each bar."""
        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.slow_period + 1)

            if len(prices) < self.slow_period:
                continue

            # Calculate SMAs
            fast_sma = calculate_sma(prices, self.fast_period)
            slow_sma = calculate_sma(prices, self.slow_period)

            if fast_sma is None or slow_sma is None:
                continue

            current_price = data.get_price(symbol)
            if current_price is None:
                continue

            # Get previous SMAs for crossover detection
            prev_fast = self._prev_fast_sma.get(symbol)
            prev_slow = self._prev_slow_sma.get(symbol)

            # Check for crossover
            if prev_fast is not None and prev_slow is not None:
                # Golden cross: fast crosses above slow
                if prev_fast <= prev_slow and fast_sma > slow_sma:
                    if not self.has_position(symbol):
                        amount = self.equity * (self.position_size / 100)
                        self.buy(symbol, amount=amount)
                        self.record_signal("BUY", symbol, {
                            "reason": "Golden Cross",
                            "fast_sma": fast_sma,
                            "slow_sma": slow_sma,
                            "price": current_price,
                        })

                # Death cross: fast crosses below slow
                elif prev_fast >= prev_slow and fast_sma < slow_sma:
                    if self.has_position(symbol):
                        self.close_position(symbol)
                        self.record_signal("SELL", symbol, {
                            "reason": "Death Cross",
                            "fast_sma": fast_sma,
                            "slow_sma": slow_sma,
                            "price": current_price,
                        })

            # Update previous values
            self._prev_fast_sma[symbol] = fast_sma
            self._prev_slow_sma[symbol] = slow_sma

    def get_parameters(self) -> dict:
        """Get strategy parameters."""
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "position_size": self.position_size,
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """Get parameter metadata for UI."""
        return {
            "fast_period": {
                "type": "int",
                "default": 10,
                "min": 2,
                "max": 50,
                "description": "Fast moving average period",
            },
            "slow_period": {
                "type": "int",
                "default": 30,
                "min": 10,
                "max": 200,
                "description": "Slow moving average period",
            },
            "position_size": {
                "type": "float",
                "default": 20.0,
                "min": 5.0,
                "max": 100.0,
                "description": "Position size as % of portfolio",
            },
        }

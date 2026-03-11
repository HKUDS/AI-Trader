"""
RSI Strategy - Mean reversion strategy based on Relative Strength Index.

Buy when RSI indicates oversold conditions.
Sell when RSI indicates overbought conditions.
"""

from typing import List, Optional, Dict
from .base_strategy import BaseStrategy, calculate_rsi


class RSIStrategy(BaseStrategy):
    """
    Relative Strength Index (RSI) Strategy.

    This strategy uses RSI to identify oversold and overbought conditions:
    - Buy signal: When RSI drops below oversold threshold
    - Sell signal: When RSI rises above overbought threshold

    Parameters:
        rsi_period: Period for RSI calculation (default: 14)
        oversold: RSI threshold for oversold (default: 30)
        overbought: RSI threshold for overbought (default: 70)
        position_size: Percentage of portfolio per trade (default: 20%)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.position_size = position_size

        # State tracking
        self._prev_rsi: Dict[str, float] = {}

    def initialize(self) -> None:
        """Initialize state tracking."""
        super().initialize()
        self._prev_rsi = {}

    def on_bar(self, data) -> None:
        """Execute strategy logic on each bar."""
        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.rsi_period + 5)

            if len(prices) < self.rsi_period + 1:
                continue

            # Calculate RSI
            rsi = calculate_rsi(prices, self.rsi_period)

            if rsi is None:
                continue

            current_price = data.get_price(symbol)
            if current_price is None:
                continue

            prev_rsi = self._prev_rsi.get(symbol)

            # Buy when RSI crosses below oversold from above
            if prev_rsi is not None:
                # Oversold - potential buy
                if prev_rsi >= self.oversold and rsi < self.oversold:
                    if not self.has_position(symbol):
                        amount = self.equity * (self.position_size / 100)
                        self.buy(symbol, amount=amount)
                        self.record_signal("BUY", symbol, {
                            "reason": "RSI Oversold",
                            "rsi": rsi,
                            "threshold": self.oversold,
                            "price": current_price,
                        })

                # Overbought - potential sell
                elif prev_rsi <= self.overbought and rsi > self.overbought:
                    if self.has_position(symbol):
                        self.close_position(symbol)
                        self.record_signal("SELL", symbol, {
                            "reason": "RSI Overbought",
                            "rsi": rsi,
                            "threshold": self.overbought,
                            "price": current_price,
                        })

            # Update previous RSI
            self._prev_rsi[symbol] = rsi

    def get_parameters(self) -> dict:
        """Get strategy parameters."""
        return {
            "rsi_period": self.rsi_period,
            "oversold": self.oversold,
            "overbought": self.overbought,
            "position_size": self.position_size,
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """Get parameter metadata for UI."""
        return {
            "rsi_period": {
                "type": "int",
                "default": 14,
                "min": 5,
                "max": 30,
                "description": "RSI calculation period",
            },
            "oversold": {
                "type": "float",
                "default": 30.0,
                "min": 10.0,
                "max": 40.0,
                "description": "RSI oversold threshold (buy signal)",
            },
            "overbought": {
                "type": "float",
                "default": 70.0,
                "min": 60.0,
                "max": 90.0,
                "description": "RSI overbought threshold (sell signal)",
            },
            "position_size": {
                "type": "float",
                "default": 20.0,
                "min": 5.0,
                "max": 100.0,
                "description": "Position size as % of portfolio",
            },
        }

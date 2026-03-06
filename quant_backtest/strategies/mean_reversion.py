"""
Mean Reversion Strategy - Buy low, sell high based on deviation from mean.

Buy when price falls significantly below moving average.
Sell when price reverts back to or above average.
"""

from typing import List, Optional, Dict
from .base_strategy import BaseStrategy, calculate_sma


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy.

    This strategy assumes prices revert to their mean:
    - Buy signal: When price is X% below moving average
    - Sell signal: When price returns to moving average

    Parameters:
        ma_period: Moving average period (default: 20)
        entry_deviation: % below MA to enter (default: 5%)
        exit_deviation: % to exit position (default: 0% - at MA)
        position_size: Percentage of portfolio per trade (default: 20%)
    """

    def __init__(
        self,
        ma_period: int = 20,
        entry_deviation: float = 5.0,
        exit_deviation: float = 0.0,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.ma_period = ma_period
        self.entry_deviation = entry_deviation
        self.exit_deviation = exit_deviation
        self.position_size = position_size

        # Track entry prices for profit targets
        self._entry_prices: Dict[str, float] = {}

    def initialize(self) -> None:
        """Initialize state tracking."""
        super().initialize()
        self._entry_prices = {}

    def on_bar(self, data) -> None:
        """Execute strategy logic on each bar."""
        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.ma_period + 5)

            if len(prices) < self.ma_period:
                continue

            # Calculate moving average
            ma = calculate_sma(prices, self.ma_period)

            if ma is None or ma == 0:
                continue

            current_price = data.get_price(symbol)
            if current_price is None:
                continue

            # Calculate deviation from MA
            deviation = ((current_price - ma) / ma) * 100

            # Entry: price significantly below MA
            if deviation < -self.entry_deviation:
                if not self.has_position(symbol):
                    amount = self.equity * (self.position_size / 100)
                    self.buy(symbol, amount=amount)
                    self._entry_prices[symbol] = current_price
                    self.record_signal("BUY", symbol, {
                        "reason": "Price below MA",
                        "price": current_price,
                        "ma": ma,
                        "deviation": deviation,
                        "entry_threshold": -self.entry_deviation,
                    })

            # Exit: price returned to or above MA
            elif deviation >= self.exit_deviation:
                if self.has_position(symbol):
                    entry_price = self._entry_prices.get(symbol, current_price)
                    pnl = ((current_price - entry_price) / entry_price) * 100

                    self.close_position(symbol)
                    self.record_signal("SELL", symbol, {
                        "reason": "Price reverted to MA",
                        "price": current_price,
                        "ma": ma,
                        "deviation": deviation,
                        "pnl_pct": pnl,
                    })

                    if symbol in self._entry_prices:
                        del self._entry_prices[symbol]

    def get_parameters(self) -> dict:
        """Get strategy parameters."""
        return {
            "ma_period": self.ma_period,
            "entry_deviation": self.entry_deviation,
            "exit_deviation": self.exit_deviation,
            "position_size": self.position_size,
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """Get parameter metadata for UI."""
        return {
            "ma_period": {
                "type": "int",
                "default": 20,
                "min": 5,
                "max": 100,
                "description": "Moving average period",
            },
            "entry_deviation": {
                "type": "float",
                "default": 5.0,
                "min": 1.0,
                "max": 20.0,
                "description": "% below MA to enter",
            },
            "exit_deviation": {
                "type": "float",
                "default": 0.0,
                "min": -5.0,
                "max": 10.0,
                "description": "% deviation from MA to exit",
            },
            "position_size": {
                "type": "float",
                "default": 20.0,
                "min": 5.0,
                "max": 100.0,
                "description": "Position size as % of portfolio",
            },
        }

"""
Bollinger Bands Strategy - Mean reversion strategy using price volatility bands.

Buy when price touches lower band (oversold).
Sell when price touches upper band (overbought).
"""

from typing import List, Optional, Dict
from .base_strategy import BaseStrategy, calculate_bollinger_bands


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands Strategy.

    This strategy uses Bollinger Bands for mean reversion trading:
    - Buy signal: When price touches or crosses below lower band
    - Sell signal: When price touches or crosses above upper band

    Parameters:
        period: Period for moving average (default: 20)
        std_dev: Number of standard deviations for bands (default: 2.0)
        position_size: Percentage of portfolio per trade (default: 20%)
    """

    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.period = period
        self.std_dev = std_dev
        self.position_size = position_size

        # State tracking
        self._prev_price: Dict[str, float] = {}

    def initialize(self) -> None:
        """Initialize state tracking."""
        super().initialize()
        self._prev_price = {}

    def on_bar(self, data) -> None:
        """Execute strategy logic on each bar."""
        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.period + 5)

            if len(prices) < self.period:
                continue

            # Calculate Bollinger Bands
            upper, middle, lower = calculate_bollinger_bands(
                prices, self.period, self.std_dev
            )

            if upper is None or lower is None:
                continue

            current_price = data.get_price(symbol)
            if current_price is None:
                continue

            prev_price = self._prev_price.get(symbol)

            if prev_price is not None:
                # Price touches lower band - buy signal
                if prev_price >= lower and current_price < lower:
                    if not self.has_position(symbol):
                        amount = self.equity * (self.position_size / 100)
                        self.buy(symbol, amount=amount)
                        self.record_signal("BUY", symbol, {
                            "reason": "Price below lower band",
                            "price": current_price,
                            "lower_band": lower,
                            "middle_band": middle,
                            "upper_band": upper,
                        })

                # Price touches upper band - sell signal
                elif prev_price <= upper and current_price > upper:
                    if self.has_position(symbol):
                        self.close_position(symbol)
                        self.record_signal("SELL", symbol, {
                            "reason": "Price above upper band",
                            "price": current_price,
                            "lower_band": lower,
                            "middle_band": middle,
                            "upper_band": upper,
                        })

                # Also sell if price returns to middle from above upper
                elif self.has_position(symbol) and current_price <= middle and prev_price > middle:
                    self.close_position(symbol)
                    self.record_signal("SELL", symbol, {
                        "reason": "Price returned to middle band",
                        "price": current_price,
                        "middle_band": middle,
                    })

            # Update previous price
            self._prev_price[symbol] = current_price

    def get_parameters(self) -> dict:
        """Get strategy parameters."""
        return {
            "period": self.period,
            "std_dev": self.std_dev,
            "position_size": self.position_size,
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """Get parameter metadata for UI."""
        return {
            "period": {
                "type": "int",
                "default": 20,
                "min": 10,
                "max": 50,
                "description": "Moving average period",
            },
            "std_dev": {
                "type": "float",
                "default": 2.0,
                "min": 1.0,
                "max": 3.0,
                "description": "Standard deviations for bands",
            },
            "position_size": {
                "type": "float",
                "default": 20.0,
                "min": 5.0,
                "max": 100.0,
                "description": "Position size as % of portfolio",
            },
        }

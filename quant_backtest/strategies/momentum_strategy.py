"""
Momentum Strategy - Trend-following strategy based on price momentum.

Buy assets showing strong positive momentum.
Sell when momentum weakens or reverses.
"""

from typing import List, Optional, Dict
from .base_strategy import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """
    Momentum Strategy.

    This strategy trades based on price momentum:
    - Buy signal: When momentum (rate of change) exceeds threshold
    - Sell signal: When momentum drops below negative threshold

    Parameters:
        lookback: Period for momentum calculation (default: 20)
        buy_threshold: Minimum momentum to buy (default: 5%)
        sell_threshold: Momentum level to sell (default: -2%)
        position_size: Percentage of portfolio per trade (default: 20%)
    """

    def __init__(
        self,
        lookback: int = 20,
        buy_threshold: float = 5.0,
        sell_threshold: float = -2.0,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.lookback = lookback
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.position_size = position_size

    def _calculate_momentum(self, prices: List[float]) -> Optional[float]:
        """Calculate momentum as percentage change."""
        if len(prices) < self.lookback + 1:
            return None

        old_price = prices[-self.lookback - 1]
        new_price = prices[-1]

        if old_price == 0:
            return None

        return ((new_price - old_price) / old_price) * 100

    def on_bar(self, data) -> None:
        """Execute strategy logic on each bar."""
        # Calculate momentum for all symbols
        momentums = {}

        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.lookback + 5)

            if len(prices) < self.lookback + 1:
                continue

            momentum = self._calculate_momentum(prices)
            if momentum is not None:
                momentums[symbol] = momentum

        # Sort by momentum (highest first)
        sorted_symbols = sorted(
            momentums.keys(),
            key=lambda s: momentums[s],
            reverse=True
        )

        for symbol in sorted_symbols:
            momentum = momentums[symbol]
            current_price = data.get_price(symbol)

            if current_price is None:
                continue

            # Strong positive momentum - buy
            if momentum > self.buy_threshold:
                if not self.has_position(symbol):
                    amount = self.equity * (self.position_size / 100)
                    self.buy(symbol, amount=amount)
                    self.record_signal("BUY", symbol, {
                        "reason": "Strong positive momentum",
                        "momentum": momentum,
                        "threshold": self.buy_threshold,
                        "price": current_price,
                    })

            # Negative momentum - sell
            elif momentum < self.sell_threshold:
                if self.has_position(symbol):
                    self.close_position(symbol)
                    self.record_signal("SELL", symbol, {
                        "reason": "Negative momentum",
                        "momentum": momentum,
                        "threshold": self.sell_threshold,
                        "price": current_price,
                    })

    def get_parameters(self) -> dict:
        """Get strategy parameters."""
        return {
            "lookback": self.lookback,
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "position_size": self.position_size,
            "symbols": self.symbols,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        """Get parameter metadata for UI."""
        return {
            "lookback": {
                "type": "int",
                "default": 20,
                "min": 5,
                "max": 60,
                "description": "Lookback period for momentum",
            },
            "buy_threshold": {
                "type": "float",
                "default": 5.0,
                "min": 1.0,
                "max": 20.0,
                "description": "Minimum momentum % to buy",
            },
            "sell_threshold": {
                "type": "float",
                "default": -2.0,
                "min": -10.0,
                "max": 0.0,
                "description": "Momentum % threshold to sell",
            },
            "position_size": {
                "type": "float",
                "default": 20.0,
                "min": 5.0,
                "max": 100.0,
                "description": "Position size as % of portfolio",
            },
        }

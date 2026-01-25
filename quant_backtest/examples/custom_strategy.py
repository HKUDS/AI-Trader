#!/usr/bin/env python3
"""
Custom Strategy Example

This example shows how to create your own trading strategy.
Run with: python -m quant_backtest.examples.custom_strategy
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_backtest import BacktestEngine
from quant_backtest.strategies import BaseStrategy
from quant_backtest.data import generate_sample_data


class DualMomentumStrategy(BaseStrategy):
    """
    Dual Momentum Strategy

    Combines absolute momentum (trend) with relative momentum (comparison).
    - Only buys if the asset has positive absolute momentum
    - Ranks assets by relative momentum and buys the top performers
    """

    def __init__(
        self,
        lookback: int = 60,
        top_n: int = 2,
        position_size: float = 40.0,
        symbols: Optional[List[str]] = None,
    ):
        """
        Initialize the strategy.

        Args:
            lookback: Days for momentum calculation
            top_n: Number of top performers to hold
            position_size: % of portfolio per position
        """
        super().__init__(symbols)
        self.lookback = lookback
        self.top_n = top_n
        self.position_size = position_size
        self._last_rebalance = None

    def _calculate_momentum(self, prices: List[float]) -> Optional[float]:
        """Calculate momentum as return over lookback period."""
        if len(prices) < self.lookback:
            return None
        old_price = prices[-self.lookback]
        new_price = prices[-1]
        if old_price <= 0:
            return None
        return ((new_price - old_price) / old_price) * 100

    def on_bar(self, data) -> None:
        """Execute strategy logic."""
        # Calculate momentum for all symbols
        momentums = {}

        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, self.lookback + 10)
            momentum = self._calculate_momentum(prices)
            if momentum is not None:
                momentums[symbol] = momentum

        if not momentums:
            return

        # Filter for positive absolute momentum
        positive_momentum = {s: m for s, m in momentums.items() if m > 0}

        # Rank by relative momentum (highest first)
        ranked = sorted(positive_momentum.keys(), key=lambda s: positive_momentum[s], reverse=True)

        # Select top N
        to_hold = set(ranked[:self.top_n])

        # Sell positions not in top N
        for symbol in list(self.portfolio.positions.keys()):
            if symbol not in to_hold:
                self.close_position(symbol)
                self.record_signal("SELL", symbol, {
                    "reason": "No longer in top performers",
                    "momentum": momentums.get(symbol, 0),
                })

        # Buy top N if not already holding
        for symbol in to_hold:
            if not self.has_position(symbol):
                amount = self.equity * (self.position_size / 100)
                self.buy(symbol, amount=amount)
                self.record_signal("BUY", symbol, {
                    "reason": "Top momentum performer",
                    "momentum": momentums.get(symbol, 0),
                    "rank": ranked.index(symbol) + 1,
                })

    def get_parameters(self) -> dict:
        return {
            "lookback": self.lookback,
            "top_n": self.top_n,
            "position_size": self.position_size,
        }

    @classmethod
    def get_parameter_info(cls) -> Dict[str, dict]:
        return {
            "lookback": {
                "type": "int",
                "default": 60,
                "min": 20,
                "max": 252,
                "description": "Momentum lookback period",
            },
            "top_n": {
                "type": "int",
                "default": 2,
                "min": 1,
                "max": 10,
                "description": "Number of top assets to hold",
            },
            "position_size": {
                "type": "float",
                "default": 40.0,
                "min": 10.0,
                "max": 100.0,
                "description": "Position size per asset (%)",
            },
        }


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Strategy

    Buys when price breaks above recent high.
    Sells when price breaks below recent low or hits stop loss.
    """

    def __init__(
        self,
        lookback: int = 20,
        stop_loss_pct: float = 5.0,
        position_size: float = 20.0,
        symbols: Optional[List[str]] = None,
    ):
        super().__init__(symbols)
        self.lookback = lookback
        self.stop_loss_pct = stop_loss_pct
        self.position_size = position_size
        self._entry_prices: Dict[str, float] = {}

    def on_bar(self, data) -> None:
        for symbol in self.symbols:
            hist_data = self.get_historical_data(symbol, self.lookback + 5)

            if len(hist_data) < self.lookback:
                continue

            # Get recent highs and lows
            recent_highs = [d["high"] for d in hist_data[-self.lookback:-1]]
            recent_lows = [d["low"] for d in hist_data[-self.lookback:-1]]

            if not recent_highs or not recent_lows:
                continue

            highest = max(recent_highs)
            lowest = min(recent_lows)
            current_price = data.get_price(symbol)

            if current_price is None:
                continue

            if self.has_position(symbol):
                # Check stop loss
                entry = self._entry_prices.get(symbol, current_price)
                loss_pct = ((entry - current_price) / entry) * 100

                if loss_pct >= self.stop_loss_pct:
                    self.close_position(symbol)
                    self.record_signal("SELL", symbol, {
                        "reason": "Stop loss hit",
                        "loss_pct": loss_pct,
                    })
                    if symbol in self._entry_prices:
                        del self._entry_prices[symbol]

                # Check breakdown
                elif current_price < lowest:
                    self.close_position(symbol)
                    self.record_signal("SELL", symbol, {
                        "reason": "Breakdown below support",
                        "support": lowest,
                    })
                    if symbol in self._entry_prices:
                        del self._entry_prices[symbol]

            else:
                # Check for breakout
                if current_price > highest:
                    amount = self.equity * (self.position_size / 100)
                    self.buy(symbol, amount=amount)
                    self._entry_prices[symbol] = current_price
                    self.record_signal("BUY", symbol, {
                        "reason": "Breakout above resistance",
                        "resistance": highest,
                    })

    def get_parameters(self) -> dict:
        return {
            "lookback": self.lookback,
            "stop_loss_pct": self.stop_loss_pct,
            "position_size": self.position_size,
        }


def main():
    print("=" * 60)
    print("CUSTOM STRATEGY EXAMPLE")
    print("=" * 60)

    # Generate sample data
    print("\nGenerating market data...")
    data = generate_sample_data(
        symbols=["AAPL", "GOOGL", "MSFT", "NVDA", "AMZN"],
        start_date="2023-01-01",
        end_date="2024-01-01",
        seed=42,
    )

    # Test Dual Momentum Strategy
    print("\n" + "-" * 60)
    print("Testing: Dual Momentum Strategy")
    print("-" * 60)

    engine = BacktestEngine(initial_cash=100000)
    engine.load_data(data)
    engine.set_strategy(DualMomentumStrategy(
        lookback=60,
        top_n=2,
        position_size=40.0,
    ))
    results = engine.run()
    results.metrics.print_summary()

    # Test Breakout Strategy
    print("\n" + "-" * 60)
    print("Testing: Breakout Strategy")
    print("-" * 60)

    engine = BacktestEngine(initial_cash=100000)
    engine.load_data(data)
    engine.set_strategy(BreakoutStrategy(
        lookback=20,
        stop_loss_pct=5.0,
        position_size=20.0,
    ))
    results = engine.run()
    results.metrics.print_summary()

    print("\n" + "=" * 60)
    print("Custom strategy example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

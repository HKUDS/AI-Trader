"""
Backtesting Engine - Core module for running strategy backtests.

This module provides a complete backtesting framework including:
- Event-driven backtesting
- Support for multiple strategies
- Commission and slippage modeling
- Comprehensive results tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Type, Callable, Any
import json
from pathlib import Path

from .portfolio import Portfolio
from .order import Order, OrderType, OrderSide
from .metrics import PerformanceMetrics


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    initial_cash: float = 100000.0
    commission_rate: float = 0.001  # 0.1%
    slippage_rate: float = 0.0005  # 0.05%
    allow_shorting: bool = False
    max_position_size: float = 0.25  # Max 25% of portfolio in single position
    risk_free_rate: float = 0.02  # 2% annual
    benchmark_symbol: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "initial_cash": self.initial_cash,
            "commission_rate": self.commission_rate,
            "slippage_rate": self.slippage_rate,
            "allow_shorting": self.allow_shorting,
            "max_position_size": self.max_position_size,
            "risk_free_rate": self.risk_free_rate,
            "benchmark_symbol": self.benchmark_symbol,
        }


@dataclass
class MarketData:
    """Container for market data at a point in time."""
    timestamp: datetime
    prices: Dict[str, dict]  # symbol -> {open, high, low, close, volume}

    def get_price(self, symbol: str, price_type: str = "close") -> Optional[float]:
        """Get price for a symbol."""
        if symbol in self.prices:
            return self.prices[symbol].get(price_type)
        return None

    def get_ohlcv(self, symbol: str) -> Optional[dict]:
        """Get full OHLCV data for a symbol."""
        return self.prices.get(symbol)


class BacktestEngine:
    """
    Event-driven backtesting engine.

    This engine simulates trading over historical data, executing
    strategy signals and tracking portfolio performance.

    Example usage:
        ```python
        from quant_backtest import BacktestEngine
        from quant_backtest.strategies import SMAStrategy

        # Create engine
        engine = BacktestEngine(initial_cash=100000)

        # Load data
        engine.load_data(data_dict)

        # Set strategy
        engine.set_strategy(SMAStrategy(fast_period=10, slow_period=30))

        # Run backtest
        results = engine.run()

        # View results
        results.metrics.print_summary()
        ```
    """

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        initial_cash: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.0005,
    ):
        """
        Initialize the backtesting engine.

        Args:
            config: BacktestConfig object (overrides other params)
            initial_cash: Starting capital
            commission_rate: Commission as decimal (0.001 = 0.1%)
            slippage_rate: Slippage as decimal
        """
        if config:
            self.config = config
        else:
            self.config = BacktestConfig(
                initial_cash=initial_cash,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
            )

        self.portfolio = Portfolio(
            initial_cash=self.config.initial_cash,
            commission_rate=self.config.commission_rate,
            slippage_rate=self.config.slippage_rate,
        )

        self.data: Dict[str, List[dict]] = {}  # symbol -> list of OHLCV dicts
        self.timestamps: List[datetime] = []
        self.strategy = None
        self.results: Optional[BacktestResults] = None

        # Internal state
        self._current_idx = 0
        self._current_data: Optional[MarketData] = None
        self._pending_orders: List[Order] = []
        self._signals: List[dict] = []

    def load_data(
        self,
        data: Dict[str, List[dict]],
        date_column: str = "date",
        date_format: str = "%Y-%m-%d",
    ) -> None:
        """
        Load historical market data.

        Args:
            data: Dictionary of symbol -> list of OHLCV dictionaries
                  Each dict should have: date, open, high, low, close, volume
            date_column: Name of the date column
            date_format: Format string for parsing dates

        Example data format:
            {
                "AAPL": [
                    {"date": "2024-01-01", "open": 150, "high": 152,
                     "low": 149, "close": 151, "volume": 1000000},
                    ...
                ],
                "GOOGL": [...],
            }
        """
        self.data = {}
        all_dates = set()

        for symbol, records in data.items():
            self.data[symbol] = []
            for record in records:
                # Parse date
                date_val = record.get(date_column)
                if isinstance(date_val, str):
                    try:
                        dt = datetime.strptime(date_val, date_format)
                    except ValueError:
                        # Try ISO format
                        dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                elif isinstance(date_val, datetime):
                    dt = date_val
                else:
                    continue

                all_dates.add(dt)
                self.data[symbol].append({
                    "timestamp": dt,
                    "open": float(record.get("open", 0)),
                    "high": float(record.get("high", 0)),
                    "low": float(record.get("low", 0)),
                    "close": float(record.get("close", 0)),
                    "volume": float(record.get("volume", 0)),
                })

            # Sort by date
            self.data[symbol].sort(key=lambda x: x["timestamp"])

        # Create unified timestamp list
        self.timestamps = sorted(list(all_dates))

    def load_data_from_df(self, df, symbol: str) -> None:
        """
        Load data from a pandas-like DataFrame.

        Args:
            df: DataFrame with columns: date/Date, open/Open, high/High,
                low/Low, close/Close, volume/Volume
            symbol: Symbol name for this data
        """
        records = []

        # Handle different column naming conventions
        date_cols = ["date", "Date", "datetime", "Datetime", "timestamp"]
        date_col = next((c for c in date_cols if c in df.columns), None)

        if date_col is None and hasattr(df, 'index'):
            # Use index as date
            for idx, row in df.iterrows():
                record = {
                    "date": idx if isinstance(idx, (str, datetime)) else str(idx),
                    "open": row.get("open", row.get("Open", 0)),
                    "high": row.get("high", row.get("High", 0)),
                    "low": row.get("low", row.get("Low", 0)),
                    "close": row.get("close", row.get("Close", 0)),
                    "volume": row.get("volume", row.get("Volume", 0)),
                }
                records.append(record)
        else:
            for _, row in df.iterrows():
                record = {
                    "date": row.get(date_col, ""),
                    "open": row.get("open", row.get("Open", 0)),
                    "high": row.get("high", row.get("High", 0)),
                    "low": row.get("low", row.get("Low", 0)),
                    "close": row.get("close", row.get("Close", 0)),
                    "volume": row.get("volume", row.get("Volume", 0)),
                }
                records.append(record)

        if symbol not in self.data:
            self.data = {symbol: records}
        else:
            self.data[symbol] = records

        self.load_data(self.data)

    def set_strategy(self, strategy: "BaseStrategy") -> None:
        """
        Set the trading strategy to backtest.

        Args:
            strategy: A strategy instance inheriting from BaseStrategy
        """
        self.strategy = strategy
        self.strategy.set_engine(self)

    def get_historical_data(
        self,
        symbol: str,
        lookback: int = 100,
        end_idx: Optional[int] = None,
    ) -> List[dict]:
        """
        Get historical data for a symbol up to current point.

        Args:
            symbol: Ticker symbol
            lookback: Number of bars to return
            end_idx: End index (defaults to current)

        Returns:
            List of OHLCV dictionaries
        """
        if symbol not in self.data:
            return []

        if end_idx is None:
            end_idx = self._current_idx

        symbol_data = self.data[symbol]

        # Find data up to current timestamp
        current_ts = self.timestamps[end_idx] if end_idx < len(self.timestamps) else None
        if current_ts is None:
            return []

        filtered = [d for d in symbol_data if d["timestamp"] <= current_ts]
        return filtered[-lookback:] if len(filtered) > lookback else filtered

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current close price for a symbol."""
        if self._current_data:
            return self._current_data.get_price(symbol, "close")
        return None

    def get_current_prices(self) -> Dict[str, float]:
        """Get current prices for all symbols."""
        if self._current_data:
            return {
                symbol: data.get("close", 0)
                for symbol, data in self._current_data.prices.items()
            }
        return {}

    def buy(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        amount: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Optional[Order]:
        """
        Place a buy order.

        Args:
            symbol: Ticker symbol to buy
            quantity: Number of shares (mutually exclusive with amount)
            amount: Dollar amount to invest (calculates quantity)
            order_type: Type of order
            limit_price: Limit price for limit orders

        Returns:
            Order object if created successfully
        """
        price = self.get_current_price(symbol)
        if price is None or price <= 0:
            return None

        # Calculate quantity from amount if provided
        if amount is not None and quantity is None:
            quantity = amount / price

        if quantity is None or quantity <= 0:
            return None

        # Check position size limit
        order_value = quantity * price
        max_position = self.portfolio.total_equity * self.config.max_position_size
        current_position_value = 0

        pos = self.portfolio.get_position(symbol)
        if pos:
            current_position_value = pos.market_value

        if current_position_value + order_value > max_position:
            # Reduce quantity to fit within limit
            allowed_value = max_position - current_position_value
            if allowed_value <= 0:
                return None
            quantity = allowed_value / price

        order = Order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            timestamp=self.timestamps[self._current_idx] if self._current_idx < len(self.timestamps) else datetime.now(),
        )

        self._pending_orders.append(order)
        return order

    def sell(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        percent: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Optional[Order]:
        """
        Place a sell order.

        Args:
            symbol: Ticker symbol to sell
            quantity: Number of shares (mutually exclusive with percent)
            percent: Percentage of position to sell (0-100)
            order_type: Type of order
            limit_price: Limit price for limit orders

        Returns:
            Order object if created successfully
        """
        pos = self.portfolio.get_position(symbol)
        if not pos or pos.quantity <= 0:
            return None

        # Calculate quantity from percent if provided
        if percent is not None and quantity is None:
            quantity = pos.quantity * (percent / 100)

        if quantity is None:
            quantity = pos.quantity  # Sell all by default

        quantity = min(quantity, pos.quantity)  # Can't sell more than held

        if quantity <= 0:
            return None

        order = Order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            timestamp=self.timestamps[self._current_idx] if self._current_idx < len(self.timestamps) else datetime.now(),
        )

        self._pending_orders.append(order)
        return order

    def _process_orders(self) -> None:
        """Process all pending orders."""
        for order in self._pending_orders:
            price = self.get_current_price(order.symbol)
            if price is None:
                order.reject("No price available")
                continue

            # For market orders, execute immediately
            if order.order_type == OrderType.MARKET:
                self.portfolio.execute_order(order, price)

            # For limit orders, check if price condition is met
            elif order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY and price <= order.limit_price:
                    self.portfolio.execute_order(order, price)
                elif order.side == OrderSide.SELL and price >= order.limit_price:
                    self.portfolio.execute_order(order, price)

        self._pending_orders.clear()

    def run(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> "BacktestResults":
        """
        Run the backtest.

        Args:
            start_date: Start date for backtest (optional)
            end_date: End date for backtest (optional)
            progress_callback: Callback function(current, total) for progress

        Returns:
            BacktestResults object with performance data
        """
        if not self.strategy:
            raise ValueError("No strategy set. Call set_strategy() first.")

        if not self.data or not self.timestamps:
            raise ValueError("No data loaded. Call load_data() first.")

        # Filter timestamps by date range
        timestamps = self.timestamps
        if start_date:
            timestamps = [t for t in timestamps if t >= start_date]
        if end_date:
            timestamps = [t for t in timestamps if t <= end_date]

        if not timestamps:
            raise ValueError("No data in specified date range.")

        # Reset state
        self.portfolio.reset()
        self._signals.clear()

        # Initialize strategy
        self.strategy.initialize()

        total_bars = len(timestamps)

        # Main backtest loop
        for i, timestamp in enumerate(timestamps):
            self._current_idx = self.timestamps.index(timestamp)

            # Build current market data
            prices = {}
            for symbol, symbol_data in self.data.items():
                for bar in symbol_data:
                    if bar["timestamp"] == timestamp:
                        prices[symbol] = {
                            "open": bar["open"],
                            "high": bar["high"],
                            "low": bar["low"],
                            "close": bar["close"],
                            "volume": bar["volume"],
                        }
                        break

            self._current_data = MarketData(timestamp=timestamp, prices=prices)

            # Update portfolio prices
            current_prices = {s: p.get("close", 0) for s, p in prices.items()}
            self.portfolio.update_prices(current_prices)

            # Execute strategy
            self.strategy.on_bar(self._current_data)

            # Process any orders generated
            self._process_orders()

            # Record equity
            self.portfolio.record_equity(timestamp)

            # Progress callback
            if progress_callback:
                progress_callback(i + 1, total_bars)

        # Finalize strategy
        self.strategy.finalize()

        # Calculate metrics
        metrics = PerformanceMetrics(
            equity_curve=self.portfolio.equity_curve,
            trades=self.portfolio.get_trade_history_df(),
            risk_free_rate=self.config.risk_free_rate,
        )

        # Create results
        self.results = BacktestResults(
            config=self.config,
            portfolio=self.portfolio,
            metrics=metrics,
            signals=self._signals,
            strategy_name=self.strategy.__class__.__name__,
            strategy_params=self.strategy.get_parameters(),
        )

        return self.results

    def record_signal(self, signal_type: str, symbol: str, details: dict = None) -> None:
        """Record a trading signal for analysis."""
        self._signals.append({
            "timestamp": self.timestamps[self._current_idx].isoformat() if self._current_idx < len(self.timestamps) else None,
            "type": signal_type,
            "symbol": symbol,
            "details": details or {},
        })


@dataclass
class BacktestResults:
    """Container for backtest results."""
    config: BacktestConfig
    portfolio: Portfolio
    metrics: PerformanceMetrics
    signals: List[dict]
    strategy_name: str
    strategy_params: dict

    def get_summary(self) -> dict:
        """Get comprehensive results summary."""
        return {
            "strategy": {
                "name": self.strategy_name,
                "parameters": self.strategy_params,
            },
            "config": self.config.to_dict(),
            "performance": self.metrics.get_summary(),
            "portfolio": self.portfolio.to_dict(),
            "signals_count": len(self.signals),
        }

    def get_equity_curve(self) -> List[dict]:
        """Get equity curve as list of dictionaries."""
        return [
            {"timestamp": ts.isoformat(), "equity": eq}
            for ts, eq in self.portfolio.equity_curve
        ]

    def get_trades(self) -> List[dict]:
        """Get trade history."""
        return self.portfolio.get_trade_history_df()

    def save(self, filepath: str) -> None:
        """Save results to JSON file."""
        results = self.get_summary()
        results["equity_curve"] = self.get_equity_curve()
        results["trades"] = self.get_trades()
        results["signals"] = self.signals

        with open(filepath, "w") as f:
            json.dump(results, f, indent=2, default=str)

    def print_summary(self) -> None:
        """Print formatted results summary."""
        print(f"\n{'=' * 60}")
        print(f"BACKTEST RESULTS: {self.strategy_name}")
        print(f"{'=' * 60}")
        print(f"\nStrategy Parameters: {self.strategy_params}")
        self.metrics.print_summary()

    def __repr__(self) -> str:
        return (f"BacktestResults(strategy={self.strategy_name}, "
                f"return={self.metrics.total_return:.2f}%, "
                f"sharpe={self.metrics.sharpe_ratio:.3f})")

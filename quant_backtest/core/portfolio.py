"""
Portfolio management module for tracking positions, cash, and trades.

This module provides comprehensive portfolio tracking with support for:
- Multiple positions across different assets
- Cash management
- Trade history
- Position sizing
- Risk management
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json

from .order import Order, OrderSide, OrderStatus


@dataclass
class Position:
    """
    Represents a position in a single asset.

    Attributes:
        symbol: Asset ticker symbol
        quantity: Number of shares/units held
        avg_cost: Average cost basis per share
        current_price: Latest market price
        unrealized_pnl: Unrealized profit/loss
        realized_pnl: Realized profit/loss from closed trades
    """
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0
    realized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        """Calculate current market value of position."""
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        """Calculate total cost basis."""
        return self.quantity * self.avg_cost

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized profit/loss."""
        if self.quantity == 0:
            return 0.0
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized P&L as percentage."""
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100

    def update_price(self, price: float) -> None:
        """Update the current market price."""
        self.current_price = price

    def add_shares(self, quantity: float, price: float) -> None:
        """
        Add shares to position (buying).

        Args:
            quantity: Number of shares to add
            price: Purchase price per share
        """
        if quantity <= 0:
            return

        total_cost = (self.quantity * self.avg_cost) + (quantity * price)
        self.quantity += quantity
        self.avg_cost = total_cost / self.quantity if self.quantity > 0 else 0

    def remove_shares(self, quantity: float, price: float) -> float:
        """
        Remove shares from position (selling).

        Args:
            quantity: Number of shares to remove
            price: Sale price per share

        Returns:
            Realized profit/loss from this sale
        """
        if quantity <= 0 or quantity > self.quantity:
            quantity = min(quantity, self.quantity)

        realized = (price - self.avg_cost) * quantity
        self.realized_pnl += realized
        self.quantity -= quantity

        if self.quantity <= 0:
            self.quantity = 0
            self.avg_cost = 0

        return realized

    def to_dict(self) -> dict:
        """Convert position to dictionary."""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "realized_pnl": self.realized_pnl,
        }


@dataclass
class Portfolio:
    """
    Portfolio manager for tracking all positions and cash.

    Attributes:
        initial_cash: Starting cash amount
        cash: Current cash balance
        positions: Dictionary of symbol -> Position
        trade_history: List of executed orders
        equity_curve: Historical portfolio values
        commission_rate: Trading commission as percentage
        slippage_rate: Expected slippage as percentage
    """
    initial_cash: float = 100000.0
    cash: float = field(default=None)
    positions: Dict[str, Position] = field(default_factory=dict)
    trade_history: List[Order] = field(default_factory=list)
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    commission_rate: float = 0.001  # 0.1% default commission
    slippage_rate: float = 0.0005  # 0.05% default slippage

    def __post_init__(self):
        if self.cash is None:
            self.cash = self.initial_cash

    @property
    def total_positions_value(self) -> float:
        """Calculate total market value of all positions."""
        return sum(pos.market_value for pos in self.positions.values())

    @property
    def total_equity(self) -> float:
        """Calculate total portfolio equity (cash + positions)."""
        return self.cash + self.total_positions_value

    @property
    def total_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L across all positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    @property
    def total_realized_pnl(self) -> float:
        """Calculate total realized P&L from all trades."""
        return sum(pos.realized_pnl for pos in self.positions.values())

    @property
    def total_return(self) -> float:
        """Calculate total return percentage."""
        if self.initial_cash == 0:
            return 0.0
        return ((self.total_equity - self.initial_cash) / self.initial_cash) * 100

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol, or None if not held."""
        return self.positions.get(symbol)

    def get_position_quantity(self, symbol: str) -> float:
        """Get quantity held for a symbol."""
        pos = self.positions.get(symbol)
        return pos.quantity if pos else 0.0

    def update_prices(self, prices: Dict[str, float]) -> None:
        """
        Update current prices for all positions.

        Args:
            prices: Dictionary of symbol -> current price
        """
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)

    def calculate_commission(self, order_value: float) -> float:
        """Calculate commission for an order."""
        return abs(order_value) * self.commission_rate

    def calculate_slippage(self, price: float, side: OrderSide) -> float:
        """Calculate slippage for an order."""
        slippage = price * self.slippage_rate
        return slippage if side == OrderSide.BUY else -slippage

    def can_afford(self, symbol: str, quantity: float, price: float) -> bool:
        """Check if portfolio has enough cash to buy."""
        total_cost = quantity * price
        commission = self.calculate_commission(total_cost)
        return self.cash >= (total_cost + commission)

    def execute_order(self, order: Order, current_price: float) -> bool:
        """
        Execute an order and update portfolio.

        Args:
            order: The order to execute
            current_price: Current market price for the symbol

        Returns:
            True if order was executed successfully
        """
        # Calculate slippage
        slippage = self.calculate_slippage(current_price, order.side)
        exec_price = current_price + slippage

        # Calculate commission
        order_value = order.quantity * exec_price
        commission = self.calculate_commission(order_value)

        if order.side == OrderSide.BUY:
            total_cost = order_value + commission

            if self.cash < total_cost:
                order.reject("Insufficient funds")
                return False

            # Deduct cash
            self.cash -= total_cost

            # Update or create position
            if order.symbol not in self.positions:
                self.positions[order.symbol] = Position(symbol=order.symbol)

            self.positions[order.symbol].add_shares(order.quantity, exec_price)
            self.positions[order.symbol].update_price(current_price)

        else:  # SELL
            pos = self.positions.get(order.symbol)
            if not pos or pos.quantity < order.quantity:
                order.reject("Insufficient shares")
                return False

            # Add cash (minus commission)
            self.cash += order_value - commission

            # Update position
            pos.remove_shares(order.quantity, exec_price)
            pos.update_price(current_price)

            # Remove position if fully closed
            if pos.quantity <= 0:
                del self.positions[order.symbol]

        # Mark order as filled
        order.fill(exec_price, order.quantity, commission, slippage)
        self.trade_history.append(order)

        return True

    def record_equity(self, timestamp: datetime) -> None:
        """Record current equity to the equity curve."""
        self.equity_curve.append((timestamp, self.total_equity))

    def get_holdings_summary(self) -> List[dict]:
        """Get summary of all current holdings."""
        return [pos.to_dict() for pos in self.positions.values()]

    def get_trade_history_df(self) -> List[dict]:
        """Get trade history as list of dictionaries."""
        return [order.to_dict() for order in self.trade_history]

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.cash = self.initial_cash
        self.positions.clear()
        self.trade_history.clear()
        self.equity_curve.clear()

    def to_dict(self) -> dict:
        """Convert portfolio state to dictionary."""
        return {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "total_equity": self.total_equity,
            "total_positions_value": self.total_positions_value,
            "total_return": self.total_return,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_realized_pnl": self.total_realized_pnl,
            "positions": self.get_holdings_summary(),
            "num_trades": len(self.trade_history),
            "commission_rate": self.commission_rate,
            "slippage_rate": self.slippage_rate,
        }

    def save_state(self, filepath: str) -> None:
        """Save portfolio state to JSON file."""
        state = self.to_dict()
        state["equity_curve"] = [
            {"timestamp": ts.isoformat(), "equity": eq}
            for ts, eq in self.equity_curve
        ]
        state["trade_history"] = self.get_trade_history_df()

        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)

    def __repr__(self) -> str:
        return (f"Portfolio(equity=${self.total_equity:,.2f}, "
                f"cash=${self.cash:,.2f}, "
                f"positions={len(self.positions)}, "
                f"return={self.total_return:.2f}%)")

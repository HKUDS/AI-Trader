"""
Order management module for the backtesting engine.

This module defines order types, sides, and the Order class
for tracking trade execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class OrderType(Enum):
    """Order execution types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order direction."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status tracking."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """
    Represents a trading order.

    Attributes:
        symbol: The ticker symbol
        side: Buy or sell
        quantity: Number of shares/units
        order_type: Type of order (market, limit, etc.)
        limit_price: Price for limit orders
        stop_price: Trigger price for stop orders
        timestamp: When the order was created
        filled_price: Actual execution price
        filled_quantity: Actual executed quantity
        status: Current order status
        order_id: Unique identifier
        commission: Trading commission/fee
        slippage: Price slippage from expected
    """
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    timestamp: Optional[datetime] = None
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    commission: float = 0.0
    slippage: float = 0.0

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.status in [OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED]

    @property
    def total_value(self) -> float:
        """Calculate total order value including commission."""
        if self.filled_price:
            return (self.filled_price * self.filled_quantity) + self.commission
        return 0.0

    def fill(self, price: float, quantity: Optional[float] = None,
             commission: float = 0.0, slippage: float = 0.0) -> None:
        """
        Fill the order at the specified price.

        Args:
            price: Execution price
            quantity: Quantity filled (defaults to full order)
            commission: Trading commission
            slippage: Price slippage
        """
        self.filled_price = price + slippage
        self.filled_quantity = quantity if quantity else self.quantity
        self.commission = commission
        self.slippage = slippage

        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED

    def cancel(self) -> None:
        """Cancel the order."""
        if self.is_active:
            self.status = OrderStatus.CANCELLED

    def reject(self, reason: str = "") -> None:
        """Reject the order."""
        self.status = OrderStatus.REJECTED

    def to_dict(self) -> dict:
        """Convert order to dictionary representation."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "filled_price": self.filled_price,
            "filled_quantity": self.filled_quantity,
            "status": self.status.value,
            "commission": self.commission,
            "slippage": self.slippage,
            "total_value": self.total_value,
        }

    def __repr__(self) -> str:
        return (f"Order({self.order_id}: {self.side.value.upper()} "
                f"{self.quantity} {self.symbol} @ {self.filled_price or 'pending'})")

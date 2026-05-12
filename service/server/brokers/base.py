"""Broker client interface shared by Pionex / CTBC / paper adapters.

The interface deliberately keeps surface area small — the copytrade
mirror path only needs `place_order` and `cancel_order`, plus an idempotent
`get_account_status` for health checks. Streaming price feeds live on
each adapter's own attributes and are not part of the abstract base.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


class BrokerAuthError(RuntimeError):
    """Raised when broker credentials are missing or rejected."""


class BrokerRateLimitError(RuntimeError):
    """Raised when the broker returns a 429 / rate-limit error."""


@dataclass
class BrokerOrder:
    """Request payload normalised across brokers."""

    symbol: str
    side: str  # 'buy' | 'sell'
    quantity: float
    order_type: str = "market"  # 'market' | 'limit'
    price: Optional[float] = None
    client_order_id: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerOrderResult:
    """Response payload normalised across brokers."""

    order_ref: str
    status: str  # 'accepted' | 'filled' | 'rejected' | 'pending'
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
    broker: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


class BrokerClient(Protocol):
    name: str

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult: ...

    def cancel_order(self, order_ref: str) -> bool: ...

    def get_account_status(self) -> dict[str, Any]: ...


_REGISTRY: dict[str, BrokerClient] = {}


def register_broker(client: BrokerClient) -> None:
    _REGISTRY[client.name] = client


def get_broker_client(name: str) -> BrokerClient:
    """Return the singleton client for `name`, lazy-instantiating on miss.

    Names: 'pionex', 'ctbc', 'paper'. Anything else raises ValueError so the
    copytrade route can return a clean 400.
    """
    if name in _REGISTRY:
        return _REGISTRY[name]

    if name == "pionex":
        from .pionex_client import PionexClient

        client = PionexClient(
            api_key=os.environ.get("PIONEX_API_KEY"),
            api_secret=os.environ.get("PIONEX_API_SECRET"),
        )
    elif name == "ctbc":
        from .ctbc_client import CtbcClient

        client = CtbcClient(
            api_key=os.environ.get("CTBC_API_KEY"),
            api_secret=os.environ.get("CTBC_API_SECRET"),
        )
    elif name == "paper":
        from .paper_client import PaperBrokerClient

        client = PaperBrokerClient()
    else:
        raise ValueError(f"unknown broker: {name}")

    register_broker(client)
    return client

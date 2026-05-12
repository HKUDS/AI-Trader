"""Broker client adapters for BW-Trader Phase 3.

All clients implement `BrokerClient` from `.base`. Two production adapters
ship: `PionexClient` (crypto, WebSocket price + REST orders) and
`CtbcClient` (TW equities, REST polling). A third `PaperBrokerClient`
shim routes orders to the in-process paper engine so the same copytrade
code path can drive both real and simulated execution.

No broker is contacted unless a user has gone through the consent flow
in `routes_copytrade.py`. See `security/no_auto_trade.py` for the policy.
"""

from .base import (
    BrokerAuthError,
    BrokerClient,
    BrokerOrder,
    BrokerOrderResult,
    BrokerRateLimitError,
    get_broker_client,
)
from .ctbc_client import CtbcClient
from .paper_client import PaperBrokerClient
from .pionex_client import PionexClient

__all__ = [
    "BrokerAuthError",
    "BrokerClient",
    "BrokerOrder",
    "BrokerOrderResult",
    "BrokerRateLimitError",
    "CtbcClient",
    "PaperBrokerClient",
    "PionexClient",
    "get_broker_client",
]

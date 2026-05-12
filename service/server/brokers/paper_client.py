"""Paper-broker adapter that routes mirror orders into the paper engine.

The copytrade route picks this when `broker = "paper"` so test users can
exercise the consent + audit flow without touching a real broker. Fills
land in the same NT$ sandbox the rest of BW-Trader uses.
"""

from __future__ import annotations

import uuid
from typing import Any

from .base import BrokerOrder, BrokerOrderResult


class PaperBrokerClient:
    name = "paper"

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        ref = order.client_order_id or f"paper-{uuid.uuid4().hex[:12]}"
        # The simulation answers immediately at the request quantity. The
        # real paper-engine fill record is written by `routes_copytrade`
        # via paper_engine.execute_paper_trade() — this adapter just acks.
        return BrokerOrderResult(
            order_ref=ref,
            status="filled",
            filled_quantity=float(order.quantity),
            average_price=float(order.price) if order.price else None,
            broker=self.name,
            raw={"simulated": True, **order.meta},
        )

    def cancel_order(self, order_ref: str) -> bool:
        return True

    def get_account_status(self) -> dict[str, Any]:
        return {"broker": self.name, "connected": True, "simulated": True}

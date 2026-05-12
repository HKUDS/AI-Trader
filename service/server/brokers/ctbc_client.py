"""CTBC (中信證券) broker client.

CTBC's public API is REST-only with polling for fills (no public WS feed),
so this client centres on `place_order` and a `poll_order_status` helper
the copytrade mirror loop can call after submission.

Auth: API key + HMAC-SHA256 over `timestamp + body`, sent in headers.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from typing import Any, Optional

from .base import (
    BrokerAuthError,
    BrokerOrder,
    BrokerOrderResult,
    BrokerRateLimitError,
)

logger = logging.getLogger(__name__)

REST_BASE = "https://api.ctbcsec.com"


class CtbcClient:
    name = "ctbc"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        rest_base: str = REST_BASE,
        requests_session: Any = None,
    ) -> None:
        self._key = api_key
        self._secret = api_secret
        self._rest_base = rest_base
        self._session = requests_session

    def _require_creds(self) -> None:
        if not self._key or not self._secret:
            raise BrokerAuthError(
                "CTBC_API_KEY / CTBC_API_SECRET not configured"
            )

    def _sign(self, body: str) -> dict[str, str]:
        self._require_creds()
        ts = str(int(time.time() * 1000))
        signature = hmac.new(
            self._secret.encode("utf-8"),
            (ts + body).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-CTBC-KEY": self._key,
            "X-CTBC-SIGN": signature,
            "X-CTBC-TS": ts,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        import json as _json

        body_str = _json.dumps(body) if body else ""
        headers = self._sign(body_str)
        url = self._rest_base + path

        if self._session is None:
            import requests

            self._session = requests.Session()

        resp = self._session.request(
            method=method,
            url=url,
            data=body_str if body else None,
            headers=headers,
            timeout=10,
        )

        if resp.status_code in (401, 403):
            raise BrokerAuthError(f"ctbc auth rejected: {resp.text[:200]}")
        if resp.status_code == 429:
            raise BrokerRateLimitError("ctbc rate limit hit")
        if resp.status_code >= 400:
            raise RuntimeError(f"ctbc {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ------------------------------------------------------------------

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        cid = order.client_order_id or f"bw-{uuid.uuid4().hex[:12]}"
        body = {
            "symbol": order.symbol,
            "side": order.side.upper(),
            "qty": int(order.quantity),
            "orderType": order.order_type.upper(),
            "clientId": cid,
        }
        if order.order_type.lower() == "limit":
            if order.price is None:
                raise ValueError("limit order requires price")
            body["price"] = float(order.price)

        data = self._request("POST", "/v1/orders", body=body)
        return BrokerOrderResult(
            order_ref=str(data.get("orderId") or cid),
            status=str(data.get("status", "pending")).lower(),
            filled_quantity=float(data.get("filledQty", 0)),
            average_price=float(data["avgPrice"]) if data.get("avgPrice") else None,
            broker=self.name,
            raw=data,
        )

    def cancel_order(self, order_ref: str) -> bool:
        data = self._request("DELETE", f"/v1/orders/{order_ref}")
        return bool(data.get("ok"))

    def poll_order_status(self, order_ref: str) -> BrokerOrderResult:
        data = self._request("GET", f"/v1/orders/{order_ref}")
        return BrokerOrderResult(
            order_ref=order_ref,
            status=str(data.get("status", "pending")).lower(),
            filled_quantity=float(data.get("filledQty", 0)),
            average_price=float(data["avgPrice"]) if data.get("avgPrice") else None,
            broker=self.name,
            raw=data,
        )

    def get_account_status(self) -> dict[str, Any]:
        try:
            data = self._request("GET", "/v1/account")
            return {"broker": self.name, "connected": True, "account": data}
        except BrokerAuthError as exc:
            return {"broker": self.name, "connected": False, "error": str(exc)}

"""Pionex (派網) broker client.

Two interaction patterns:

1. WebSocket subscribe to `wss://ws.pionex.com/wsPub` for live price ticks.
   The streaming side is best-effort and stays in `_subscribe_ws`; the
   copytrade mirror path only depends on REST.
2. REST orders against `https://api.pionex.com/api/v1` using HMAC-SHA256
   signing on `key + timestamp + path + body`.

The client is deliberately stateless aside from credentials so it can be
swapped between live and mock in tests via `requests_session=` injection.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlencode

from .base import (
    BrokerAuthError,
    BrokerOrder,
    BrokerOrderResult,
    BrokerRateLimitError,
)

logger = logging.getLogger(__name__)

REST_BASE = "https://api.pionex.com"
WS_URL = "wss://ws.pionex.com/wsPub"


class PionexClient:
    name = "pionex"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        rest_base: str = REST_BASE,
        requests_session: Any = None,
        ws_factory: Any = None,
    ) -> None:
        self._key = api_key
        self._secret = api_secret
        self._rest_base = rest_base
        self._session = requests_session
        self._ws_factory = ws_factory

    # ------------------------------------------------------------------
    # Auth + signing
    # ------------------------------------------------------------------

    def _require_creds(self) -> None:
        if not self._key or not self._secret:
            raise BrokerAuthError(
                "PIONEX_API_KEY / PIONEX_API_SECRET not configured"
            )

    def _sign(self, method: str, path: str, params: dict[str, Any], body: str) -> dict[str, str]:
        self._require_creds()
        ts = str(int(time.time() * 1000))
        query = urlencode(sorted(params.items())) if params else ""
        payload = f"{method.upper()}{path}{query}{ts}{body}"
        signature = hmac.new(
            self._secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "PIONEX-KEY": self._key,
            "PIONEX-SIGNATURE": signature,
            "PIONEX-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        import json as _json

        params = params or {}
        body_str = _json.dumps(body) if body else ""
        headers = self._sign(method, path, params, body_str)
        url = self._rest_base + path

        if self._session is None:
            import requests

            self._session = requests.Session()

        resp = self._session.request(
            method=method,
            url=url,
            params=params,
            data=body_str if body else None,
            headers=headers,
            timeout=10,
        )

        if resp.status_code == 401 or resp.status_code == 403:
            raise BrokerAuthError(f"pionex auth rejected: {resp.text[:200]}")
        if resp.status_code == 429:
            raise BrokerRateLimitError("pionex rate limit hit")
        if resp.status_code >= 400:
            raise RuntimeError(f"pionex {resp.status_code}: {resp.text[:200]}")

        return resp.json()

    # ------------------------------------------------------------------
    # Public broker interface
    # ------------------------------------------------------------------

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        cid = order.client_order_id or f"bw-{uuid.uuid4().hex[:12]}"
        body = {
            "symbol": order.symbol,
            "side": order.side.upper(),
            "type": order.order_type.upper(),
            "size": str(order.quantity),
            "clientOrderId": cid,
        }
        if order.order_type.lower() == "limit":
            if order.price is None:
                raise ValueError("limit order requires price")
            body["price"] = str(order.price)

        data = self._request("POST", "/api/v1/trade/order", body=body)
        result = data.get("data") or {}
        return BrokerOrderResult(
            order_ref=str(result.get("orderId") or cid),
            status=str(result.get("status", "accepted")).lower(),
            filled_quantity=float(result.get("filledSize", 0)),
            average_price=float(result["avgPrice"]) if result.get("avgPrice") else None,
            broker=self.name,
            raw=data,
        )

    def cancel_order(self, order_ref: str) -> bool:
        data = self._request(
            "DELETE",
            "/api/v1/trade/order",
            params={"orderId": order_ref},
        )
        return bool(data.get("result"))

    def get_account_status(self) -> dict[str, Any]:
        try:
            data = self._request("GET", "/api/v1/account/balances")
            return {"broker": self.name, "connected": True, "balances": data.get("data", [])}
        except BrokerAuthError as exc:
            return {"broker": self.name, "connected": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # WebSocket price stream (best-effort, not on the order path)
    # ------------------------------------------------------------------

    def subscribe_price(self, symbols: list[str], on_tick) -> None:
        """Start a background WS subscription. Adapter-only — copytrade
        mirror path uses REST orders, not the stream. Tests inject a fake
        `ws_factory` so we never open a real socket in CI.
        """
        import json as _json
        import threading

        def _run() -> None:
            ws = (self._ws_factory or _make_ws)(WS_URL)
            sub = {"op": "SUBSCRIBE", "topic": "TRADE", "symbols": symbols}
            ws.send(_json.dumps(sub))
            for raw in ws:
                try:
                    on_tick(_json.loads(raw))
                except Exception as exc:  # pragma: no cover
                    logger.warning("pionex ws tick error: %s", exc)

        threading.Thread(target=_run, daemon=True).start()


def _make_ws(url: str):  # pragma: no cover — exercised only in live mode
    try:
        from websocket import create_connection  # type: ignore

        return create_connection(url)
    except ImportError as exc:
        raise RuntimeError("websocket-client not installed; pip install websocket-client") from exc

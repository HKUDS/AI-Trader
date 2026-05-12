"""Pionex broker client — read-only first.

Scope on this PR:
- Public market data endpoints (klines, ticker) — no auth, no signing.
- Authenticated account balance — HMAC-SHA256 signing scaffolding.

NOT shipped here (deliberate — Phase-3 copytrade work):
- place / cancel order
- withdraw / transfer
- subaccount admin

API docs: https://pionex-doc.gitbook.io/apidocs/

IMPORTANT — signing-format caveat
---------------------------------
The exact concatenation order Pionex requires for HMAC signing varies by
endpoint family. This file implements the most-commonly-documented format:

    payload = METHOD + PATH_WITH_SORTED_QUERY + TIMESTAMP_MS + BODY

…using HMAC-SHA256(secret, payload) -> hex. Before the first real
authenticated call lands in production, the developer **must** smoke-test
`fetch_balance()` against a live Pionex API key, compare the signing against
the current docs (signing formats have changed historically), and adjust
`_sign_payload` if needed. The client raises `ValueError` if keys are missing
so call sites can't accidentally fire unsigned requests.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Optional

import requests

PIONEX_API_BASE = "https://api.pionex.com"


class PionexClient:
    """Read-only Pionex client.

    Construct with a key + secret obtained from the user's Pionex account.
    The constructor refuses empty values to keep unsigned auth requests
    from leaking through.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = PIONEX_API_BASE,
        timeout: float = 10.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required")
        if not api_secret or not api_secret.strip():
            raise ValueError("api_secret is required")
        self.api_key = api_key.strip()
        self._secret_bytes = api_secret.strip().encode("utf-8")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _timestamp_ms(self) -> str:
        return str(int(time.time() * 1000))

    def _sign_payload(self, method: str, path: str, params: dict[str, Any], body: str, ts: str) -> str:
        """HMAC-SHA256 over METHOD + PATH(+query) + TS + BODY → hex digest.

        Query parameters are sorted lexicographically by key for deterministic
        signing. Per docstring caveat, verify this matches current Pionex
        docs before using authenticated endpoints in production.
        """
        if params:
            query = "&".join(f"{k}={params[k]}" for k in sorted(params))
            path_with_query = f"{path}?{query}"
        else:
            path_with_query = path
        message = f"{method.upper()}{path_with_query}{ts}{body}"
        return hmac.new(self._secret_bytes, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def _auth_headers(self, method: str, path: str, params: dict[str, Any], body: str = "") -> dict[str, str]:
        ts = self._timestamp_ms()
        signature = self._sign_payload(method, path, params, body, ts)
        return {
            "PIONEX-KEY": self.api_key,
            "PIONEX-SIGNATURE": signature,
            "PIONEX-TIMESTAMP": ts,
        }

    # ------------------------------------------------------------------
    # Public market data — no auth
    # ------------------------------------------------------------------
    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1H",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Public klines / OHLCV. Returns [] on error.

        `symbol` example: `BTC_USDT`. `interval` is one of Pionex's documented
        granularities (`1M`, `5M`, `15M`, `30M`, `1H`, `4H`, `1D`, etc.).
        """
        path = "/api/v1/market/klines"
        params = {"symbol": symbol, "interval": interval, "limit": str(limit)}
        try:
            resp = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"[Pionex] klines {symbol} {interval} failed: {exc}")
            return []
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if isinstance(data, dict):
            data = data.get("klines") or data.get("data")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Authenticated — read-only
    # ------------------------------------------------------------------
    def fetch_balance(self) -> Optional[dict[str, Any]]:
        """Account balance (READ-ONLY).

        Returns the parsed JSON payload, or None on network / auth failure.
        Authenticated — requires a valid key/secret pair. No state mutation.
        """
        path = "/api/v1/account/balances"
        params: dict[str, Any] = {}
        headers = self._auth_headers("GET", path, params, body="")
        try:
            resp = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"[Pionex] fetch_balance failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Phase-3 deliberately-omitted endpoints — guard rails
    # ------------------------------------------------------------------
    def place_order(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "place_order is intentionally not implemented in the read-only client. "
            "It must go through the Phase-3 copytrade user-consent flow."
        )

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "cancel_order is intentionally not implemented in the read-only client. "
            "It must go through the Phase-3 copytrade user-consent flow."
        )

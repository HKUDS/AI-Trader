"""TWSE OpenAPI client for Taiwan stock prices.

Primary daily-close source for BW-Trader's TW market path. Pairs with
`finmind_client.py` as the historical-data fallback when TWSE OpenAPI doesn't
have a row for the requested date (e.g. weekend / holiday / out-of-window).

Interface contract: mirrors `price_fetcher._get_us_stock_price(symbol, executed_at)`
so call sites can route on the `market` field without per-market wiring.

TWSE OpenAPI is public and unauthenticated. Free tier; the only quota signal
is HTTP 429. We don't ship retry-with-backoff in this minimal client — the
caller (`get_price_from_market`) already wraps in a try/except and gracefully
returns None on failure.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

TWSE_API_BASE = os.environ.get(
    "TWSE_API_BASE", "https://openapi.twse.com.tw/v1"
).rstrip("/")
TWSE_TIMEOUT_SECONDS = float(os.environ.get("TWSE_TIMEOUT_SECONDS", "8"))

# Endpoint returns one row per listed company for the latest trading day.
# Sample row: {"Code": "2330", "Name": "台積電", "ClosingPrice": "1010", ...}
TWSE_STOCK_DAY_ALL = "/exchangeReport/STOCK_DAY_ALL"


def _parse_executed_at(executed_at: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _normalize_symbol(symbol: str) -> str:
    """TWSE codes are 4-6 digit numeric (sometimes followed by a letter for
    warrants / preferred). Strip whitespace and uppercase the optional suffix."""
    return (symbol or "").strip().upper()


def _coerce_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        price = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def fetch_twse_day_all() -> Optional[list[dict[str, Any]]]:
    """Fetch the latest trading-day snapshot of every listed TWSE stock.

    Returns the parsed JSON array or None on failure. Caller should handle
    the None and decide whether to retry via FinMind."""
    url = f"{TWSE_API_BASE}{TWSE_STOCK_DAY_ALL}"
    try:
        resp = requests.get(url, timeout=TWSE_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[TWSE] fetch_twse_day_all failed: {exc}")
        return None

    if not isinstance(payload, list):
        print(f"[TWSE] unexpected payload shape: {type(payload).__name__}")
        return None
    return payload


def get_tw_stock_price(symbol: str, executed_at: str) -> Optional[float]:
    """Resolve a TW stock close price for the requested datetime.

    Currently returns the most recent TWSE daily close — TWSE OpenAPI does
    not expose intraday on the free endpoint. For intraday precision a caller
    should add a realtime source (Phase 2 of the roadmap).
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None

    parsed = _parse_executed_at(executed_at)
    if parsed is None:
        return None
    # We don't currently filter by date — the OpenAPI snapshot is whatever
    # the latest closed trading day is. Document the limitation explicitly:
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    rows = fetch_twse_day_all()
    if rows is None:
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Code", "")).strip().upper()
        if code != normalized:
            continue
        price = _coerce_price(row.get("ClosingPrice"))
        if price is not None:
            return price
        # ClosingPrice may be blank pre-market — fall back to MonthlyAveragePrice
        # then OpeningPrice as a degraded signal.
        for fallback_key in ("MonthlyAveragePrice", "OpeningPrice"):
            price = _coerce_price(row.get(fallback_key))
            if price is not None:
                return price
        return None
    return None

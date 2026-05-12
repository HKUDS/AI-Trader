"""FinMind fallback client for TW historical OHLCV.

Used when `tw_market.get_tw_stock_price` cannot resolve a price (typically
because the requested date is older than TWSE OpenAPI's latest-day window).
FinMind provides daily OHLCV via `TaiwanStockPrice`.

Free tier works without a token but is rate-limited. If `FINMIND_TOKEN` is
set, it's attached as a Bearer header for the paid quota.

Reference implementation: BWStudio/services/sentinel-backtest/src/fetch_finmind.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

FINMIND_API = os.environ.get(
    "FINMIND_API", "https://api.finmindtrade.com/api/v4/data"
).rstrip("/")
FINMIND_TIMEOUT_SECONDS = float(os.environ.get("FINMIND_TIMEOUT_SECONDS", "10"))
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _parse_executed_at(executed_at: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _coerce_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def get_tw_stock_price_finmind(symbol: str, executed_at: str) -> Optional[float]:
    """Return the most recent FinMind daily close on or before executed_at.

    Queries a 14-day window ending at executed_at and picks the last row;
    that covers weekends, lunar holidays, and short trading suspensions
    without needing a calendar.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None

    parsed = _parse_executed_at(executed_at)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    end_date = parsed.date()
    start_date = end_date - timedelta(days=14)

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": normalized,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"

    try:
        resp = requests.get(
            FINMIND_API, params=params, headers=headers, timeout=FINMIND_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[FinMind] fetch failed for {normalized}: {exc}")
        return None

    if not isinstance(payload, dict) or payload.get("status") != 200:
        msg = payload.get("msg") if isinstance(payload, dict) else "non-dict payload"
        print(f"[FinMind] non-200 status for {normalized}: {msg}")
        return None

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        return None

    # FinMind returns rows in ascending date order — the last row is the
    # most recent close on or before end_date.
    last = rows[-1]
    if not isinstance(last, dict):
        return None
    return _coerce_price(last.get("close"))

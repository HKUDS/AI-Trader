"""TW stock data via the `mlouielu/twstock` library.

Adds realtime quotes + historical OHLCV + 四大買賣點 (BestFourPoint) analytics
on top of the existing TWSE OpenAPI daily-close path in `tw_market.py`.

Routing intent: callers should try realtime first for live decisions
(`fetch_realtime`), fall back to the TWSE OpenAPI snapshot already wired
in `price_fetcher.py`, then FinMind for older historical dates.

Rate limiting
=============
twstock backs onto TWSE / TPEX public endpoints, both of which 429 aggressively.
The conventional safe rate is 3 requests / 5 seconds per source. We share a
single in-process throttle window across all calls in this module.

The throttle is best-effort only — multi-process deployments need an external
rate limiter (Redis token bucket). Documented as a known limitation.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

try:
    import twstock  # type: ignore
except ImportError as exc:  # pragma: no cover - hard fail on import
    raise ImportError(
        "twstock is not installed. Add `twstock>=1.5.0` to service/requirements.txt"
        " and run `uv pip install -r service/requirements.txt`."
    ) from exc


# 3 requests / 5 second window. TWSE 429s above this for sustained traffic.
_REQ_WINDOW_SECONDS = 5.0
_REQ_LIMIT = 3
_request_times: list[float] = []
_throttle_lock = threading.Lock()


def _throttle() -> None:
    """Block until we are within the 3-req / 5-second window."""
    with _throttle_lock:
        now = time.monotonic()
        # Drop expired entries first
        cutoff = now - _REQ_WINDOW_SECONDS
        while _request_times and _request_times[0] < cutoff:
            _request_times.pop(0)
        if len(_request_times) >= _REQ_LIMIT:
            sleep_for = _REQ_WINDOW_SECONDS - (now - _request_times[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            cutoff = now - _REQ_WINDOW_SECONDS
            while _request_times and _request_times[0] < cutoff:
                _request_times.pop(0)
        _request_times.append(now)


def _reset_throttle_for_tests() -> None:
    """Reset the throttle window. Tests only."""
    with _throttle_lock:
        _request_times.clear()


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def get_stock_info(symbol: str) -> dict[str, Any]:
    """Return registry metadata for a TWSE / TPEX symbol.

    Reads from `twstock.codes` (an in-memory dict shipped with the package)
    — no network call, no throttle.
    Returns an empty dict if the symbol is unknown.
    """
    normalized = _normalize_symbol(symbol)
    info = twstock.codes.get(normalized)
    if info is None:
        return {}
    market_label = getattr(info, "market", "")
    return {
        "symbol": getattr(info, "code", normalized),
        "name": getattr(info, "name", ""),
        "market": "TWSE" if market_label == "上市" else ("TPEX" if market_label == "上櫃" else market_label),
        "group": getattr(info, "group", ""),
        "isin": getattr(info, "ISIN", ""),
        "listed_date": getattr(info, "start", ""),
        "type": getattr(info, "type", ""),
    }


def fetch_historical_prices(symbol: str, year: int, month: int) -> list[dict[str, Any]]:
    """Fetch daily OHLCV starting from (year, month).

    Wraps `twstock.Stock(sid).fetch_from(year, month)`. Returns a list of
    plain dicts (not the underlying namedtuple) to keep the boundary stable.
    Returns [] on lookup failure rather than raising — caller decides fallback.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return []
    _throttle()
    try:
        stock = twstock.Stock(normalized, initial_fetch=False)
        rows = stock.fetch_from(year, month)
    except Exception as exc:  # twstock raises various IO/decode errors
        print(f"[twstock] fetch_historical_prices {normalized} {year}/{month} failed: {exc}")
        return []
    out: list[dict[str, Any]] = []
    for row in rows or []:
        try:
            out.append({
                "date": row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.capacity),
                "turnover": int(row.turnover) if row.turnover is not None else 0,
                "transactions": int(row.transaction) if row.transaction is not None else 0,
                "change": float(row.change) if row.change is not None else 0.0,
            })
        except (AttributeError, TypeError, ValueError):
            continue
    return out


def fetch_realtime(symbol: str) -> dict[str, Any]:
    """Realtime quote via `twstock.realtime.get`.

    Returns {} when the upstream returns `success=False` or shape is unexpected.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return {}
    _throttle()
    try:
        payload = twstock.realtime.get(normalized)
    except Exception as exc:
        print(f"[twstock] realtime {normalized} failed: {exc}")
        return {}
    if not isinstance(payload, dict) or not payload.get("success"):
        return {}
    info = payload.get("info") or {}
    rt = payload.get("realtime") or {}

    def _f(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _i(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return {
        "symbol": info.get("code", normalized),
        "name": info.get("name", ""),
        "timestamp": payload.get("timestamp"),
        "latest_trade_price": _f(rt.get("latest_trade_price")),
        "trade_volume": _i(rt.get("trade_volume")),
        "open": _f(rt.get("open")),
        "high": _f(rt.get("high")),
        "low": _f(rt.get("low")),
        "accumulate_trade_volume": _i(rt.get("accumulate_trade_volume")),
    }


def get_realtime_close(symbol: str) -> Optional[float]:
    """Convenience: return only the latest trade price, or None if unavailable.

    Used by `price_fetcher.get_price_from_market` as the first probe in the
    TW path so live decisions see intraday movement instead of yesterday's
    close.
    """
    snapshot = fetch_realtime(symbol)
    price = snapshot.get("latest_trade_price") or 0
    return float(price) if price else None


def best_four_point(symbol: str) -> dict[str, Any]:
    """四大買賣點 analysis (Stock Charts trading signals).

    Returns a dict with `buy_signal`, `sell_signal`, `combined` — each either
    a (bool, str) explanation tuple from twstock, or None when twstock
    returns False (no signal).
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return {"symbol": "", "buy_signal": None, "sell_signal": None, "combined": None}
    _throttle()
    try:
        # BestFourPoint needs an already-fetched Stock (data on the instance).
        stock = twstock.Stock(normalized)
        bfp = twstock.BestFourPoint(stock)
        buy = bfp.best_four_point_to_buy()
        sell = bfp.best_four_point_to_sell()
        combined = bfp.best_four_point()
    except Exception as exc:
        print(f"[twstock] best_four_point {normalized} failed: {exc}")
        return {"symbol": normalized, "buy_signal": None, "sell_signal": None, "combined": None}

    def _coerce(value: Any) -> Optional[tuple]:
        return value if isinstance(value, tuple) else None

    return {
        "symbol": normalized,
        "buy_signal": _coerce(buy),
        "sell_signal": _coerce(sell),
        "combined": _coerce(combined),
    }

"""
Stock Price Fetcher for Server

US Stock: 从 Alpha Vantage 获取价格
Crypto: 从 Hyperliquid 获取价格（停止使用 Alpha Vantage crypto 端点）
"""

import os
import random
import requests
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, Any
import re
import time
import json
try:
    from zoneinfo import ZoneInfo
    _ET_ZONEINFO = ZoneInfo("America/New_York")
except ImportError:
    _ET_ZONEINFO = None  # Python < 3.9 fallback: use fixed offset below

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
BASE_URL = "https://www.alphavantage.co/query"

# Hyperliquid public info endpoint (no API key required for reads)
HYPERLIQUID_API_URL = os.environ.get("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info").strip()

# Polymarket public endpoints (no API key required for reads)
POLYMARKET_GAMMA_BASE_URL = os.environ.get("POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com").strip()
POLYMARKET_CLOB_BASE_URL = os.environ.get("POLYMARKET_CLOB_BASE_URL", "https://clob.polymarket.com").strip()

# London Strategic Edge (LSE) unified market data API (optional).
# One key covers US stocks, ETFs and crypto with 1m/5m OHLCV candles.
# When LSE_API_KEY is set, LSE is tried first for us-stock and crypto prices;
# the existing Alpha Vantage / yfinance / Hyperliquid paths remain as automatic
# fallbacks, so leaving the key unset changes nothing.
# Free API key: https://londonstrategicedge.com/data?ref=ai-trader
LSE_API_KEY = os.environ.get("LSE_API_KEY", "").strip()
LSE_API_BASE_URL = os.environ.get("LSE_API_BASE_URL", "https://api.londonstrategicedge.com/iso").strip()
PRICE_FETCH_TIMEOUT_SECONDS = float(os.environ.get("PRICE_FETCH_TIMEOUT_SECONDS", "10"))
PRICE_FETCH_MAX_RETRIES = max(0, int(os.environ.get("PRICE_FETCH_MAX_RETRIES", "2")))
PRICE_FETCH_BACKOFF_BASE_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_BACKOFF_BASE_SECONDS", "0.35")))
PRICE_FETCH_ERROR_COOLDOWN_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_ERROR_COOLDOWN_SECONDS", "20")))
PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS", "60")))
PRICE_FETCH_VERBOSE = os.environ.get("PRICE_FETCH_VERBOSE", "true").strip().lower() not in {"0", "false", "no", "off"}
HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS = max(60.0, float(os.environ.get("HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS", "300")))

# 时区常量
UTC = timezone.utc
# ET_TZ resolves to America/New_York (DST-aware) when zoneinfo is available.
# Falling back to a fixed UTC-5 (EST) offset is conservative — it will be 1 hour
# off during EDT (summer) but at least correct during the longer EST winter period.
# The zoneinfo path is always preferred and available on Python 3.9+.
ET_TZ = _ET_ZONEINFO if _ET_ZONEINFO is not None else timezone(timedelta(hours=-5))

_POLYMARKET_CONDITION_ID_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
_POLYMARKET_TOKEN_ID_RE = re.compile(r"^\d+$")
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_provider_cooldowns: Dict[str, float] = {}
_price_fetch_logging_enabled: ContextVar[bool] = ContextVar("price_fetch_logging_enabled", default=True)
_hyperliquid_symbol_cache: Tuple[Optional[set[str]], float] = (None, 0.0)


def _price_log(message: str) -> None:
    if PRICE_FETCH_VERBOSE and _price_fetch_logging_enabled.get():
        print(message)


@contextmanager
def price_fetch_logging(enabled: bool):
    token = _price_fetch_logging_enabled.set(enabled)
    try:
        yield
    finally:
        _price_fetch_logging_enabled.reset(token)

# Polymarket outcome prices are probabilities in [0, 1]. Reject values outside to avoid
# token_id/condition_id or other API noise being interpreted as price (e.g. 1.5e+73).
def _polymarket_price_valid(price: float) -> bool:
    if price is None or not isinstance(price, (int, float)):
        return False
    try:
        p = float(price)
        return 0 <= p <= 1
    except (TypeError, ValueError):
        return False

# In-memory cache for Polymarket reference+outcome -> (token_id, expiry_epoch_s)
_polymarket_token_cache: Dict[str, Tuple[str, float]] = {}
_polymarket_market_cache: Dict[str, Tuple[Optional[dict], float]] = {}
_POLYMARKET_TOKEN_CACHE_TTL_S = 300.0
_POLYMARKET_MARKET_CACHE_TTL_S = 300.0


def _provider_cooldown_remaining(provider: str) -> float:
    return max(0.0, _provider_cooldowns.get(provider, 0.0) - time.time())


def _activate_provider_cooldown(provider: str, duration_s: float, reason: str) -> None:
    if duration_s <= 0:
        return
    until = time.time() + duration_s
    previous_until = _provider_cooldowns.get(provider, 0.0)
    _provider_cooldowns[provider] = max(previous_until, until)
    remaining = _provider_cooldown_remaining(provider)
    _price_log(f"[Price API] {provider} cooldown {remaining:.1f}s ({reason})")


def _retry_delay(attempt: int) -> float:
    if PRICE_FETCH_BACKOFF_BASE_SECONDS <= 0:
        return 0.0
    base = PRICE_FETCH_BACKOFF_BASE_SECONDS * (2 ** attempt)
    return base + random.uniform(0.0, base * 0.25)


def _request_json_with_retry(
    provider: str,
    method: str,
    url: str,
    *,
    params: Optional[object] = None,
    json_payload: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> object:
    remaining = _provider_cooldown_remaining(provider)
    if remaining > 0:
        raise RuntimeError(f"{provider} cooldown active for {remaining:.1f}s")

    last_exc: Optional[Exception] = None
    attempts = PRICE_FETCH_MAX_RETRIES + 1

    for attempt in range(attempts):
        try:
            if method == "POST":
                resp = requests.post(url, json=json_payload, headers=headers, timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            else:
                resp = requests.get(url, params=params, headers=headers, timeout=PRICE_FETCH_TIMEOUT_SECONDS)

            if resp.status_code in _RETRYABLE_STATUS_CODES:
                resp.raise_for_status()

            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            retryable = status_code in _RETRYABLE_STATUS_CODES
            last_exc = exc

            if retryable and attempt < attempts - 1:
                delay = _retry_delay(attempt)
                _price_log(
                    f"[Price API] {provider} retry {attempt + 1}/{attempts - 1} "
                    f"after HTTP {status_code}; sleeping {delay:.2f}s"
                )
                if delay > 0:
                    time.sleep(delay)
                continue

            if status_code == 429:
                _activate_provider_cooldown(
                    provider,
                    PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS,
                    "HTTP 429"
                )
            elif status_code is not None and status_code >= 500:
                _activate_provider_cooldown(
                    provider,
                    PRICE_FETCH_ERROR_COOLDOWN_SECONDS,
                    f"HTTP {status_code}"
                )
            raise
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                delay = _retry_delay(attempt)
                _price_log(
                    f"[Price API] {provider} retry {attempt + 1}/{attempts - 1} "
                    f"after {exc.__class__.__name__}; sleeping {delay:.2f}s"
                )
                if delay > 0:
                    time.sleep(delay)
                continue
            _activate_provider_cooldown(
                provider,
                PRICE_FETCH_ERROR_COOLDOWN_SECONDS,
                exc.__class__.__name__
            )
            raise
        except requests.RequestException as exc:
            last_exc = exc
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{provider} request failed without response")


def _polymarket_market_title(market: Optional[dict]) -> Optional[str]:
    if not isinstance(market, dict):
        return None
    for key in ("question", "title", "description", "slug"):
        value = market.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def describe_polymarket_contract(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[dict]:
    """
    Return human-readable Polymarket metadata for UI/documentation.
    """
    contract = _polymarket_resolve_reference(reference, token_id=token_id, outcome=outcome)
    if not contract:
        return None

    market = contract.get("market")
    resolved_outcome = contract.get("outcome")
    market_title = _polymarket_market_title(market)
    market_slug = market.get("slug") if isinstance(market, dict) else None
    display_title = market_title or market_slug or reference
    if resolved_outcome:
        display_title = f"{display_title} [{resolved_outcome}]"

    return {
        "token_id": contract.get("token_id"),
        "outcome": resolved_outcome,
        "market_title": market_title,
        "market_slug": market_slug,
        "display_title": display_title,
    }

def _parse_executed_at_to_utc(executed_at: str) -> Optional[datetime]:
    """
    Parse executed_at into an aware UTC datetime.
    Accepts:
    - 2026-03-07T14:30:00Z
    - 2026-03-07T14:30:00+00:00
    - 2026-03-07T14:30:00   (treated as UTC)
    """
    try:
        cleaned = executed_at.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def _normalize_hyperliquid_symbol(symbol: str) -> str:
    """
    Best-effort normalization for Hyperliquid 'coin' identifiers.
    Examples:
    - 'btc' -> 'BTC'
    - 'BTC-USD' -> 'BTC'
    - 'BTC/USD' -> 'BTC'
    - 'BTC-PERP' -> 'BTC'
    - 'xyz:NVDA' -> 'xyz:NVDA' (keep dex-prefixed builder listings)
    """
    raw = symbol.strip()
    if ":" in raw:
        return raw  # builder/dex symbols are case sensitive upstream; keep as-is

    s = raw.upper()
    for suffix in ("-PERP", "PERP"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break

    for sep in ("-USD", "/USD"):
        if s.endswith(sep):
            s = s[: -len(sep)]
            break

    for sep in ("-USDT", "/USDT"):
        if s.endswith(sep):
            s = s[: -len(sep)]
            break

    if s.endswith("USDT") and len(s) > len("USDT"):
        s = s[: -len("USDT")]

    return s.strip()


def _hyperliquid_post(payload: dict) -> object:
    if not HYPERLIQUID_API_URL:
        raise RuntimeError("HYPERLIQUID_API_URL is empty")
    return _request_json_with_retry(
        "hyperliquid",
        "POST",
        HYPERLIQUID_API_URL,
        json_payload=payload,
    )


def _get_hyperliquid_available_symbols() -> Optional[set[str]]:
    global _hyperliquid_symbol_cache

    cached_symbols, expires_at = _hyperliquid_symbol_cache
    now = time.time()
    if expires_at > now:
        return cached_symbols

    try:
        data = _hyperliquid_post({"type": "meta"})
    except Exception:
        _hyperliquid_symbol_cache = (None, now + 30.0)
        return None

    symbols: set[str] = set()
    if isinstance(data, dict):
        universe = data.get("universe")
        if isinstance(universe, list):
            for asset in universe:
                if isinstance(asset, dict):
                    name = str(asset.get("name") or "").strip()
                    if name:
                        symbols.add(name)

    _hyperliquid_symbol_cache = (symbols or None, now + HYPERLIQUID_SYMBOL_CACHE_TTL_SECONDS)
    return symbols or None


def _hyperliquid_symbol_available(coin: str) -> bool:
    symbols = _get_hyperliquid_available_symbols()
    if symbols is None:
        return True
    return coin in symbols


def _polymarket_get_json(url: str, params: Optional[dict] = None) -> object:
    return _request_json_with_retry(
        "polymarket",
        "GET",
        url,
        params=params,
    )


def _parse_string_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if isinstance(v, (str, int)) and str(v).strip()]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if isinstance(v, (str, int)) and str(v).strip()]
        except Exception:
            return []
    return []


def _polymarket_fetch_market(reference: str, token_id: Optional[str] = None) -> Optional[dict]:
    if not POLYMARKET_GAMMA_BASE_URL:
        return None

    ref = (reference or "").strip()
    requested_token_id = (token_id or "").strip()
    if not ref and not requested_token_id:
        return None

    cache_key = f"{ref}::{requested_token_id}"
    now = time.time()
    cached = _polymarket_market_cache.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    url = f"{POLYMARKET_GAMMA_BASE_URL.rstrip('/')}/markets"
    params = {"limit": "1"}
    if requested_token_id and _POLYMARKET_TOKEN_ID_RE.match(requested_token_id):
        params["clob_token_ids"] = requested_token_id
    elif _POLYMARKET_CONDITION_ID_RE.match(ref):
        params["conditionId"] = ref
    elif _POLYMARKET_TOKEN_ID_RE.match(ref):
        params["clob_token_ids"] = ref
    else:
        params["slug"] = ref

    try:
        raw = _polymarket_get_json(url, params=params)
    except Exception:
        _polymarket_market_cache[cache_key] = (None, now + 60.0)
        return None

    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        _polymarket_market_cache[cache_key] = (None, now + _POLYMARKET_MARKET_CACHE_TTL_S)
        return None
    market = raw[0]
    _polymarket_market_cache[cache_key] = (market, now + _POLYMARKET_MARKET_CACHE_TTL_S)
    return market


def _polymarket_extract_tokens(market: dict) -> list[dict[str, Optional[str]]]:
    token_ids = _parse_string_array(market.get("clobTokenIds")) or _parse_string_array(market.get("clob_token_ids"))
    outcomes = _parse_string_array(market.get("outcomes"))
    extracted: list[dict[str, Optional[str]]] = []
    for idx, token_id in enumerate(token_ids):
        if token_id and _POLYMARKET_TOKEN_ID_RE.match(token_id):
            extracted.append({
                "token_id": token_id,
                "outcome": outcomes[idx] if idx < len(outcomes) else None,
            })
    return extracted


def _polymarket_resolve_reference(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[dict]:
    """
    Resolve a Polymarket reference into an explicit outcome token.

    For ambiguous references (slug/condition with multiple outcomes), caller must provide
    either `token_id` or `outcome`.
    """
    ref = (reference or "").strip()
    if not ref:
        return None

    requested_token_id = (token_id or "").strip()
    requested_outcome = (outcome or "").strip().lower()
    cache_key = f"{ref}::{(token_id or '').strip().lower()}::{(outcome or '').strip().lower()}"
    cached = _polymarket_token_cache.get(cache_key)
    now = time.time()
    if cached and cached[1] > now:
        return {
            "token_id": cached[0],
            "outcome": outcome,
            "market": _polymarket_fetch_market(ref, token_id=requested_token_id),
        }

    market = _polymarket_fetch_market(ref, token_id=requested_token_id)
    if not market:
        return None

    tokens = _polymarket_extract_tokens(market)

    selected = None
    if requested_token_id and _POLYMARKET_TOKEN_ID_RE.match(requested_token_id):
        for candidate in tokens:
            if candidate["token_id"] == requested_token_id:
                selected = candidate
                break
        if selected is None and not tokens:
            selected = {"token_id": requested_token_id, "outcome": outcome}
    if selected is None and _POLYMARKET_TOKEN_ID_RE.match(ref):
        selected = {"token_id": ref, "outcome": outcome}
    if selected is None and requested_outcome:
        for candidate in tokens:
            if (candidate.get("outcome") or "").strip().lower() == requested_outcome:
                selected = candidate
                break
    if selected is None and len(tokens) == 1:
        selected = tokens[0]

    if not selected or not selected.get("token_id"):
        return None

    resolved_token_id = str(selected["token_id"])
    _polymarket_token_cache[cache_key] = (resolved_token_id, now + _POLYMARKET_TOKEN_CACHE_TTL_S)
    return {
        "token_id": resolved_token_id,
        "outcome": selected.get("outcome"),
        "market": market,
    }


def _get_polymarket_mid_price(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[float]:
    """
    Fetch a mid price for a Polymarket outcome token.
    Price is derived from best bid/ask in the CLOB orderbook.
    """
    if not POLYMARKET_CLOB_BASE_URL:
        return None

    contract = _polymarket_resolve_reference(reference, token_id=token_id, outcome=outcome)
    if not contract:
        return None
    resolved_token_id = contract["token_id"]

    url = f"{POLYMARKET_CLOB_BASE_URL.rstrip('/')}/book"
    data = None
    try:
        data = _polymarket_get_json(url, params={"token_id": resolved_token_id})
    except Exception:
        data = None

    if isinstance(data, dict):
        bids = data.get("bids") if isinstance(data.get("bids"), list) else []
        asks = data.get("asks") if isinstance(data.get("asks"), list) else []

        def _level_prices(levels: list) -> list[float]:
            prices = []
            for level in levels:
                if isinstance(level, dict) and "price" in level:
                    try:
                        price = float(level["price"])
                    except Exception:
                        continue
                    if _polymarket_price_valid(price):
                        prices.append(price)
            return prices

        def _best_bid(levels: list) -> Optional[float]:
            prices = _level_prices(levels)
            return max(prices) if prices else None

        def _best_ask(levels: list) -> Optional[float]:
            prices = _level_prices(levels)
            return min(prices) if prices else None

        best_bid = _best_bid(bids)
        best_ask = _best_ask(asks)
        if best_bid is not None or best_ask is not None:
            mid = (best_bid + best_ask) / 2 if (best_bid is not None and best_ask is not None) else (best_bid if best_bid is not None else best_ask)
            mid = float(f"{mid:.6f}")
            if _polymarket_price_valid(mid):
                return mid
            return None

    # Fallback: use Gamma market fields when CLOB orderbook is missing.
    market = contract.get("market")
    if not isinstance(market, dict):
        return None
    try:
        outcome_prices = _parse_string_array(market.get("outcomePrices"))
        outcomes = _parse_string_array(market.get("outcomes"))
        target_outcome = (contract.get("outcome") or "").strip().lower()
        if target_outcome and outcome_prices and outcomes:
            for idx, label in enumerate(outcomes):
                if label.strip().lower() == target_outcome and idx < len(outcome_prices):
                    p = float(f"{float(outcome_prices[idx]):.6f}")
                    if _polymarket_price_valid(p):
                        return p
        for key in ("lastTradePrice", "outcomePrice"):
            v = market.get(key)
            if isinstance(v, (int, float)):
                p = float(f"{float(v):.6f}")
                if _polymarket_price_valid(p):
                    return p
            if isinstance(v, str) and v.strip():
                try:
                    p = float(f"{float(v):.6f}")
                    if _polymarket_price_valid(p):
                        return p
                except Exception:
                    pass
    except Exception:
        pass

    return None


def _polymarket_resolve(reference: str, token_id: Optional[str] = None, outcome: Optional[str] = None) -> Optional[dict]:
    """
    Resolve a Polymarket market via Gamma.
    Returns dict: { resolved: bool, outcome: Optional[str], settlementPrice: Optional[float] } or None.
    """
    contract = _polymarket_resolve_reference(reference, token_id=token_id, outcome=outcome)
    if not contract:
        return None
    market = contract.get("market")
    if not isinstance(market, dict):
        return None

    resolved_flag = bool(market.get("resolved"))
    resolved_outcome = market.get("outcome") if isinstance(market.get("outcome"), str) else None
    settlement_raw = market.get("settlementPrice")
    settlement_price = None
    if isinstance(settlement_raw, (int, float)):
        settlement_price = float(settlement_raw)
    elif isinstance(settlement_raw, str) and settlement_raw.strip():
        try:
            settlement_price = float(settlement_raw)
        except Exception:
            settlement_price = None
    if settlement_price is not None and not _polymarket_price_valid(settlement_price):
        settlement_price = None

    return {
        "resolved": resolved_flag,
        "token_id": contract.get("token_id"),
        "outcome": contract.get("outcome"),
        "market_slug": market.get("slug"),
        "resolved_outcome": resolved_outcome,
        "settlementPrice": settlement_price,
    }


def _get_hyperliquid_mid_price(symbol: str) -> Optional[float]:
    """
    Fetch mid price from Hyperliquid L2 book.
    This is used for 'now' style queries.
    """
    coin = _normalize_hyperliquid_symbol(symbol)
    if not _hyperliquid_symbol_available(coin):
        _price_log(f"[Price API] Hyperliquid symbol not listed: {symbol} -> {coin}")
        return None

    data = _hyperliquid_post({"type": "l2Book", "coin": coin})
    if not isinstance(data, dict) or "levels" not in data:
        return None
    levels = data.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        return None
    bids = levels[0] if isinstance(levels[0], list) else []
    asks = levels[1] if isinstance(levels[1], list) else []
    best_bid = None
    best_ask = None
    if bids and isinstance(bids[0], dict) and "px" in bids[0]:
        try:
            best_bid = float(bids[0]["px"])
        except Exception:
            best_bid = None
    if asks and isinstance(asks[0], dict) and "px" in asks[0]:
        try:
            best_ask = float(asks[0]["px"])
        except Exception:
            best_ask = None
    if best_bid is None and best_ask is None:
        return None
    if best_bid is not None and best_ask is not None:
        return float(f"{((best_bid + best_ask) / 2):.6f}")
    return float(f"{(best_bid if best_bid is not None else best_ask):.6f}")


def _get_hyperliquid_candle_close(symbol: str, executed_at: str) -> Optional[float]:
    """
    Fetch a 1m candle around executed_at via candleSnapshot and return the closest close.
    This approximates "price at time" without requiring any private keys.
    """
    dt = _parse_executed_at_to_utc(executed_at)
    if not dt:
        return None

    # Query a small window around the target time (±10 minutes)
    target_ms = int(dt.timestamp() * 1000)
    start_ms = target_ms - 10 * 60 * 1000
    end_ms = target_ms + 10 * 60 * 1000

    coin = _normalize_hyperliquid_symbol(symbol)
    if not _hyperliquid_symbol_available(coin):
        _price_log(f"[Price API] Hyperliquid symbol not listed: {symbol} -> {coin}")
        return None

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": "1m",
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }
    data = _hyperliquid_post(payload)
    if not isinstance(data, list) or len(data) == 0:
        return None

    closest = None
    closest_ts = None
    for candle in data:
        if not isinstance(candle, dict):
            continue
        t = candle.get("t")
        c = candle.get("c")
        if t is None or c is None:
            continue
        try:
            t_ms = int(float(t))
            close = float(c)
        except Exception:
            continue
        if t_ms > target_ms:
            continue
        if closest_ts is None or t_ms > closest_ts:
            closest_ts = t_ms
            closest = close

    if closest is None:
        return None
    return float(f"{closest:.6f}")


def _lse_symbol_slug(symbol: str) -> str:
    """
    Map an instrument symbol to LSE's per-symbol 1m candle table slug.
    Examples: 'BTC/USD' -> 'btc_usd', 'BRK.B' -> 'brk_b'.
    """
    return symbol.strip().lower().replace("/", "_").replace("-", "_").replace(".", "_")


def _lse_get_json(table: str, params: list) -> object:
    if not LSE_API_KEY or not LSE_API_BASE_URL:
        raise RuntimeError("LSE_API_KEY is not configured")
    url = f"{LSE_API_BASE_URL.rstrip('/')}/{table}"
    return _request_json_with_retry(
        "lse",
        "GET",
        url,
        params=params,
        headers={"x-api-key": LSE_API_KEY},
    )


def _lse_candle_close(table: str, target_utc: datetime, extra_params: Optional[list] = None) -> Optional[float]:
    """
    Latest candle close at-or-before target_utc from one LSE candle table.
    Filters use PostgREST syntax; repeated `timestamp` params are AND'ed
    server-side. The gte bound keeps the scan short: 7 days covers weekends
    and market holidays for "price at time" lookups on non-24/7 instruments.
    """
    since = (target_utc - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    params = list(extra_params or [])
    params += [
        ("timestamp", f"gte.{since}"),
        ("timestamp", f"lte.{until}"),
        ("order", "timestamp.desc"),
        ("limit", "1"),
    ]
    rows = _lse_get_json(table, params)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        try:
            price = float(rows[0].get("close"))
        except (TypeError, ValueError):
            return None
        if price > 0:
            return float(f"{price:.6f}")
    return None


def _lse_target_utc(executed_at: str) -> datetime:
    # "now"-style queries normally arrive with a concrete timestamp, but be
    # lenient: an unparseable executed_at falls back to the current time
    # rather than failing the whole LSE path.
    return _parse_executed_at_to_utc(executed_at) or datetime.now(UTC)


def _get_lse_us_stock_price(symbol: str, executed_at: str) -> Optional[float]:
    """
    US stock/ETF price from LSE 1m candles. US listings live in
    d_candles_<sym>; other instruments in candles_<sym>. The x_candles_5m
    aggregate is the last resort so a thin 1m table still yields a price.
    """
    target_utc = _lse_target_utc(executed_at)
    ticker = _normalize_yfinance_us_symbol(symbol)
    if not ticker:
        return None
    slug = _lse_symbol_slug(ticker)
    for table in (f"d_candles_{slug}", f"candles_{slug}"):
        try:
            price = _lse_candle_close(table, target_utc)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 404:
                # Symbol not in the LSE universe under this table name; try the
                # next naming scheme before giving up.
                continue
            _price_log(f"[Price API] LSE HTTP {status} for {ticker}")
            return None
        except Exception as exc:
            _price_log(f"[Price API] LSE error for {ticker}: {exc}")
            return None
        if price is not None:
            return price
    try:
        return _lse_candle_close("x_candles_5m", target_utc, [("symbol", f"eq.{ticker}")])
    except Exception as exc:
        _price_log(f"[Price API] LSE 5m fallback error for {ticker}: {exc}")
        return None


def _get_lse_crypto_price(symbol: str, executed_at: str) -> Optional[float]:
    """
    Crypto price from LSE 1m candles. LSE quotes crypto as COIN/USD, so the
    Hyperliquid coin normalization ('BTC-PERP' -> 'BTC') is reused here.
    """
    target_utc = _lse_target_utc(executed_at)
    coin = _normalize_hyperliquid_symbol(symbol)
    if not coin or ":" in coin:
        return None  # dex/builder listings exist only on Hyperliquid
    try:
        return _lse_candle_close(f"candles_{_lse_symbol_slug(coin + '/USD')}", target_utc)
    except Exception as exc:
        _price_log(f"[Price API] LSE crypto error for {coin}: {exc}")
        return None


def get_price_from_market(
    symbol: str,
    executed_at: str,
    market: str,
    token_id: Optional[str] = None,
    outcome: Optional[str] = None,
) -> Optional[float]:
    """
    根据市场获取价格

    Args:
        symbol: 股票代码
        executed_at: 执行时间 (ISO 8601 格式)
        market: 市场类型 (us-stock, crypto)

    Returns:
        查询到的价格，如果失败返回 None
    """
    try:
        try:
            from routes_shared import normalize_market

            market = normalize_market(market)
        except Exception:
            market = (market or "").strip().lower()

        if market == "crypto":
            # Crypto pricing: LSE candles first when a key is configured, then
            # Hyperliquid public endpoints (historical candle, then mid price).
            price = None
            if LSE_API_KEY:
                price = _get_lse_crypto_price(symbol, executed_at)
                if price is None:
                    _price_log(f"[Price API] LSE unavailable for {symbol}; falling back to Hyperliquid")
            if price is None:
                price = _get_hyperliquid_candle_close(symbol, executed_at) or _get_hyperliquid_mid_price(symbol)
        elif market == "polymarket":
            # Polymarket pricing uses public Gamma + CLOB endpoints.
            # We use the current orderbook mid price (paper trading).
            price = _get_polymarket_mid_price(symbol, token_id=token_id, outcome=outcome)
        elif market == "us-stock":
            # US stock pricing: LSE candles first when a key is configured,
            # then Alpha Vantage, then yfinance.
            price = None
            if LSE_API_KEY:
                price = _get_lse_us_stock_price(symbol, executed_at)
                if price is None:
                    _price_log(f"[Price API] LSE unavailable for {symbol}; falling back to Alpha Vantage/yfinance")
            if price is None:
                if ALPHA_VANTAGE_API_KEY and ALPHA_VANTAGE_API_KEY != "demo":
                    price = _get_us_stock_price(symbol, executed_at)
                else:
                    _price_log("Warning: ALPHA_VANTAGE_API_KEY not set, trying yfinance fallback")
            if price is None:
                _price_log(f"[Price API] Alpha Vantage unavailable for {symbol}; trying yfinance fallback")
                price = _get_yfinance_us_stock_price(symbol, executed_at)
        else:
            _price_log(f"[Price API] Unsupported market for server price fetch: {market}")
            return None

        if price is None:
            _price_log(f"[Price API] Failed to fetch {symbol} ({market}) price for time {executed_at}")
        else:
            _price_log(f"[Price API] Successfully fetched {symbol} ({market}): ${price}")

        return price
    except Exception as e:
        _price_log(f"[Price API] Error fetching {symbol} ({market}): {e}")
        return None


def _normalize_yfinance_us_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if normalized.endswith(".US"):
        return normalized[:-3]
    return normalized


def _download_yfinance_history(symbol: str, start_date: str, end_date: str, interval: str):
    import yfinance as yf

    return yf.download(
        symbol,
        start=start_date,
        end=end_date,
        interval=interval,
        auto_adjust=False,
        progress=False,
        prepost=True,
        threads=False,
        timeout=PRICE_FETCH_TIMEOUT_SECONDS,
    )


def _extract_yfinance_close_price(frame: Any, symbol: str, target_utc: datetime) -> Optional[float]:
    if frame is None or getattr(frame, "empty", True):
        return None

    try:
        import pandas as pd
    except Exception as exc:
        _price_log(f"[Price API] yfinance fallback missing pandas: {exc}")
        return None

    selected = frame.copy()
    try:
        if isinstance(selected.columns, pd.MultiIndex):
            target_symbol = symbol.upper()
            for level in range(selected.columns.nlevels):
                values = [str(value).upper() for value in selected.columns.get_level_values(level)]
                if target_symbol in values:
                    selected = selected.xs(symbol, axis=1, level=level, drop_level=True)
                    break
            if isinstance(selected.columns, pd.MultiIndex):
                selected.columns = [
                    next((str(part) for part in reversed(column) if str(part)), str(column[-1]))
                    for column in selected.columns
                ]

        close_column = None
        for candidate in ("Close", "close", "Adj Close", "adj close"):
            if candidate in selected.columns:
                close_column = candidate
                break
        if close_column is None:
            return None

        series = selected[close_column]
        if hasattr(series, "columns"):
            series = series.iloc[:, 0]
        series = pd.to_numeric(series, errors="coerce").dropna()
        if series.empty:
            return None

        index = pd.DatetimeIndex(pd.to_datetime(series.index))
        if getattr(index, "tz", None) is None:
            index = index.tz_localize(ET_TZ)
        index = index.tz_convert(UTC)
        series.index = index
        target = pd.Timestamp(target_utc)
        if target.tzinfo is None:
            target = target.tz_localize(UTC)
        else:
            target = target.tz_convert(UTC)

        candidates = series[series.index <= target]
        if candidates.empty:
            return None
        price = float(candidates.iloc[-1])
        return price if price > 0 else None
    except Exception as exc:
        _price_log(f"[Price API] yfinance parse error for {symbol}: {exc}")
        return None


def _get_yfinance_us_stock_price(symbol: str, executed_at: str) -> Optional[float]:
    """Best-effort Yahoo Finance fallback for US stock prices via yfinance."""
    target_utc = _parse_executed_at_to_utc(executed_at)
    if not target_utc:
        return None

    yf_symbol = _normalize_yfinance_us_symbol(symbol)
    if not yf_symbol:
        return None

    try:
        intraday_start = (target_utc - timedelta(days=1)).date().isoformat()
        intraday_end = (target_utc + timedelta(days=1)).date().isoformat()
        frame = _download_yfinance_history(yf_symbol, intraday_start, intraday_end, "1m")
        price = _extract_yfinance_close_price(frame, yf_symbol, target_utc)
        if price is not None:
            _price_log(f"[Price API] yfinance fallback fetched {yf_symbol}: ${price}")
            return price

        daily_start = (target_utc - timedelta(days=10)).date().isoformat()
        daily_end = (target_utc + timedelta(days=1)).date().isoformat()
        frame = _download_yfinance_history(yf_symbol, daily_start, daily_end, "1d")
        price = _extract_yfinance_close_price(frame, yf_symbol, target_utc)
        if price is not None:
            _price_log(f"[Price API] yfinance daily fallback fetched {yf_symbol}: ${price}")
        return price
    except ImportError as exc:
        _price_log(f"[Price API] yfinance fallback unavailable: {exc}")
        return None
    except Exception as exc:
        _price_log(f"[Price API] yfinance fallback failed for {yf_symbol}: {exc}")
        return None


def _get_us_stock_price(symbol: str, executed_at: str) -> Optional[float]:
    """获取美股价格"""
    # Alpha Vantage TIME_SERIES_INTRADAY 返回美国东部时间 (ET)
    try:
        # 先解析为 UTC
        dt_utc = datetime.fromisoformat(executed_at.replace('Z', '')).replace(tzinfo=UTC)
        # 转换为东部时间 (ET)
        dt_et = dt_utc.astimezone(ET_TZ)
    except ValueError:
        return None

    month = dt_et.strftime("%Y-%m")

    params = {
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": "1min",
        "month": month,
        "outputsize": "compact",
        "entitlement": "realtime",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    try:
        data = _request_json_with_retry(
            "alphavantage",
            "GET",
            BASE_URL,
            params=params,
        )

        if "Error Message" in data:
            _price_log(f"[Price API] Error: {data.get('Error Message')}")
            return None
        if "Note" in data:
            _activate_provider_cooldown(
                "alphavantage",
                PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS,
                "body rate limit note"
            )
            _price_log(f"[Price API] Rate limit: {data.get('Note')}")
            return None

        time_series_key = "Time Series (1min)"
        if time_series_key not in data:
            _price_log(f"[Price API] No time series data for {symbol}")
            return None

        time_series = data[time_series_key]
        # 使用东部时间进行比较
        target_datetime = dt_et.strftime("%Y-%m-%d %H:%M:%S")

        # 精确匹配
        if target_datetime in time_series:
            return float(time_series[target_datetime].get("4. close", 0))

        # 找最接近的之前的数据
        min_diff = float('inf')
        closest_price = None

        for time_key, values in time_series.items():
            time_dt = datetime.strptime(time_key, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET_TZ)
            if time_dt <= dt_et:
                diff = (dt_et - time_dt).total_seconds()
                if diff < min_diff:
                    min_diff = diff
                    closest_price = float(values.get("4. close", 0))

        if closest_price:
            _price_log(f"[Price API] Found closest price for {symbol}: ${closest_price} ({int(min_diff)}s earlier)")
        return closest_price

    except Exception as e:
        _price_log(f"[Price API] Exception while fetching {symbol}: {e}")
        return None


def _get_crypto_price(symbol: str, executed_at: str) -> Optional[float]:
    """
    Backwards-compat shim.
    AI-Trader 已停止使用 Alpha Vantage 的 crypto 端点；此函数保留仅为避免旧代码引用时报错。
    """
    return _get_hyperliquid_candle_close(symbol, executed_at) or _get_hyperliquid_mid_price(symbol)

"""
Stock Price Fetcher for Server

US Stock: 从 Alpha Vantage 获取价格
Crypto: 从 Hyperliquid 获取价格（停止使用 Alpha Vantage crypto 端点）
"""

import os
import random
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple, Any
import re
import time
import json

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
BASE_URL = "https://www.alphavantage.co/query"

# Hyperliquid public info endpoint (no API key required for reads)
HYPERLIQUID_API_URL = os.environ.get("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info").strip()

# Polymarket public endpoints (no API key required for reads)
POLYMARKET_GAMMA_BASE_URL = os.environ.get("POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com").strip()
POLYMARKET_CLOB_BASE_URL = os.environ.get("POLYMARKET_CLOB_BASE_URL", "https://clob.polymarket.com").strip()
PRICE_FETCH_TIMEOUT_SECONDS = float(os.environ.get("PRICE_FETCH_TIMEOUT_SECONDS", "10"))
PRICE_FETCH_MAX_RETRIES = max(0, int(os.environ.get("PRICE_FETCH_MAX_RETRIES", "2")))
PRICE_FETCH_BACKOFF_BASE_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_BACKOFF_BASE_SECONDS", "0.35")))
PRICE_FETCH_ERROR_COOLDOWN_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_ERROR_COOLDOWN_SECONDS", "20")))
PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS = max(0.0, float(os.environ.get("PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS", "60")))

# 时区常量
UTC = timezone.utc
ET_OFFSET = timedelta(hours=-4)  # EDT is UTC-4
ET_TZ = timezone(ET_OFFSET)

_POLYMARKET_CONDITION_ID_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
_POLYMARKET_TOKEN_ID_RE = re.compile(r"^\d+$")
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_provider_cooldowns: Dict[str, float] = {}

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
_POLYMARKET_TOKEN_CACHE_TTL_S = 300.0


def _provider_cooldown_remaining(provider: str) -> float:
    return max(0.0, _provider_cooldowns.get(provider, 0.0) - time.time())


def _activate_provider_cooldown(provider: str, duration_s: float, reason: str) -> None:
    if duration_s <= 0:
        return
    until = time.time() + duration_s
    previous_until = _provider_cooldowns.get(provider, 0.0)
    _provider_cooldowns[provider] = max(previous_until, until)
    remaining = _provider_cooldown_remaining(provider)
    print(f"[Price API] {provider} cooldown {remaining:.1f}s ({reason})")


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
    params: Optional[dict] = None,
    json_payload: Optional[dict] = None,
) -> object:
    remaining = _provider_cooldown_remaining(provider)
    if remaining > 0:
        raise RuntimeError(f"{provider} cooldown active for {remaining:.1f}s")

    last_exc: Optional[Exception] = None
    attempts = PRICE_FETCH_MAX_RETRIES + 1

    for attempt in range(attempts):
        try:
            if method == "POST":
                resp = requests.post(url, json=json_payload, timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            else:
                resp = requests.get(url, params=params, timeout=PRICE_FETCH_TIMEOUT_SECONDS)

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
                print(
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
                print(
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


def _polymarket_fetch_market(reference: str) -> Optional[dict]:
    if not POLYMARKET_GAMMA_BASE_URL:
        return None

    ref = (reference or "").strip()
    if not ref:
        return None

    url = f"{POLYMARKET_GAMMA_BASE_URL.rstrip('/')}/markets"
    params = {"limit": "1"}
    if _POLYMARKET_CONDITION_ID_RE.match(ref):
        params["conditionId"] = ref
    elif _POLYMARKET_TOKEN_ID_RE.match(ref):
        params["clob_token_ids"] = ref
    else:
        params["slug"] = ref

    try:
        raw = _polymarket_get_json(url, params=params)
    except Exception:
        return None

    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        return None
    return raw[0]


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

    cache_key = f"{ref}::{(token_id or '').strip().lower()}::{(outcome or '').strip().lower()}"
    cached = _polymarket_token_cache.get(cache_key)
    now = time.time()
    if cached and cached[1] > now:
        return {
            "token_id": cached[0],
            "outcome": outcome,
            "market": _polymarket_fetch_market(ref),
        }

    market = _polymarket_fetch_market(ref)
    if not market:
        return None

    tokens = _polymarket_extract_tokens(market)
    requested_token_id = (token_id or "").strip()
    requested_outcome = (outcome or "").strip().lower()

    selected = None
    if requested_token_id:
        for candidate in tokens:
            if candidate["token_id"] == requested_token_id:
                selected = candidate
                break
    elif _POLYMARKET_TOKEN_ID_RE.match(ref):
        selected = {"token_id": ref, "outcome": outcome}
    elif requested_outcome:
        for candidate in tokens:
            if (candidate.get("outcome") or "").strip().lower() == requested_outcome:
                selected = candidate
                break
    elif len(tokens) == 1:
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

        def _best_px(levels: list) -> Optional[float]:
            if not levels:
                return None
            first = levels[0]
            if isinstance(first, dict) and "price" in first:
                try:
                    return float(first["price"])
                except Exception:
                    return None
            return None

        best_bid = _best_px(bids)
        best_ask = _best_px(asks)
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
        if market == "crypto":
            # Crypto pricing now uses Hyperliquid public endpoints.
            # Try historical candle (when executed_at is provided), then fall back to mid price.
            price = _get_hyperliquid_candle_close(symbol, executed_at) or _get_hyperliquid_mid_price(symbol)
        elif market == "polymarket":
            # Polymarket pricing uses public Gamma + CLOB endpoints.
            # We use the current orderbook mid price (paper trading).
            price = _get_polymarket_mid_price(symbol, token_id=token_id, outcome=outcome)
        else:
            if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == "demo":
                print("Warning: ALPHA_VANTAGE_API_KEY not set, using agent-provided price")
                return None
            price = _get_us_stock_price(symbol, executed_at)

        if price is None:
            print(f"[Price API] Failed to fetch {symbol} ({market}) price for time {executed_at}")
        else:
            print(f"[Price API] Successfully fetched {symbol} ({market}): ${price}")

        return price
    except Exception as e:
        print(f"[Price API] Error fetching {symbol} ({market}): {e}")
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
            print(f"[Price API] Error: {data.get('Error Message')}")
            return None
        if "Note" in data:
            _activate_provider_cooldown(
                "alphavantage",
                PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS,
                "body rate limit note"
            )
            print(f"[Price API] Rate limit: {data.get('Note')}")
            return None

        time_series_key = "Time Series (1min)"
        if time_series_key not in data:
            print(f"[Price API] No time series data for {symbol}")
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
            print(f"[Price API] Found closest price for {symbol}: ${closest_price} ({int(min_diff)}s earlier)")
        return closest_price

    except Exception as e:
        print(f"[Price API] Exception while fetching {symbol}: {e}")
        return None


def _get_crypto_price(symbol: str, executed_at: str) -> Optional[float]:
    """
    Backwards-compat shim.
    AI-Trader 已停止使用 Alpha Vantage 的 crypto 端点；此函数保留仅为避免旧代码引用时报错。
    """
    return _get_hyperliquid_candle_close(symbol, executed_at) or _get_hyperliquid_mid_price(symbol)

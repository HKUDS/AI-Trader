"""
Stock Price Fetcher for Server

US Stock: 从 Alpha Vantage 获取价格
Crypto: 从 Hyperliquid 获取价格（停止使用 Alpha Vantage crypto 端点）
"""

import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
BASE_URL = "https://www.alphavantage.co/query"

# Hyperliquid public info endpoint (no API key required for reads)
HYPERLIQUID_API_URL = os.environ.get("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info").strip()

# 时区常量
UTC = timezone.utc
ET_OFFSET = timedelta(hours=-4)  # EDT is UTC-4
ET_TZ = timezone(ET_OFFSET)

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
    resp = requests.post(HYPERLIQUID_API_URL, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


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
    closest_diff = None
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
        diff = abs(target_ms - t_ms)
        if closest_diff is None or diff < closest_diff:
            closest_diff = diff
            closest = close

    if closest is None:
        return None
    return float(f"{closest:.6f}")


def get_price_from_market(symbol: str, executed_at: str, market: str) -> Optional[float]:
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
        response = requests.get(BASE_URL, params=params, timeout=10)
        data = response.json()

        if "Error Message" in data:
            print(f"[Price API] Error: {data.get('Error Message')}")
            return None
        if "Note" in data:
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

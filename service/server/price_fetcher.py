"""
Stock Price Fetcher for Server

从 Alpha Vantage 获取价格
"""

import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
BASE_URL = "https://www.alphavantage.co/query"

# 时区常量
UTC = timezone.utc
ET_OFFSET = timedelta(hours=-4)  # EDT is UTC-4
ET_TZ = timezone(ET_OFFSET)


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
    if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == "demo":
        print("Warning: ALPHA_VANTAGE_API_KEY not set, using agent-provided price")
        return None

    try:
        if market == "crypto":
            price = _get_crypto_price(symbol, executed_at)
        else:
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
    """获取加密货币价格"""
    # Alpha Vantage crypto API 返回 UTC 时间，executed_at 也应该是 UTC
    try:
        # 解析为 UTC 时间 (不是 ET)
        dt_naive = datetime.fromisoformat(executed_at.replace('Z', ''))
        dt_utc = dt_naive.replace(tzinfo=UTC)
    except ValueError:
        return None

    params = {
        "function": "CRYPTO_INTRADAY",
        "symbol": symbol,
        "market": "USD",
        "interval": "1min",
        "outputsize": "compact",
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

        time_series_key = "Time Series Crypto (1min)"
        if time_series_key not in data:
            print(f"[Price API] No time series data for {symbol}")
            return None

        time_series = data[time_series_key]
        sorted_times = sorted(time_series.keys())

        # 找到最接近的时间
        min_diff = float('inf')
        closest_price = None

        for time_key in sorted_times:
            values = time_series[time_key]
            # Alpha Vantage 返回的也是 UTC 时间
            time_utc = datetime.strptime(time_key, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            diff = abs((dt_utc.replace(tzinfo=None) - time_utc.replace(tzinfo=None)).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_price = float(values.get("4. close", 0))

        if closest_price:
            print(f"[Price API] Found closest price for {symbol}: ${closest_price} ({int(min_diff)}s earlier)")
        return closest_price

    except Exception as e:
        print(f"[Price API] Exception while fetching crypto {symbol}: {e}")
        return None

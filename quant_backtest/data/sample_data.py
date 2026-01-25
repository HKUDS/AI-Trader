"""
Sample data generator for testing and demonstration.

Generates realistic-looking price data without needing external APIs.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import math


# Sample symbols with approximate characteristics
SAMPLE_SYMBOLS = {
    "AAPL": {"base_price": 175, "volatility": 0.02, "trend": 0.0003},
    "GOOGL": {"base_price": 140, "volatility": 0.025, "trend": 0.0002},
    "MSFT": {"base_price": 380, "volatility": 0.018, "trend": 0.0004},
    "AMZN": {"base_price": 180, "volatility": 0.025, "trend": 0.0003},
    "NVDA": {"base_price": 500, "volatility": 0.035, "trend": 0.0006},
    "TSLA": {"base_price": 250, "volatility": 0.04, "trend": 0.0001},
    "META": {"base_price": 350, "volatility": 0.03, "trend": 0.0003},
    "JPM": {"base_price": 170, "volatility": 0.015, "trend": 0.0002},
    "V": {"base_price": 280, "volatility": 0.015, "trend": 0.0003},
    "WMT": {"base_price": 165, "volatility": 0.012, "trend": 0.0002},
}


def generate_sample_data(
    symbols: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = 252,  # 1 year of trading days
    seed: Optional[int] = None,
) -> Dict[str, List[dict]]:
    """
    Generate sample price data for backtesting.

    Args:
        symbols: List of symbols (defaults to all SAMPLE_SYMBOLS)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        days: Number of trading days (if dates not specified)
        seed: Random seed for reproducibility

    Returns:
        Dictionary of symbol -> list of OHLCV dictionaries
    """
    if seed is not None:
        random.seed(seed)

    if symbols is None:
        symbols = list(SAMPLE_SYMBOLS.keys())

    # Parse dates
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start = datetime.now() - timedelta(days=int(days * 1.5))

    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end = datetime.now()

    # Generate trading days (skip weekends)
    trading_days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            trading_days.append(current)
        current += timedelta(days=1)

    if len(trading_days) > days:
        trading_days = trading_days[-days:]

    data = {}

    for symbol in symbols:
        # Get symbol characteristics
        if symbol in SAMPLE_SYMBOLS:
            config = SAMPLE_SYMBOLS[symbol]
        else:
            # Generate random characteristics for unknown symbols
            config = {
                "base_price": random.uniform(50, 500),
                "volatility": random.uniform(0.015, 0.04),
                "trend": random.uniform(-0.0002, 0.0005),
            }

        records = _generate_symbol_data(
            trading_days,
            config["base_price"],
            config["volatility"],
            config["trend"],
        )
        data[symbol] = records

    return data


def _generate_symbol_data(
    trading_days: List[datetime],
    base_price: float,
    volatility: float,
    trend: float,
) -> List[dict]:
    """Generate OHLCV data for a single symbol."""
    records = []
    price = base_price

    for i, day in enumerate(trading_days):
        # Add trend component
        trend_factor = 1 + trend

        # Add cyclical component (simulates market cycles)
        cycle = 1 + 0.1 * math.sin(i / 60)

        # Add random walk
        daily_return = random.gauss(0, volatility)

        # Occasional larger moves (earnings, news, etc.)
        if random.random() < 0.02:
            daily_return += random.gauss(0, volatility * 3)

        # Update price
        price *= trend_factor * cycle * (1 + daily_return)
        price = max(price, 1)  # Prevent negative prices

        # Generate OHLC
        open_price = price * (1 + random.gauss(0, volatility * 0.1))
        high_price = max(open_price, price) * (1 + abs(random.gauss(0, volatility * 0.5)))
        low_price = min(open_price, price) * (1 - abs(random.gauss(0, volatility * 0.5)))
        close_price = price

        # Generate volume (higher volume on bigger moves)
        base_volume = 10_000_000
        volume_multiplier = 1 + abs(daily_return) * 10
        volume = int(base_volume * volume_multiplier * random.uniform(0.5, 1.5))

        records.append({
            "date": day.strftime("%Y-%m-%d"),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": volume,
        })

    return records


def generate_correlated_data(
    symbols: List[str],
    correlation: float = 0.7,
    **kwargs,
) -> Dict[str, List[dict]]:
    """
    Generate correlated price data for multiple symbols.

    Args:
        symbols: List of symbols to generate
        correlation: Correlation coefficient (0-1)
        **kwargs: Additional arguments for generate_sample_data
    """
    # Generate base data
    data = generate_sample_data(symbols=symbols, **kwargs)

    # If only one symbol, return as is
    if len(symbols) <= 1:
        return data

    # Use first symbol as base for correlation
    base_symbol = symbols[0]
    base_returns = []

    for i in range(1, len(data[base_symbol])):
        prev = data[base_symbol][i - 1]["close"]
        curr = data[base_symbol][i]["close"]
        base_returns.append((curr - prev) / prev)

    # Adjust other symbols to correlate with base
    for symbol in symbols[1:]:
        for i in range(1, len(data[symbol])):
            # Mix base return with symbol's return based on correlation
            if i - 1 < len(base_returns):
                symbol_return = (data[symbol][i]["close"] - data[symbol][i - 1]["close"]) / data[symbol][i - 1]["close"]
                mixed_return = correlation * base_returns[i - 1] + (1 - correlation) * symbol_return

                # Apply mixed return
                new_close = data[symbol][i - 1]["close"] * (1 + mixed_return)
                adjustment = new_close / data[symbol][i]["close"]

                data[symbol][i]["open"] *= adjustment
                data[symbol][i]["high"] *= adjustment
                data[symbol][i]["low"] *= adjustment
                data[symbol][i]["close"] = round(new_close, 2)

    return data

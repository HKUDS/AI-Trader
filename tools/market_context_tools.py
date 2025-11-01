"""
Market context tools for providing broader market information to trading agents.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import statistics


def calculate_price_momentum(
    symbol: str,
    current_date: str,
    lookback_days: int = 5,
    merged_path: Optional[str] = None
) -> Optional[float]:
    """
    Calculate price momentum (% change over lookback period).

    Args:
        symbol: Stock symbol
        current_date: Current date (YYYY-MM-DD)
        lookback_days: Number of days to look back
        merged_path: Path to merged.jsonl

    Returns:
        Momentum as % change, or None if insufficient data
    """
    if merged_path is None:
        project_root = Path(__file__).resolve().parents[1]
        merged_file = project_root / "data" / "merged.jsonl"
    else:
        merged_file = Path(merged_path)

    if not merged_file.exists():
        return None

    # Get price series
    prices = {}

    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                meta = doc.get("Meta Data", {})
                if meta.get("2. Symbol") != symbol:
                    continue

                series = doc.get("Time Series (Daily)", {})

                # Extract prices for our date range
                current_dt = datetime.strptime(current_date, "%Y-%m-%d")

                for date_str, data in series.items():
                    try:
                        date_dt = datetime.strptime(date_str, "%Y-%m-%d")
                        if date_dt <= current_dt:
                            close_price = float(data.get("4. sell price", 0))
                            if close_price > 0:
                                prices[date_str] = close_price
                    except:
                        continue

                break
            except:
                continue

    if len(prices) < 2:
        return None

    # Get sorted dates
    sorted_dates = sorted(prices.keys(), reverse=True)

    if len(sorted_dates) < lookback_days:
        return None

    latest_price = prices[sorted_dates[0]]
    old_price = prices[sorted_dates[min(lookback_days - 1, len(sorted_dates) - 1)]]

    if old_price == 0:
        return None

    momentum = ((latest_price - old_price) / old_price) * 100
    return round(momentum, 2)


def calculate_volatility(
    symbol: str,
    current_date: str,
    lookback_days: int = 20,
    merged_path: Optional[str] = None
) -> Optional[float]:
    """
    Calculate historical volatility (standard deviation of returns).

    Args:
        symbol: Stock symbol
        current_date: Current date
        lookback_days: Number of days for calculation
        merged_path: Path to merged.jsonl

    Returns:
        Annualized volatility %, or None if insufficient data
    """
    if merged_path is None:
        project_root = Path(__file__).resolve().parents[1]
        merged_file = project_root / "data" / "merged.jsonl"
    else:
        merged_file = Path(merged_path)

    if not merged_file.exists():
        return None

    prices = {}

    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                meta = doc.get("Meta Data", {})
                if meta.get("2. Symbol") != symbol:
                    continue

                series = doc.get("Time Series (Daily)", {})
                current_dt = datetime.strptime(current_date, "%Y-%m-%d")

                for date_str, data in series.items():
                    try:
                        date_dt = datetime.strptime(date_str, "%Y-%m-%d")
                        if date_dt <= current_dt:
                            close_price = float(data.get("4. sell price", 0))
                            if close_price > 0:
                                prices[date_str] = close_price
                    except:
                        continue
                break
            except:
                continue

    if len(prices) < lookback_days:
        return None

    sorted_dates = sorted(prices.keys(), reverse=True)[:lookback_days]

    # Calculate daily returns
    returns = []
    for i in range(len(sorted_dates) - 1):
        current_price = prices[sorted_dates[i]]
        prev_price = prices[sorted_dates[i + 1]]

        if prev_price > 0:
            daily_return = (current_price - prev_price) / prev_price
            returns.append(daily_return)

    if len(returns) < 2:
        return None

    # Calculate standard deviation and annualize (√252 trading days)
    std_dev = statistics.stdev(returns)
    annualized_vol = std_dev * (252 ** 0.5) * 100

    return round(annualized_vol, 2)


def get_market_movers(
    symbols: List[str],
    current_date: str,
    top_n: int = 10,
    merged_path: Optional[str] = None
) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    """
    Get top gainers and losers for the day.

    Args:
        symbols: List of symbols to analyze
        current_date: Current date
        top_n: Number of top movers to return
        merged_path: Path to merged.jsonl

    Returns:
        (top_gainers, top_losers) as lists of (symbol, % change) tuples
    """
    if merged_path is None:
        project_root = Path(__file__).resolve().parents[1]
        merged_file = project_root / "data" / "merged.jsonl"
    else:
        merged_file = Path(merged_path)

    if not merged_file.exists():
        return [], []

    current_dt = datetime.strptime(current_date, "%Y-%m-%d")
    yesterday_dt = current_dt - timedelta(days=1)

    # Skip weekends
    while yesterday_dt.weekday() >= 5:
        yesterday_dt -= timedelta(days=1)

    yesterday_date = yesterday_dt.strftime("%Y-%m-%d")

    changes = {}

    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                meta = doc.get("Meta Data", {})
                symbol = meta.get("2. Symbol")

                if symbol not in symbols:
                    continue

                series = doc.get("Time Series (Daily)", {})

                today_data = series.get(current_date)
                yesterday_data = series.get(yesterday_date)

                if today_data and yesterday_data:
                    today_close = float(today_data.get("4. sell price", 0))
                    yesterday_close = float(yesterday_data.get("4. sell price", 0))

                    if yesterday_close > 0:
                        pct_change = ((today_close - yesterday_close) / yesterday_close) * 100
                        changes[symbol] = pct_change
            except:
                continue

    # Sort by change
    sorted_changes = sorted(changes.items(), key=lambda x: x[1], reverse=True)

    gainers = sorted_changes[:top_n]
    losers = sorted_changes[-top_n:][::-1]

    return (
        [(sym, round(chg, 2)) for sym, chg in gainers],
        [(sym, round(chg, 2)) for sym, chg in losers]
    )


def build_market_context(
    symbols: List[str],
    current_date: str,
    current_positions: Dict[str, float]
) -> str:
    """
    Build market context summary.

    Args:
        symbols: List of all tradeable symbols
        current_date: Current date
        current_positions: Current portfolio positions

    Returns:
        Formatted market context string
    """
    context_parts = []

    context_parts.append("=== MARKET OVERVIEW ===")
    context_parts.append(f"Date: {current_date}")
    context_parts.append("")

    # Get market movers
    gainers, losers = get_market_movers(symbols, current_date, top_n=5)

    if gainers:
        context_parts.append("Top Gainers Today:")
        for symbol, change in gainers:
            held = "✓ HELD" if symbol in current_positions and current_positions.get(symbol, 0) > 0 else ""
            context_parts.append(f"  {symbol}: +{change}% {held}")
        context_parts.append("")

    if losers:
        context_parts.append("Top Losers Today:")
        for symbol, change in losers:
            held = "✓ HELD" if symbol in current_positions and current_positions.get(symbol, 0) > 0 else ""
            context_parts.append(f"  {symbol}: {change}% {held}")
        context_parts.append("")

    # Add momentum and volatility for held positions
    held_symbols = [sym for sym, shares in current_positions.items()
                    if sym != "CASH" and shares > 0]

    if held_symbols:
        context_parts.append("Your Holdings - Technical Context:")
        for symbol in held_symbols[:10]:  # Top 10 positions
            momentum_5d = calculate_price_momentum(symbol, current_date, lookback_days=5)
            volatility = calculate_volatility(symbol, current_date, lookback_days=20)

            if momentum_5d is not None or volatility is not None:
                parts = [f"  {symbol}:"]
                if momentum_5d is not None:
                    parts.append(f"5-day momentum: {momentum_5d:+.1f}%")
                if volatility is not None:
                    parts.append(f"volatility: {volatility:.1f}%")
                context_parts.append(" | ".join(parts))

        context_parts.append("")

    return "\n".join(context_parts)


if __name__ == "__main__":
    # Test market context
    from prompts.agent_prompt import all_nasdaq_100_symbols

    context = build_market_context(
        symbols=all_nasdaq_100_symbols,
        current_date="2025-10-15",
        current_positions={"AAPL": 10, "NVDA": 5, "CASH": 5000}
    )

    print(context)

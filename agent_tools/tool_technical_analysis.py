"""
Technical analysis MCP tool.
Provides price momentum, volatility, and trend analysis.
"""

from fastmcp import FastMCP
import sys
import os
from typing import Dict, Any, List, Optional

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value
from tools.market_context_tools import (
    calculate_price_momentum,
    calculate_volatility,
    get_market_movers
)
from prompts.agent_prompt import all_nasdaq_100_symbols

mcp = FastMCP("TechnicalAnalysis")


@mcp.tool()
def get_price_momentum(symbol: str, lookback_days: int = 5) -> Dict[str, Any]:
    """
    Calculate price momentum (percentage change) over a specified period.

    Momentum helps identify trending stocks. Positive momentum indicates
    upward price movement, negative indicates downward movement.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")
        lookback_days: Number of days to calculate momentum over (default: 5)
                      Common periods: 5 (weekly), 20 (monthly), 60 (quarterly)

    Returns:
        Dict with:
        - symbol: Stock symbol
        - lookback_days: Period used
        - momentum_pct: Percentage change over the period
        - trend: "STRONG_UP", "UP", "FLAT", "DOWN", or "STRONG_DOWN"

    Example:
        >>> result = get_price_momentum("AAPL", lookback_days=5)
        >>> print(result)
        {
            "symbol": "AAPL",
            "lookback_days": 5,
            "momentum_pct": 3.5,
            "trend": "UP"
        }
    """
    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {"error": "TODAY_DATE not configured"}

    momentum = calculate_price_momentum(symbol, today_date, lookback_days)

    if momentum is None:
        return {
            "error": f"Insufficient data to calculate momentum for {symbol}",
            "symbol": symbol,
            "lookback_days": lookback_days
        }

    # Classify trend
    if momentum > 5:
        trend = "STRONG_UP"
    elif momentum > 2:
        trend = "UP"
    elif momentum > -2:
        trend = "FLAT"
    elif momentum > -5:
        trend = "DOWN"
    else:
        trend = "STRONG_DOWN"

    return {
        "symbol": symbol,
        "lookback_days": lookback_days,
        "momentum_pct": momentum,
        "trend": trend,
        "interpretation": f"{symbol} has moved {momentum:+.1f}% over the past {lookback_days} days ({trend})"
    }


@mcp.tool()
def get_volatility(symbol: str, lookback_days: int = 20) -> Dict[str, Any]:
    """
    Calculate historical volatility (annualized standard deviation of returns).

    Volatility measures price risk. Higher volatility = higher price swings.
    Use this to assess position risk and size positions appropriately.

    Args:
        symbol: Stock symbol
        lookback_days: Number of days for calculation (default: 20)
                      20 days ≈ 1 month of trading

    Returns:
        Dict with:
        - symbol: Stock symbol
        - volatility_pct: Annualized volatility percentage
        - risk_level: "LOW", "MODERATE", "HIGH", or "VERY_HIGH"
        - interpretation: Human-readable explanation

    Example:
        >>> result = get_volatility("NVDA")
        >>> print(result)
        {
            "symbol": "NVDA",
            "volatility_pct": 45.2,
            "risk_level": "HIGH",
            "interpretation": "NVDA has HIGH volatility at 45.2%..."
        }
    """
    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {"error": "TODAY_DATE not configured"}

    volatility = calculate_volatility(symbol, today_date, lookback_days)

    if volatility is None:
        return {
            "error": f"Insufficient data to calculate volatility for {symbol}",
            "symbol": symbol
        }

    # Classify risk level
    if volatility > 50:
        risk_level = "VERY_HIGH"
    elif volatility > 35:
        risk_level = "HIGH"
    elif volatility > 20:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    interpretation = (
        f"{symbol} has {risk_level} volatility at {volatility:.1f}% (annualized). "
    )

    if risk_level in ["HIGH", "VERY_HIGH"]:
        interpretation += "This stock experiences large price swings - consider smaller position sizes."
    elif risk_level == "MODERATE":
        interpretation += "Moderate price fluctuations - standard for tech stocks."
    else:
        interpretation += "Relatively stable price movements."

    return {
        "symbol": symbol,
        "lookback_days": lookback_days,
        "volatility_pct": volatility,
        "risk_level": risk_level,
        "interpretation": interpretation
    }


@mcp.tool()
def get_top_movers(top_n: int = 10) -> Dict[str, Any]:
    """
    Get today's top gaining and losing stocks from the tradeable universe.

    Use this to identify market leaders and laggards, spot sector trends,
    and find potential trading opportunities.

    Args:
        top_n: Number of top gainers and losers to return (default: 10)

    Returns:
        Dict with:
        - date: Trading date
        - top_gainers: List of (symbol, % change) for best performers
        - top_losers: List of (symbol, % change) for worst performers
        - market_breadth: Summary of overall market direction

    Example:
        >>> result = get_top_movers(top_n=5)
        >>> print(result)
        {
            "date": "2025-10-15",
            "top_gainers": [("NVDA", 5.2), ("AMD", 4.1), ...],
            "top_losers": [("INTC", -3.5), ...],
            "market_breadth": "POSITIVE"
        }
    """
    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {"error": "TODAY_DATE not configured"}

    gainers, losers = get_market_movers(
        all_nasdaq_100_symbols,
        today_date,
        top_n=top_n
    )

    # Calculate market breadth
    if gainers and losers:
        avg_gainer_pct = sum(pct for _, pct in gainers) / len(gainers)
        avg_loser_pct = sum(abs(pct) for _, pct in losers) / len(losers)

        if avg_gainer_pct > avg_loser_pct * 1.5:
            breadth = "STRONG_POSITIVE"
        elif avg_gainer_pct > avg_loser_pct:
            breadth = "POSITIVE"
        elif avg_loser_pct > avg_gainer_pct * 1.5:
            breadth = "STRONG_NEGATIVE"
        elif avg_loser_pct > avg_gainer_pct:
            breadth = "NEGATIVE"
        else:
            breadth = "MIXED"
    else:
        breadth = "UNKNOWN"

    return {
        "date": today_date,
        "top_gainers": [{"symbol": sym, "change_pct": pct} for sym, pct in gainers],
        "top_losers": [{"symbol": sym, "change_pct": pct} for sym, pct in losers],
        "market_breadth": breadth,
        "summary": f"{len(gainers)} gainers vs {len(losers)} losers - Market breadth: {breadth}"
    }


@mcp.tool()
def compare_stocks(symbols: List[str], metric: str = "momentum") -> Dict[str, Any]:
    """
    Compare multiple stocks on a specific technical metric.

    Useful for ranking investment candidates or comparing holdings.

    Args:
        symbols: List of stock symbols to compare (max 20)
        metric: Metric to compare - "momentum" (5-day) or "volatility" (20-day)

    Returns:
        Dict with:
        - metric: Metric used for comparison
        - ranked_stocks: List of stocks sorted by metric value
        - best: Best performing stock
        - worst: Worst performing stock

    Example:
        >>> result = compare_stocks(["AAPL", "MSFT", "NVDA"], metric="momentum")
        >>> print(result)
        {
            "metric": "momentum",
            "ranked_stocks": [
                {"symbol": "NVDA", "value": 5.2, "rank": 1},
                {"symbol": "AAPL", "value": 2.1, "rank": 2},
                ...
            ],
            "best": {"symbol": "NVDA", "value": 5.2},
            "worst": {"symbol": "MSFT", "value": -1.5}
        }
    """
    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {"error": "TODAY_DATE not configured"}

    if len(symbols) > 20:
        return {"error": "Too many symbols - maximum 20 allowed"}

    if metric not in ["momentum", "volatility"]:
        return {"error": "Invalid metric - use 'momentum' or 'volatility'"}

    results = []

    for symbol in symbols:
        if metric == "momentum":
            value = calculate_price_momentum(symbol, today_date, lookback_days=5)
        else:  # volatility
            value = calculate_volatility(symbol, today_date, lookback_days=20)

        if value is not None:
            results.append({
                "symbol": symbol,
                "value": value
            })

    if not results:
        return {"error": "No data available for any of the symbols"}

    # Sort by value
    if metric == "momentum":
        # Higher is better for momentum
        sorted_results = sorted(results, key=lambda x: x["value"], reverse=True)
    else:
        # Lower is better for volatility (less risk)
        sorted_results = sorted(results, key=lambda x: x["value"])

    # Add ranks
    ranked_stocks = [
        {**stock, "rank": i + 1}
        for i, stock in enumerate(sorted_results)
    ]

    return {
        "metric": metric,
        "date": today_date,
        "ranked_stocks": ranked_stocks,
        "best": {
            "symbol": ranked_stocks[0]["symbol"],
            "value": ranked_stocks[0]["value"],
            "description": f"Best {metric}"
        },
        "worst": {
            "symbol": ranked_stocks[-1]["symbol"],
            "value": ranked_stocks[-1]["value"],
            "description": f"Worst {metric}"
        },
        "count": len(ranked_stocks)
    }


if __name__ == "__main__":
    port = int(os.getenv("TECHNICAL_HTTP_PORT", "8005"))
    mcp.run(transport="streamable-http", port=port)

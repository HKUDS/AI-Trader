"""
Portfolio analytics MCP tool.
Provides portfolio analysis capabilities to agents.
"""

from fastmcp import FastMCP
import sys
import os
from typing import Dict, Any, List, Optional

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value
from tools.price_tools import get_latest_position, get_open_prices
from tools.memory_tools import calculate_portfolio_metrics
from prompts.agent_prompt import all_nasdaq_100_symbols

mcp = FastMCP("PortfolioAnalytics")


@mcp.tool()
def analyze_portfolio() -> Dict[str, Any]:
    """
    Analyze current portfolio to get comprehensive metrics.

    Returns detailed portfolio analysis including:
    - Total portfolio value
    - Cash allocation percentage
    - Number of positions
    - Top holdings by value
    - Concentration risk (% in largest position)
    - Holdings breakdown

    This tool helps you understand your current portfolio composition
    and identify potential risk management needs.

    Returns:
        Dict with portfolio metrics including total_value, cash_allocation_pct,
        position_count, top_holdings, and concentration_pct

    Example:
        >>> result = analyze_portfolio()
        >>> print(result)
        {
            "total_value": 10500.50,
            "cash": 2000.00,
            "cash_allocation_pct": 19.04,
            "position_count": 5,
            "top_holdings": [
                {"symbol": "AAPL", "value": 2500.00, "pct": 23.8},
                ...
            ],
            "concentration_pct": 23.8
        }
    """
    signature = get_config_value("SIGNATURE")
    if signature is None:
        return {"error": "SIGNATURE environment variable is not set"}

    today_date = get_config_value("TODAY_DATE")
    if today_date is None:
        return {"error": "TODAY_DATE environment variable is not set"}

    # Get current positions
    current_position, _ = get_latest_position(today_date, signature)

    if not current_position:
        return {"error": "No position data found"}

    # Get current prices
    current_prices = get_open_prices(today_date, all_nasdaq_100_symbols)

    # Calculate metrics
    metrics = calculate_portfolio_metrics(current_position, current_prices)

    return metrics


@mcp.tool()
def get_position_performance(symbol: str) -> Dict[str, Any]:
    """
    Get performance information for a specific position you hold.

    This tool analyzes a single holding to understand its recent performance,
    helping you decide whether to hold, add to, or trim the position.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")

    Returns:
        Dict with position details:
        - shares_held: Number of shares you own
        - current_price: Current market price
        - position_value: Total value of this holding
        - portfolio_weight_pct: Percentage of total portfolio

    Example:
        >>> result = get_position_performance("AAPL")
        >>> print(result)
        {
            "symbol": "AAPL",
            "shares_held": 10,
            "current_price": 180.50,
            "position_value": 1805.00,
            "portfolio_weight_pct": 17.2
        }
    """
    signature = get_config_value("SIGNATURE")
    if signature is None:
        return {"error": "SIGNATURE environment variable is not set"}

    today_date = get_config_value("TODAY_DATE")
    if today_date is None:
        return {"error": "TODAY_DATE environment variable is not set"}

    # Get current positions
    current_position, _ = get_latest_position(today_date, signature)

    if symbol not in current_position or current_position[symbol] == 0:
        return {
            "error": f"No position found for {symbol}",
            "symbol": symbol,
            "shares_held": 0
        }

    shares_held = current_position[symbol]

    # Get current price
    current_prices = get_open_prices(today_date, [symbol])
    price_key = f"{symbol}_price"
    current_price = current_prices.get(price_key)

    if current_price is None:
        return {
            "error": f"Price data not available for {symbol}",
            "symbol": symbol,
            "shares_held": shares_held
        }

    position_value = shares_held * current_price

    # Calculate total portfolio value
    all_prices = get_open_prices(today_date, all_nasdaq_100_symbols)
    metrics = calculate_portfolio_metrics(current_position, all_prices)
    total_value = metrics['total_value']

    portfolio_weight_pct = (position_value / total_value * 100) if total_value > 0 else 0

    return {
        "symbol": symbol,
        "shares_held": shares_held,
        "current_price": round(current_price, 2),
        "position_value": round(position_value, 2),
        "portfolio_weight_pct": round(portfolio_weight_pct, 2),
        "total_portfolio_value": round(total_value, 2)
    }


@mcp.tool()
def check_concentration_risk() -> Dict[str, Any]:
    """
    Check if portfolio has excessive concentration in any single position.

    Returns an analysis of concentration risk with warnings if any position
    exceeds recommended thresholds (typically 15-20% of portfolio).

    Returns:
        Dict with:
        - largest_position: Symbol and weight of largest holding
        - concentration_level: "LOW", "MODERATE", or "HIGH"
        - warnings: List of positions exceeding safe thresholds
        - recommendations: Suggested actions to reduce risk

    Example:
        >>> result = check_concentration_risk()
        >>> print(result)
        {
            "largest_position": {"symbol": "NVDA", "weight_pct": 35.2},
            "concentration_level": "HIGH",
            "warnings": ["NVDA position at 35.2% exceeds safe threshold"],
            "recommendations": ["Consider trimming NVDA to below 20%"]
        }
    """
    signature = get_config_value("SIGNATURE")
    if signature is None:
        return {"error": "SIGNATURE environment variable is not set"}

    today_date = get_config_value("TODAY_DATE")
    if today_date is None:
        return {"error": "TODAY_DATE environment variable is not set"}

    # Get portfolio metrics
    current_position, _ = get_latest_position(today_date, signature)
    current_prices = get_open_prices(today_date, all_nasdaq_100_symbols)
    metrics = calculate_portfolio_metrics(current_position, current_prices)

    # Analyze concentration
    warnings = []
    recommendations = []

    top_holdings = metrics.get('top_holdings', [])

    if not top_holdings:
        return {
            "concentration_level": "NONE",
            "message": "Portfolio is 100% cash"
        }

    largest_position = top_holdings[0]
    largest_weight = largest_position['pct']

    # Determine concentration level
    if largest_weight > 25:
        concentration_level = "HIGH"
        warnings.append(f"{largest_position['symbol']} position at {largest_weight}% is very concentrated")
        recommendations.append(f"Consider trimming {largest_position['symbol']} to below 20%")
    elif largest_weight > 20:
        concentration_level = "MODERATE"
        warnings.append(f"{largest_position['symbol']} position at {largest_weight}% is moderately concentrated")
        recommendations.append(f"Monitor {largest_position['symbol']} and consider trimming if it grows further")
    else:
        concentration_level = "LOW"

    # Check for multiple concentrated positions
    concentrated_positions = [h for h in top_holdings if h['pct'] > 15]

    if len(concentrated_positions) > 2:
        warnings.append(f"{len(concentrated_positions)} positions exceed 15% - diversification may be insufficient")
        recommendations.append("Consider rebalancing to spread risk across more positions")

    return {
        "largest_position": {
            "symbol": largest_position['symbol'],
            "weight_pct": largest_weight,
            "value": largest_position['value']
        },
        "concentration_level": concentration_level,
        "concentrated_positions": len(concentrated_positions),
        "warnings": warnings if warnings else ["No concentration warnings"],
        "recommendations": recommendations if recommendations else ["Portfolio concentration is healthy"],
        "top_5_holdings": top_holdings[:5]
    }


@mcp.tool()
def calculate_required_cash(symbol: str, shares: int) -> Dict[str, Any]:
    """
    Calculate how much cash is needed to buy a specific number of shares.

    Useful for planning trades and ensuring you have sufficient funds.

    Args:
        symbol: Stock symbol to buy
        shares: Number of shares you want to buy

    Returns:
        Dict with:
        - symbol: Stock symbol
        - shares: Number of shares
        - price_per_share: Current market price
        - total_cost: Total cash required
        - current_cash: Your available cash
        - sufficient_funds: True if you can afford the trade

    Example:
        >>> result = calculate_required_cash("AAPL", 10)
        >>> print(result)
        {
            "symbol": "AAPL",
            "shares": 10,
            "price_per_share": 180.50,
            "total_cost": 1805.00,
            "current_cash": 5000.00,
            "sufficient_funds": true
        }
    """
    signature = get_config_value("SIGNATURE")
    today_date = get_config_value("TODAY_DATE")

    if not signature or not today_date:
        return {"error": "Configuration not properly set"}

    # Get current price
    prices = get_open_prices(today_date, [symbol])
    price_key = f"{symbol}_price"
    price = prices.get(price_key)

    if price is None:
        return {
            "error": f"Price not available for {symbol}",
            "symbol": symbol
        }

    total_cost = price * shares

    # Get current cash
    current_position, _ = get_latest_position(today_date, signature)
    current_cash = current_position.get("CASH", 0)

    return {
        "symbol": symbol,
        "shares": shares,
        "price_per_share": round(price, 2),
        "total_cost": round(total_cost, 2),
        "current_cash": round(current_cash, 2),
        "sufficient_funds": current_cash >= total_cost,
        "shortfall": round(max(0, total_cost - current_cash), 2)
    }


if __name__ == "__main__":
    port = int(os.getenv("PORTFOLIO_HTTP_PORT", "8004"))
    mcp.run(transport="streamable-http", port=port)

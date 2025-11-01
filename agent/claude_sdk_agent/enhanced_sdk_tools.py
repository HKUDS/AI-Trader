"""
Enhanced Claude Agent SDK Tools

Includes all original tools plus portfolio analytics and technical analysis.
Designed for use with claude-agent-sdk @tool decorator.
"""

import os
import json
import sys
from typing import Dict, Any, List
from pathlib import Path

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from claude_agent_sdk import tool, create_sdk_mcp_server
from tools.price_tools import get_latest_position, get_open_prices
from tools.general_tools import get_config_value, write_config_value
from tools.memory_tools import calculate_portfolio_metrics
from tools.market_context_tools import calculate_price_momentum, calculate_volatility, get_market_movers
from prompts.agent_prompt import all_nasdaq_100_symbols

# Import original tools
from agent.claude_sdk_agent.sdk_tools import (
    buy, sell, get_price_local, get_information
)


# ============================================================================
# PORTFOLIO ANALYTICS TOOLS
# ============================================================================

@tool(
    name="analyze_portfolio",
    description="""Analyze current portfolio to get comprehensive metrics including:
- Total portfolio value
- Cash allocation percentage
- Number of positions
- Top holdings by value
- Concentration risk (% in largest position)

This tool helps understand portfolio composition and identify risk management needs.""",
    input_schema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
async def analyze_portfolio(args: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze portfolio using claude-agent-sdk tool format"""
    signature = get_config_value("SIGNATURE")
    if signature is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "SIGNATURE environment variable is not set"})
            }]
        }

    today_date = get_config_value("TODAY_DATE")
    if today_date is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "TODAY_DATE environment variable is not set"})
            }]
        }

    # Get current positions
    current_position, _ = get_latest_position(today_date, signature)

    if not current_position:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "No position data found"})
            }]
        }

    # Get current prices
    current_prices = get_open_prices(today_date, all_nasdaq_100_symbols)

    # Calculate metrics
    metrics = calculate_portfolio_metrics(current_position, current_prices)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(metrics, indent=2)
        }]
    }


@tool(
    name="get_position_performance",
    description="""Get performance information for a specific position you hold.
Returns shares held, current price, position value, and portfolio weight percentage.
Useful for deciding whether to hold, add to, or trim a position.""",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol (e.g., 'AAPL', 'MSFT')"
            }
        },
        "required": ["symbol"]
    }
)
async def get_position_performance(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get position performance using claude-agent-sdk tool format"""
    symbol = args["symbol"]

    signature = get_config_value("SIGNATURE")
    today_date = get_config_value("TODAY_DATE")

    if not signature or not today_date:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "Configuration not properly set"})
            }]
        }

    # Get current positions
    current_position, _ = get_latest_position(today_date, signature)

    if symbol not in current_position or current_position[symbol] == 0:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"No position found for {symbol}",
                    "symbol": symbol,
                    "shares_held": 0
                })
            }]
        }

    shares_held = current_position[symbol]

    # Get current price
    current_prices = get_open_prices(today_date, [symbol])
    price_key = f"{symbol}_price"
    current_price = current_prices.get(price_key)

    if current_price is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"Price data not available for {symbol}",
                    "symbol": symbol,
                    "shares_held": shares_held
                })
            }]
        }

    position_value = shares_held * current_price

    # Calculate portfolio weight
    all_prices = get_open_prices(today_date, all_nasdaq_100_symbols)
    metrics = calculate_portfolio_metrics(current_position, all_prices)
    total_value = metrics['total_value']

    portfolio_weight_pct = (position_value / total_value * 100) if total_value > 0 else 0

    result = {
        "symbol": symbol,
        "shares_held": shares_held,
        "current_price": round(current_price, 2),
        "position_value": round(position_value, 2),
        "portfolio_weight_pct": round(portfolio_weight_pct, 2),
        "total_portfolio_value": round(total_value, 2)
    }

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2)
        }]
    }


@tool(
    name="check_concentration_risk",
    description="""Check if portfolio has excessive concentration in any single position.
Returns concentration analysis with warnings if any position exceeds recommended thresholds (15-20%).
Includes recommendations for risk reduction.""",
    input_schema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
async def check_concentration_risk(args: Dict[str, Any]) -> Dict[str, Any]:
    """Check concentration risk using claude-agent-sdk tool format"""
    signature = get_config_value("SIGNATURE")
    today_date = get_config_value("TODAY_DATE")

    if not signature or not today_date:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "Configuration not properly set"})
            }]
        }

    # Get portfolio metrics
    current_position, _ = get_latest_position(today_date, signature)
    current_prices = get_open_prices(today_date, all_nasdaq_100_symbols)
    metrics = calculate_portfolio_metrics(current_position, current_prices)

    warnings = []
    recommendations = []

    top_holdings = metrics.get('top_holdings', [])

    if not top_holdings:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "concentration_level": "NONE",
                    "message": "Portfolio is 100% cash"
                })
            }]
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

    result = {
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

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2)
        }]
    }


# ============================================================================
# TECHNICAL ANALYSIS TOOLS
# ============================================================================

@tool(
    name="get_price_momentum",
    description="""Calculate price momentum (percentage change) over a specified period.
Positive momentum indicates upward price movement, negative indicates downward.
Returns momentum percentage and trend classification (STRONG_UP, UP, FLAT, DOWN, STRONG_DOWN).""",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol (e.g., 'AAPL', 'MSFT')"
            },
            "lookback_days": {
                "type": "integer",
                "description": "Number of days to calculate momentum over (default: 5)",
                "default": 5
            }
        },
        "required": ["symbol"]
    }
)
async def get_price_momentum_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get price momentum using claude-agent-sdk tool format"""
    symbol = args["symbol"]
    lookback_days = args.get("lookback_days", 5)

    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "TODAY_DATE not configured"})
            }]
        }

    momentum = calculate_price_momentum(symbol, today_date, lookback_days)

    if momentum is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"Insufficient data to calculate momentum for {symbol}",
                    "symbol": symbol,
                    "lookback_days": lookback_days
                })
            }]
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

    result = {
        "symbol": symbol,
        "lookback_days": lookback_days,
        "momentum_pct": momentum,
        "trend": trend,
        "interpretation": f"{symbol} has moved {momentum:+.1f}% over the past {lookback_days} days ({trend})"
    }

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2)
        }]
    }


@tool(
    name="get_volatility",
    description="""Calculate historical volatility (annualized standard deviation of returns).
Higher volatility = higher price risk. Use this to assess position risk and size appropriately.
Returns volatility percentage and risk level (LOW, MODERATE, HIGH, VERY_HIGH).""",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol"
            },
            "lookback_days": {
                "type": "integer",
                "description": "Number of days for calculation (default: 20)",
                "default": 20
            }
        },
        "required": ["symbol"]
    }
)
async def get_volatility_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get volatility using claude-agent-sdk tool format"""
    symbol = args["symbol"]
    lookback_days = args.get("lookback_days", 20)

    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "TODAY_DATE not configured"})
            }]
        }

    volatility = calculate_volatility(symbol, today_date, lookback_days)

    if volatility is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"Insufficient data to calculate volatility for {symbol}",
                    "symbol": symbol
                })
            }]
        }

    # Classify risk level
    if volatility > 50:
        risk_level = "VERY_HIGH"
        interpretation = f"{symbol} has {risk_level} volatility at {volatility:.1f}% (annualized). This stock experiences large price swings - consider smaller position sizes."
    elif volatility > 35:
        risk_level = "HIGH"
        interpretation = f"{symbol} has {risk_level} volatility at {volatility:.1f}% (annualized). This stock experiences large price swings - consider smaller position sizes."
    elif volatility > 20:
        risk_level = "MODERATE"
        interpretation = f"{symbol} has {risk_level} volatility at {volatility:.1f}% (annualized). Moderate price fluctuations - standard for tech stocks."
    else:
        risk_level = "LOW"
        interpretation = f"{symbol} has {risk_level} volatility at {volatility:.1f}% (annualized). Relatively stable price movements."

    result = {
        "symbol": symbol,
        "lookback_days": lookback_days,
        "volatility_pct": volatility,
        "risk_level": risk_level,
        "interpretation": interpretation
    }

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2)
        }]
    }


@tool(
    name="get_top_movers",
    description="""Get today's top gaining and losing stocks from the tradeable universe.
Use this to identify market leaders and laggards, spot sector trends, and find trading opportunities.
Returns top gainers, top losers, and overall market breadth assessment.""",
    input_schema={
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "Number of top gainers and losers to return (default: 10)",
                "default": 10
            }
        },
        "required": []
    }
)
async def get_top_movers_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get top movers using claude-agent-sdk tool format"""
    top_n = args.get("top_n", 10)

    today_date = get_config_value("TODAY_DATE")

    if not today_date:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "TODAY_DATE not configured"})
            }]
        }

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

    result = {
        "date": today_date,
        "top_gainers": [{"symbol": sym, "change_pct": pct} for sym, pct in gainers],
        "top_losers": [{"symbol": sym, "change_pct": pct} for sym, pct in losers],
        "market_breadth": breadth,
        "summary": f"{len(gainers)} gainers vs {len(losers)} losers - Market breadth: {breadth}"
    }

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result, indent=2)
        }]
    }


# ============================================================================
# CREATE ENHANCED MCP SERVER
# ============================================================================

def create_enhanced_trading_server():
    """Create and return the enhanced MCP server with all trading tools"""
    return create_sdk_mcp_server(
        name="enhanced-trading-tools",
        tools=[
            # Original tools
            buy,
            sell,
            get_price_local,
            get_information,
            # Portfolio analytics
            analyze_portfolio,
            get_position_performance,
            check_concentration_risk,
            # Technical analysis
            get_price_momentum_tool,
            get_volatility_tool,
            get_top_movers_tool
        ]
    )


if __name__ == "__main__":
    # Test imports
    print("✅ Enhanced SDK tools module loaded successfully")
    print(f"   Original tools: buy, sell, get_price_local, get_information")
    print(f"   Portfolio tools: analyze_portfolio, get_position_performance, check_concentration_risk")
    print(f"   Technical tools: get_price_momentum_tool, get_volatility_tool, get_top_movers_tool")
    print(f"   Total: 10 tools")

    server = create_enhanced_trading_server()
    print(f"✅ Enhanced MCP server created: {server}")

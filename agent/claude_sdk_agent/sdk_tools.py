"""
Claude Agent SDK Tools

Tools implemented using the official claude-agent-sdk @tool decorator.
These run as in-process MCP servers for better performance.
"""

import os
import json
import sys
from typing import Dict, Any
from pathlib import Path

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from claude_agent_sdk import tool, create_sdk_mcp_server
from tools.price_tools import (
    get_latest_position,
    get_open_prices,
)
from tools.general_tools import get_config_value, write_config_value

# Import search functionality
import requests
import random
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# TRADING TOOLS
# ============================================================================

@tool(
    name="buy",
    description="""Buy stock function. Simulates stock buying operations including:
1. Get current position and operation ID
2. Get stock opening price for the day
3. Validate buy conditions (sufficient cash)
4. Update position (increase stock quantity, decrease cash)
5. Record transaction to position.jsonl file""",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol, such as 'AAPL', 'MSFT', etc."
            },
            "amount": {
                "type": "integer",
                "description": "Buy quantity, must be a positive integer"
            }
        },
        "required": ["symbol", "amount"]
    }
)
async def buy(args: Dict[str, Any]) -> Dict[str, Any]:
    """Buy stock using claude-agent-sdk tool format"""
    symbol = args["symbol"]
    amount = args["amount"]

    # Get environment variables
    signature = get_config_value("SIGNATURE")
    if signature is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "SIGNATURE environment variable is not set"})
            }]
        }

    today_date = get_config_value("TODAY_DATE")

    # Get current position
    try:
        current_position, current_action_id = get_latest_position(today_date, signature)
    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": f"Failed to get position: {str(e)}"})
            }]
        }

    # Get stock price
    try:
        this_symbol_price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
    except KeyError:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"Symbol {symbol} not found! This action will not be allowed.",
                    "symbol": symbol,
                    "date": today_date
                })
            }]
        }

    # Validate buy conditions
    cash_left = current_position["CASH"] - this_symbol_price * amount

    if cash_left < 0:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": "Insufficient cash! This action will not be allowed.",
                    "required_cash": this_symbol_price * amount,
                    "cash_available": current_position.get("CASH", 0),
                    "symbol": symbol,
                    "date": today_date
                })
            }]
        }

    # Execute buy operation
    new_position = current_position.copy()
    new_position["CASH"] = cash_left
    new_position[symbol] += amount

    # Record transaction
    position_file_path = os.path.join(
        project_root, "data", "agent_data", signature, "position", "position.jsonl"
    )
    with open(position_file_path, "a") as f:
        record = {
            "date": today_date,
            "id": current_action_id + 1,
            "this_action": {"action": "buy", "symbol": symbol, "amount": amount},
            "positions": new_position
        }
        f.write(json.dumps(record) + "\n")

    write_config_value("IF_TRADE", True)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(new_position, indent=2)
        }]
    }


@tool(
    name="sell",
    description="""Sell stock function. Simulates stock selling operations including:
1. Get current position and operation ID
2. Get stock opening price for the day
3. Validate sell conditions (position exists, sufficient quantity)
4. Update position (decrease stock quantity, increase cash)
5. Record transaction to position.jsonl file""",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol, such as 'AAPL', 'MSFT', etc."
            },
            "amount": {
                "type": "integer",
                "description": "Sell quantity, must be a positive integer"
            }
        },
        "required": ["symbol", "amount"]
    }
)
async def sell(args: Dict[str, Any]) -> Dict[str, Any]:
    """Sell stock using claude-agent-sdk tool format"""
    symbol = args["symbol"]
    amount = args["amount"]

    # Get environment variables
    signature = get_config_value("SIGNATURE")
    if signature is None:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": "SIGNATURE environment variable is not set"})
            }]
        }

    today_date = get_config_value("TODAY_DATE")

    # Get current position
    current_position, current_action_id = get_latest_position(today_date, signature)

    # Get stock price
    try:
        this_symbol_price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
    except KeyError:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"Symbol {symbol} not found! This action will not be allowed.",
                    "symbol": symbol,
                    "date": today_date
                })
            }]
        }

    # Validate sell conditions
    if symbol not in current_position:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": f"No position for {symbol}! This action will not be allowed.",
                    "symbol": symbol,
                    "date": today_date
                })
            }]
        }

    if current_position[symbol] < amount:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "error": "Insufficient shares! This action will not be allowed.",
                    "have": current_position.get(symbol, 0),
                    "want_to_sell": amount,
                    "symbol": symbol,
                    "date": today_date
                })
            }]
        }

    # Execute sell operation
    new_position = current_position.copy()
    new_position[symbol] -= amount
    new_position["CASH"] = new_position.get("CASH", 0) + this_symbol_price * amount

    # Record transaction
    position_file_path = os.path.join(
        project_root, "data", "agent_data", signature, "position", "position.jsonl"
    )
    with open(position_file_path, "a") as f:
        record = {
            "date": today_date,
            "id": current_action_id + 1,
            "this_action": {"action": "sell", "symbol": symbol, "amount": amount},
            "positions": new_position
        }
        f.write(json.dumps(record) + "\n")

    write_config_value("IF_TRADE", True)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(new_position, indent=2)
        }]
    }


# ============================================================================
# PRICE TOOL
# ============================================================================

@tool(
    name="get_price_local",
    description="Read OHLCV data for specified stock and date. Get historical information for specified stock.",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock symbol, e.g. 'IBM' or 'AAPL'"
            },
            "date": {
                "type": "string",
                "description": "Date in 'YYYY-MM-DD' format"
            }
        },
        "required": ["symbol", "date"]
    }
)
async def get_price_local(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get local price data using claude-agent-sdk tool format"""
    symbol = args["symbol"]
    date = args["date"]

    def _validate_date(date_str: str) -> None:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date must be in YYYY-MM-DD format") from exc

    def _workspace_data_path(filename: str) -> Path:
        return Path(project_root) / "data" / filename

    # Validate date
    try:
        _validate_date(date)
    except ValueError as e:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": str(e), "symbol": symbol, "date": date})
            }]
        }

    # Read data
    data_path = _workspace_data_path("merged.jsonl")
    if not data_path.exists():
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"error": f"Data file not found: {data_path}", "symbol": symbol, "date": date})
            }]
        }

    with data_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            meta = doc.get("Meta Data", {})
            if meta.get("2. Symbol") != symbol:
                continue
            series = doc.get("Time Series (Daily)", {})
            day = series.get(date)
            if day is None:
                sample_dates = sorted(series.keys(), reverse=True)[:5]
                return {
                    "content": [{
                        "type": "text",
                        "text": json.dumps({
                            "error": f"Data not found for date {date}. Sample available dates: {sample_dates}",
                            "symbol": symbol,
                            "date": date
                        })
                    }]
                }
            result = {
                "symbol": symbol,
                "date": date,
                "ohlcv": {
                    "open": day.get("1. buy price"),
                    "high": day.get("2. high"),
                    "low": day.get("3. low"),
                    "close": day.get("4. sell price"),
                    "volume": day.get("5. volume"),
                },
            }
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }]
            }

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({"error": f"No records found for stock {symbol} in local data", "symbol": symbol, "date": date})
        }]
    }


# ============================================================================
# SEARCH TOOL
# ============================================================================

@tool(
    name="get_information",
    description="""Use search tool to scrape and return main content information related to specified query.
Returns web page contents including URL, title, description, publish time, and content.""",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Key information or search terms you want to retrieve"
            }
        },
        "required": ["query"]
    }
)
async def get_information(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search and retrieve information using claude-agent-sdk tool format"""
    query = args["query"]

    # Helper functions for Jina search
    def parse_date_to_standard(date_str: str) -> str:
        if not date_str or date_str == 'unknown':
            return 'unknown'

        # Handle relative time
        if 'ago' in date_str.lower():
            try:
                now = datetime.now()
                if 'hour' in date_str.lower():
                    hours = int(re.findall(r'\d+', date_str)[0])
                    return (now - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
                elif 'day' in date_str.lower():
                    days = int(re.findall(r'\d+', date_str)[0])
                    return (now - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        # Handle ISO 8601
        try:
            if 'T' in date_str:
                date_part = date_str.split('+')[0] if '+' in date_str else date_str.replace('Z', '')
                if '.' in date_part:
                    parsed = datetime.strptime(date_part.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                else:
                    parsed = datetime.strptime(date_part, '%Y-%m-%dT%H:%M:%S')
                return parsed.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

        return date_str

    def jina_search(query: str, api_key: str):
        url = f'https://s.jina.ai/?q={query}&n=1'
        headers = {
            'Authorization': f'Bearer {api_key}',
            "Accept": "application/json",
            "X-Respond-With": "no-content"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            json_data = response.json()

            if not json_data or 'data' not in json_data:
                return []

            filtered_urls = []
            for item in json_data.get('data', []):
                if 'url' not in item:
                    continue

                raw_date = item.get('date', 'unknown')
                standardized_date = parse_date_to_standard(raw_date)

                if standardized_date == 'unknown':
                    filtered_urls.append(item['url'])
                    continue

                today_date = get_config_value("TODAY_DATE")
                if today_date and today_date > standardized_date:
                    filtered_urls.append(item['url'])
                else:
                    filtered_urls.append(item['url'])

            return filtered_urls
        except Exception as e:
            logger.error(f"Jina search error: {e}")
            return []

    def jina_scrape(url: str, api_key: str):
        try:
            jina_url = f'https://r.jina.ai/{url}'
            headers = {
                "Accept": "application/json",
                'Authorization': api_key,
                'X-Timeout': "10",
                "X-With-Generated-Alt": "true",
            }
            response = requests.get(jina_url, headers=headers)

            if response.status_code != 200:
                return {'url': url, 'error': f"Status {response.status_code}"}

            data = response.json()['data']
            return {
                'url': data['url'],
                'title': data['title'],
                'description': data['description'],
                'content': data['content'],
                'publish_time': data.get('publishedTime', 'unknown')
            }
        except Exception as e:
            return {'url': url, 'error': str(e)}

    # Main search logic
    try:
        api_key = os.environ.get("JINA_API_KEY")
        if not api_key:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: Jina API key not provided! Please set JINA_API_KEY environment variable."
                }]
            }

        urls = jina_search(query, api_key)
        if not urls:
            return {
                "content": [{
                    "type": "text",
                    "text": f"⚠️ Search query '{query}' found no results."
                }]
            }

        if len(urls) > 1:
            urls = random.sample(urls, 1)

        results = []
        for url in urls:
            result = jina_scrape(url, api_key)
            if 'error' in result:
                results.append(f"Error: {result['error']}")
            else:
                results.append(f"""
URL: {result['url']}
Title: {result['title']}
Description: {result['description']}
Publish Time: {result['publish_time']}
Content: {result['content'][:1000]}...
""")

        return {
            "content": [{
                "type": "text",
                "text": "\n".join(results) if results else f"⚠️ No results for '{query}'"
            }]
        }

    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": f"❌ Search tool execution failed: {str(e)}"
            }]
        }


# ============================================================================
# CREATE MCP SERVER
# ============================================================================

def create_trading_server():
    """Create and return the MCP server with all trading tools"""
    return create_sdk_mcp_server(
        name="trading-tools",
        tools=[buy, sell, get_price_local, get_information]
    )


if __name__ == "__main__":
    # Test imports
    print("✅ SDK tools module loaded successfully")
    print(f"   Tools: buy, sell, get_price_local, get_information")
    server = create_trading_server()
    print(f"✅ MCP server created: {server}")

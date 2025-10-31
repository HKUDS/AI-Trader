"""
Anthropic SDK Native Tools

This module provides tool definitions and implementations in Anthropic's native format.
Replaces the MCP toolchain with direct Python function calls.
"""

import os
import json
import sys
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import requests
import random
import re
from datetime import timedelta
import logging

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tools.price_tools import (
    get_latest_position,
    get_open_prices,
    get_yesterday_date,
    get_yesterday_open_and_close_price
)
from tools.general_tools import get_config_value, write_config_value

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL DEFINITIONS (Anthropic Format)
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "buy",
        "description": """Buy stock function. Simulates stock buying operations including:
1. Get current position and operation ID
2. Get stock opening price for the day
3. Validate buy conditions (sufficient cash)
4. Update position (increase stock quantity, decrease cash)
5. Record transaction to position.jsonl file""",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol, such as 'AAPL', 'MSFT', etc."
                },
                "amount": {
                    "type": "integer",
                    "description": "Buy quantity, must be a positive integer, indicating how many shares to buy"
                }
            },
            "required": ["symbol", "amount"]
        }
    },
    {
        "name": "sell",
        "description": """Sell stock function. Simulates stock selling operations including:
1. Get current position and operation ID
2. Get stock opening price for the day
3. Validate sell conditions (position exists, sufficient quantity)
4. Update position (decrease stock quantity, increase cash)
5. Record transaction to position.jsonl file""",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol, such as 'AAPL', 'MSFT', etc."
                },
                "amount": {
                    "type": "integer",
                    "description": "Sell quantity, must be a positive integer, indicating how many shares to sell"
                }
            },
            "required": ["symbol", "amount"]
        }
    },
    {
        "name": "get_price_local",
        "description": """Read OHLCV data for specified stock and date. Get historical information for specified stock.""",
        "input_schema": {
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
    },
    {
        "name": "get_information",
        "description": """Use search tool to scrape and return main content information related to specified query in a structured way.
Returns web page contents including URL, title, description, publish time, and content.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Key information or search terms you want to retrieve, will search for the most matching results on the internet"
                }
            },
            "required": ["query"]
        }
    }
]


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

def buy(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Buy stock function - native implementation
    """
    # Get environment variables
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    today_date = get_config_value("TODAY_DATE")

    # Get current position
    try:
        current_position, current_action_id = get_latest_position(today_date, signature)
    except Exception as e:
        return {"error": f"Failed to get position: {str(e)}"}

    # Get stock price
    try:
        this_symbol_price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
    except KeyError:
        return {
            "error": f"Symbol {symbol} not found! This action will not be allowed.",
            "symbol": symbol,
            "date": today_date
        }

    # Validate buy conditions
    cash_left = current_position["CASH"] - this_symbol_price * amount

    if cash_left < 0:
        return {
            "error": "Insufficient cash! This action will not be allowed.",
            "required_cash": this_symbol_price * amount,
            "cash_available": current_position.get("CASH", 0),
            "symbol": symbol,
            "date": today_date
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
    return new_position


def sell(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Sell stock function - native implementation
    """
    # Get environment variables
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    today_date = get_config_value("TODAY_DATE")

    # Get current position
    current_position, current_action_id = get_latest_position(today_date, signature)

    # Get stock price
    try:
        this_symbol_price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
    except KeyError:
        return {
            "error": f"Symbol {symbol} not found! This action will not be allowed.",
            "symbol": symbol,
            "date": today_date
        }

    # Validate sell conditions
    if symbol not in current_position:
        return {
            "error": f"No position for {symbol}! This action will not be allowed.",
            "symbol": symbol,
            "date": today_date
        }

    if current_position[symbol] < amount:
        return {
            "error": "Insufficient shares! This action will not be allowed.",
            "have": current_position.get(symbol, 0),
            "want_to_sell": amount,
            "symbol": symbol,
            "date": today_date
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
    return new_position


def get_price_local(symbol: str, date: str) -> Dict[str, Any]:
    """
    Get local price data - native implementation
    """
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
        return {"error": str(e), "symbol": symbol, "date": date}

    # Read data
    data_path = _workspace_data_path("merged.jsonl")
    if not data_path.exists():
        return {"error": f"Data file not found: {data_path}", "symbol": symbol, "date": date}

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
                    "error": f"Data not found for date {date}. Sample available dates: {sample_dates}",
                    "symbol": symbol,
                    "date": date
                }
            return {
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

    return {"error": f"No records found for stock {symbol} in local data", "symbol": symbol, "date": date}


def get_information(query: str) -> str:
    """
    Search and retrieve information - native implementation
    """
    def parse_date_to_standard(date_str: str) -> str:
        """Convert various date formats to standard format"""
        if not date_str or date_str == 'unknown':
            return 'unknown'

        # Handle relative time formats
        if 'ago' in date_str.lower():
            try:
                now = datetime.now()
                if 'hour' in date_str.lower():
                    hours = int(re.findall(r'\d+', date_str)[0])
                    target_date = now - timedelta(hours=hours)
                elif 'day' in date_str.lower():
                    days = int(re.findall(r'\d+', date_str)[0])
                    target_date = now - timedelta(days=days)
                elif 'week' in date_str.lower():
                    weeks = int(re.findall(r'\d+', date_str)[0])
                    target_date = now - timedelta(weeks=weeks)
                elif 'month' in date_str.lower():
                    months = int(re.findall(r'\d+', date_str)[0])
                    target_date = now - timedelta(days=months * 30)
                else:
                    return 'unknown'
                return target_date.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        # Handle ISO 8601 format
        try:
            if 'T' in date_str and ('+' in date_str or 'Z' in date_str or date_str.endswith('00:00')):
                if '+' in date_str:
                    date_part = date_str.split('+')[0]
                elif 'Z' in date_str:
                    date_part = date_str.replace('Z', '')
                else:
                    date_part = date_str

                if '.' in date_part:
                    parsed_date = datetime.strptime(date_part.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                else:
                    parsed_date = datetime.strptime(date_part, '%Y-%m-%dT%H:%M:%S')
                return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

        # Handle other common formats
        try:
            if ',' in date_str and len(date_str.split()) >= 3:
                parsed_date = datetime.strptime(date_str, '%b %d, %Y')
                return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

        try:
            if re.match(r'\d{4}-\d{2}-\d{2}$', date_str):
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
                return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

        return date_str

    def jina_search(query: str, api_key: str) -> List[str]:
        """Search using Jina API"""
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

            if json_data is None or 'data' not in json_data:
                return []

            filtered_urls = []

            for item in json_data.get('data', []):
                if 'url' not in item:
                    continue

                raw_date = item.get('date', 'unknown')
                standardized_date = parse_date_to_standard(raw_date)

                if standardized_date == 'unknown' or standardized_date == raw_date:
                    filtered_urls.append(item['url'])
                    continue

                today_date = get_config_value("TODAY_DATE")
                if today_date:
                    if today_date > standardized_date:
                        filtered_urls.append(item['url'])
                else:
                    filtered_urls.append(item['url'])

            return filtered_urls

        except Exception as e:
            logger.error(f"Jina search error: {e}")
            return []

    def jina_scrape(url: str, api_key: str) -> Dict[str, Any]:
        """Scrape URL using Jina API"""
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
                raise Exception(f"Jina AI Reader Failed for {url}: {response.status_code}")

            response_dict = response.json()

            return {
                'url': response_dict['data']['url'],
                'title': response_dict['data']['title'],
                'description': response_dict['data']['description'],
                'content': response_dict['data']['content'],
                'publish_time': response_dict['data'].get('publishedTime', 'unknown')
            }

        except Exception as e:
            return {
                'url': url,
                'content': '',
                'error': str(e)
            }

    # Main search logic
    try:
        api_key = os.environ.get("JINA_API_KEY")
        if not api_key:
            return "Error: Jina API key not provided! Please set JINA_API_KEY environment variable."

        # Search for URLs
        all_urls = jina_search(query, api_key)

        if not all_urls:
            return f"⚠️ Search query '{query}' found no results."

        # Randomly select one URL
        if len(all_urls) > 1:
            all_urls = random.sample(all_urls, 1)

        # Scrape content
        formatted_results = []
        for url in all_urls:
            result = jina_scrape(url, api_key)

            if 'error' in result:
                formatted_results.append(f"Error: {result['error']}")
            else:
                formatted_results.append(f"""
URL: {result['url']}
Title: {result['title']}
Description: {result['description']}
Publish Time: {result['publish_time']}
Content: {result['content'][:1000]}...
""")

        if not formatted_results:
            return f"⚠️ Search query '{query}' returned empty results."

        return "\n".join(formatted_results)

    except Exception as e:
        return f"❌ Search tool execution failed: {str(e)}"


# ============================================================================
# TOOL DISPATCHER
# ============================================================================

def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Any:
    """
    Execute a tool by name with given inputs

    Args:
        tool_name: Name of the tool to execute
        tool_input: Dictionary of tool inputs

    Returns:
        Tool execution result
    """
    tool_functions = {
        "buy": buy,
        "sell": sell,
        "get_price_local": get_price_local,
        "get_information": get_information
    }

    if tool_name not in tool_functions:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return tool_functions[tool_name](**tool_input)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}

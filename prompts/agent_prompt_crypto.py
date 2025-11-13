import os

from dotenv import load_dotenv

load_dotenv()
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from tools.general_tools import get_config_value
from tools.price_tools import (format_price_dict_with_names, get_open_prices,
                               get_today_init_position, get_yesterday_date,
                               get_yesterday_open_and_close_price,
                               get_yesterday_profit)

STOP_SIGNAL = "<FINISH_SIGNAL>"

agent_system_prompt_crypto = """
You are a cryptocurrency trading assistant specializing in digital asset analysis and portfolio management.

Your goals are:
- Think and reason by calling available tools.
- You need to think about the prices of various cryptocurrencies and their returns.
- Your long-term goal is to maximize returns through this cryptocurrency portfolio.
- Before making decisions, gather as much information as possible through search tools to aid decision-making.
- Monitor market trends, technical indicators, and fundamental factors affecting the crypto market.

Thinking standards:
- Clearly show key intermediate steps:
  - Read input of yesterday's positions and today's prices
  - Update valuation and adjust weights for each crypto target (if strategy requires)
  - Consider volatility, trading volume, and market sentiment for each cryptocurrency

Notes:
- You don't need to request user permission during operations, you can execute directly
- You must execute operations by calling tools, directly output operations will not be accepted
- Cryptocurrency markets operate 24/7, but we use daily UTC 00:00 as the reference point for trading
- Be aware of the high volatility nature of cryptocurrencies

Here is the information you need:

Current time:
{date}

Your current positions (numbers after crypto symbols represent how many units you hold, numbers after CASH represent your available USDT):
{positions}

The current value represented by the cryptocurrencies you hold:
{yesterday_close_price}

Current buying prices:
{today_buy_price}

When you think your task is complete, output
{STOP_SIGNAL}
"""


def get_agent_system_prompt_crypto(
    today_date: str, signature: str, market: str = "crypto", crypto_symbols: Optional[List[str]] = None
) -> str:
    print(f"signature: {signature}")
    print(f"today_date: {today_date}")
    print(f"market: {market}")

    # Use default crypto symbols if not provided
    if crypto_symbols is None:
        from agent.base_agent_crypto.base_agent_crypto import BaseAgentCrypto
        crypto_symbols = BaseAgentCrypto.DEFAULT_CRYPTO_SYMBOLS

    # Get yesterday's buy and sell prices
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(
        today_date, crypto_symbols, market=market
    )
    today_buy_price = get_open_prices(today_date, crypto_symbols, market=market)
    today_init_position = get_today_init_position(today_date, signature)
    # yesterday_profit = get_yesterday_profit(today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position)

    return agent_system_prompt_crypto.format(
        date=today_date,
        positions=today_init_position,
        STOP_SIGNAL=STOP_SIGNAL,
        yesterday_close_price=yesterday_sell_prices,
        today_buy_price=today_buy_price,
        # yesterday_profit=yesterday_profit
    )


if __name__ == "__main__":
    today_date = get_config_value("TODAY_DATE")
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")
    print(get_agent_system_prompt_crypto(today_date, signature))
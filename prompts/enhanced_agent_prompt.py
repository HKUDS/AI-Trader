"""
Enhanced agent prompt with memory, market context, and strategy framework.
"""

import os
from dotenv import load_dotenv
load_dotenv()
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.price_tools import (
    get_yesterday_date,
    get_open_prices,
    get_yesterday_open_and_close_price,
    get_today_init_position,
    get_yesterday_profit
)
from tools.general_tools import get_config_value
from tools.memory_tools import build_memory_context
from tools.market_context_tools import build_market_context
from tools.market_intelligence import MarketIntelligence
from prompts.agent_prompt import all_nasdaq_100_symbols

STOP_SIGNAL = "<FINISH_SIGNAL>"

enhanced_agent_system_prompt = """You are an advanced AI trading analyst managing a portfolio of NASDAQ 100 stocks.

=== YOUR ROLE ===
You are a disciplined, data-driven investor who:
- Makes decisions based on fundamental analysis, market trends, and risk management
- Learns from past performance to refine your strategy
- Balances growth opportunities with portfolio risk
- Maintains a long-term perspective while adapting to market conditions

=== INVESTMENT PHILOSOPHY ===
1. **Quality over Quantity**: Focus on high-conviction positions rather than excessive diversification
2. **Risk-Adjusted Returns**: Consider both potential returns AND risk (volatility, concentration)
3. **Market Awareness**: Stay informed about sector trends, market conditions, and company-specific news
4. **Adaptive Strategy**: Learn from what worked and what didn't in recent trades
5. **Capital Preservation**: Protect capital during uncertain conditions; cash is a position

=== DECISION FRAMEWORK ===

When making trading decisions, consider:

**Research & Analysis**:
- Use search tools to gather recent news, earnings reports, analyst opinions
- Look for catalysts: earnings beats, product launches, strategic partnerships
- Monitor sector trends and competitive dynamics
- Check for macroeconomic factors affecting tech stocks

**Technical Context**:
- Review momentum indicators (5-day, 20-day price movements)
- Consider volatility levels - high volatility = higher risk
- Identify oversold opportunities or overbought warnings

**Risk Management**:
- Position sizing: Limit any single position to 15-20% of portfolio
- Diversification: Hold 5-10 positions to balance concentration vs dilution
- Stop-loss consideration: Monitor positions losing >10% from entry
- Cash buffer: Maintain 10-30% cash for opportunities and risk management

**Portfolio Review**:
- Evaluate current holdings performance
- Rebalance if positions become too concentrated
- Trim winners that exceed target allocation
- Exit underperformers with deteriorating fundamentals

=== MEMORY & LEARNING ===
Review your recent trading history and performance. Ask yourself:
- What strategies worked well recently?
- Which positions underperformed and why?
- Are there patterns in successful vs unsuccessful trades?
- How can you improve decision-making based on past results?

{memory_context}

{intelligence_context}

=== MARKET CONTEXT ===
{market_context}

=== TODAY'S INFORMATION ===

**Date**: {date}

**Your Current Portfolio**:
{positions}

**Yesterday's Closing Prices**:
{yesterday_close_price}

**Today's Opening Prices** (prices you can buy/sell at):
{today_buy_price}

**Yesterday's Performance**:
{yesterday_profit}

=== EXECUTION INSTRUCTIONS ===

Follow this workflow:

1. **Review & Reflect** (2-3 steps):
   - Analyze your recent performance and current portfolio
   - Consider yesterday's results and what they tell you

2. **Research** (3-5 steps):
   - Search for news on current holdings and potential new positions
   - Look for sector trends, earnings, analyst upgrades/downgrades
   - Identify catalysts and risks

3. **Analyze** (2-3 steps):
   - Evaluate portfolio risk and concentration
   - Identify opportunities to improve risk-adjusted returns
   - Consider rebalancing needs

4. **Decide & Execute** (2-4 steps):
   - Make buy/sell decisions using the trading tools
   - Explain your reasoning for each trade
   - Document your investment thesis

5. **Finish**:
   - Summarize your actions and strategy
   - Output {STOP_SIGNAL}

=== IMPORTANT NOTES ===

- You have full authority to trade - no permission needed
- Execute trades using the buy() and sell() tools
- Search actively for information - don't rely on stale knowledge
- Be decisive but thoughtful - quality over quantity
- Document your reasoning clearly for future review
- If no good opportunities exist, it's perfectly fine to hold cash

=== RISK WARNINGS ===

⚠️ Avoid these common mistakes:
- Over-trading (churning the portfolio without good reason)
- Concentration risk (too much in one stock)
- Chasing momentum without fundamental support
- Ignoring macroeconomic headwinds
- Failing to cut losses on deteriorating positions

Now, analyze today's situation and make your trading decisions.

When complete, output {STOP_SIGNAL}
"""


def get_enhanced_agent_system_prompt(
    today_date: str,
    signature: str,
    lookback_days: int = 5,
    initial_cash: float = 10000.0
) -> str:
    """
    Generate enhanced system prompt with memory and market context.

    Args:
        today_date: Current trading date
        signature: Model signature
        lookback_days: Days of trading history to include
        initial_cash: Initial portfolio value

    Returns:
        Complete system prompt string
    """
    print(f"Generating enhanced prompt for {signature} on {today_date}")

    # Get yesterday's prices
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(
        today_date, all_nasdaq_100_symbols
    )

    # Get today's prices
    today_buy_price = get_open_prices(today_date, all_nasdaq_100_symbols)

    # Get current positions
    today_init_position = get_today_init_position(today_date, signature)

    # Calculate yesterday's profit
    yesterday_profit = get_yesterday_profit(
        today_date,
        yesterday_buy_prices,
        yesterday_sell_prices,
        today_init_position
    )

    # Build memory context
    memory_context = build_memory_context(
        signature=signature,
        current_date=today_date,
        current_positions=today_init_position,
        current_prices=today_buy_price,
        lookback_days=lookback_days,
        initial_cash=initial_cash
    )

    # Build market context
    market_context = build_market_context(
        symbols=all_nasdaq_100_symbols,
        current_date=today_date,
        current_positions=today_init_position
    )

    # Build market intelligence context
    intel = MarketIntelligence()
    intelligence_context = intel.build_intelligence_context(
        current_date=today_date,
        lookback_days=30,
        max_length=2000
    )

    # Format the prompt
    return enhanced_agent_system_prompt.format(
        date=today_date,
        positions=json.dumps(today_init_position, indent=2),
        STOP_SIGNAL=STOP_SIGNAL,
        yesterday_close_price=json.dumps(yesterday_sell_prices, indent=2),
        today_buy_price=json.dumps(today_buy_price, indent=2),
        yesterday_profit=json.dumps(yesterday_profit, indent=2),
        memory_context=memory_context,
        intelligence_context=intelligence_context,
        market_context=market_context
    )


if __name__ == "__main__":
    today_date = get_config_value("TODAY_DATE") or "2025-10-15"
    signature = get_config_value("SIGNATURE") or "claude-3.7-sonnet"

    prompt = get_enhanced_agent_system_prompt(today_date, signature)
    print(prompt)
    print(f"\n\n=== PROMPT LENGTH: {len(prompt)} characters ===")

"""
Thematic Agent 系统提示词
专门为主题集中交易策略设计的AI提示词
"""

import os
import sys
from datetime import datetime
from typing import Dict, List

# 添加项目根目录到路径
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

STOP_SIGNAL = "<FINISH_SIGNAL>"

# 主题股票池定义
THEME_STOCKS = {
    "ai_semiconductor": [
        "NVDA", "AMD", "MSFT", "GOOGL", "ASML", "AVGO",
        "QCOM", "AMAT", "ARM", "INTC", "MU"
    ]
}


thematic_agent_system_prompt = """
You are an advanced AI trading assistant specializing in **Thematic Concentrated Investment Strategy**.

## 🎯 Your Investment Philosophy

You follow a successful strategy inspired by top-performing AI traders:
- **Theme Focus**: Concentrate on high-growth themes (AI/Semiconductor sector)
- **Dynamic Rebalancing**: Actively manage position weights to optimize returns
- **High Capital Efficiency**: Maintain 98%+ invested position
- **Disciplined Profit-Taking**: Lock in gains from over-performing stocks

---

## 📊 Today's Market Context

**Date**: {date}

**Yesterday's Portfolio** (Your starting positions):
{positions}

**Yesterday's Closing Prices**:
{yesterday_close_price}

**Today's Opening Prices** (Available for trading):
{today_buy_price}

**Yesterday's Profit/Loss**:
{yesterday_profit}

---

## 🎯 Your Strategic Focus: {theme_name}

**Priority Stock Pool** (Focus your investments here):
{theme_stocks}

These stocks represent your thematic focus. Prioritize investing in these companies as they align with your investment thesis.

---

## 📋 Trading Rules & Guidelines

### 1. **Position Sizing Rules**
- ✅ **Single Stock Maximum**: No more than 20% of total portfolio value in any single stock
- ✅ **Cash Management**: Keep 1-3% cash reserve (invest 97-99% of capital)
- ✅ **Diversification**: Hold 8-12 different stocks to balance concentration and diversification

### 2. **Rebalancing Triggers**
- ⚖️ **When a stock exceeds 20% weight**: Sell partial position to reduce to ~15-18%
- 📈 **When a stock gains >30% in short period**: Consider taking partial profits
- 📉 **When a stock underperforms**: Consider reallocating to stronger performers

### 3. **Trading Execution**
- 🔍 **Research First**: Use `get_information()` to gather market intelligence before major decisions
- 💰 **Buy Priority**: Focus on theme stocks with strong momentum and positive news
- 💸 **Sell Discipline**: Exit non-core positions or over-concentrated holdings
- 🔄 **Reinvest Profits**: Use proceeds from profit-taking to strengthen core positions

### 4. **Risk Management**
- ❌ **Avoid Over-Trading**: Limit to 5-7 trades per day maximum
- ❌ **No Speculation**: Only invest in stocks within your theme focus
- ❌ **No Excessive Cash**: Don't hold more than 5% in cash unless market conditions warrant

---

## 🔧 Available Tools

You have access to the following tools:

1. **`get_information(query)`**: Search for market news, earnings reports, analyst opinions
   - Use this to inform your decisions
   - Example: `get_information("NVIDIA Q4 earnings 2025")`

2. **`buy(symbol, amount)`**: Purchase stocks
   - Example: `buy("NVDA", 10)` - Buy 10 shares of NVIDIA

3. **`sell(symbol, amount)`**: Sell stocks
   - Example: `sell("AAPL", 5)` - Sell 5 shares of Apple

4. **Math operations**: `add()`, `multiply()` for calculations

---

## 📝 Your Task for Today

**Objective**: Analyze the current portfolio and make strategic adjustments to maximize returns while following the thematic concentrated strategy.

**Steps to Follow**:

1. **📊 Portfolio Assessment**
   - Calculate current portfolio value
   - Identify position weights (value of each stock / total portfolio value)
   - Check if any position exceeds 20% weight limit

2. **🔍 Market Research** (if needed)
   - Use `get_information()` to research key stocks
   - Look for earnings reports, news, sector trends
   - Focus on your theme stocks: {theme_stocks}

3. **⚖️ Rebalancing Decisions**
   - If any stock > 20% weight: Sell partial position to ~15-18%
   - If cash > 3%: Deploy into high-conviction theme stocks
   - Consider adding positions in underweight theme stocks with positive outlook

4. **💼 Execute Trades**
   - Use `buy()` and `sell()` tools to execute your decisions
   - Show your reasoning for each trade
   - Update portfolio progressively

5. **✅ Completion**
   - Review final portfolio composition
   - Ensure diversification (8-12 stocks)
   - Verify cash level is 1-3%
   - Output: {STOP_SIGNAL}

---

## 💡 Example Decision-Making Process

**Good Example**:
```
Step 1: Calculate portfolio value
- NVDA: 15 shares × $250 = $3,750 (25% weight) ⚠️ OVER LIMIT
- MSFT: 5 shares × $450 = $2,250 (15% weight) ✅
- Cash: $100 (0.7%) ✅
- Total: $15,000

Step 2: Research
get_information("NVIDIA stock outlook October 2025")
→ Strong AI demand, positive outlook

Step 3: Rebalancing decision
- NVDA is over 20% limit, but has strong outlook
- Sell partial NVDA to reduce to 18% weight
- Reinvest proceeds in underweight theme stock (AMD or ASML)

Step 4: Execute
sell("NVDA", 4) → Reduces NVDA to ~18%
buy("AMD", 8) → Adds position in theme stock
```

---

## ⚠️ Important Notes

- **You must execute trades using tools** - Simply stating intent is not enough
- **Show your calculations** - Be transparent about position sizing
- **Stay focused on theme** - Prioritize {theme_stocks}
- **Don't overthink** - Make decisions and execute
- **End with signal** - Always output {STOP_SIGNAL} when done

---

## 🚀 Let's Trade!

Analyze today's positions and execute your thematic concentrated strategy. Remember:
- Focus on {theme_name}
- Keep positions under 20%
- Maintain 98%+ invested
- Take profits and reinvest

Good luck! 📈
"""


def get_thematic_agent_system_prompt(
    today_date: str,
    signature: str,
    theme: str = "ai_semiconductor"
) -> str:
    """
    生成主题集中策略的系统提示词

    Args:
        today_date: 当前日期
        signature: Agent标识
        theme: 投资主题

    Returns:
        格式化的系统提示词
    """
    # 所有NASDAQ 100股票
    all_nasdaq_100_symbols = [
        "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
        "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
        "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
        "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
        "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
        "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
        "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
        "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
        "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
        "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
        "ON", "BIIB", "LULU", "CDW", "GFS"
    ]

    # 获取市场数据
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(
        today_date, all_nasdaq_100_symbols
    )
    today_buy_price = get_open_prices(today_date, all_nasdaq_100_symbols)
    today_init_position = get_today_init_position(today_date, signature)
    yesterday_profit = get_yesterday_profit(
        today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position
    )

    # 获取主题股票列表
    theme_stocks_list = THEME_STOCKS.get(theme, THEME_STOCKS["ai_semiconductor"])
    theme_stocks_str = ", ".join(theme_stocks_list)
    theme_name = theme.replace("_", " ").title()

    # 格式化提示词
    return thematic_agent_system_prompt.format(
        date=today_date,
        positions=today_init_position,
        yesterday_close_price=yesterday_sell_prices,
        today_buy_price=today_buy_price,
        yesterday_profit=yesterday_profit,
        theme_name=theme_name,
        theme_stocks=theme_stocks_str,
        STOP_SIGNAL=STOP_SIGNAL
    )


if __name__ == "__main__":
    # 测试代码
    today_date = get_config_value("TODAY_DATE") or "2025-10-24"
    signature = get_config_value("SIGNATURE") or "test-thematic"

    print("生成主题集中策略提示词...")
    print("="*60)

    prompt = get_thematic_agent_system_prompt(today_date, signature, "ai_semiconductor")
    print(prompt[:1000])  # 只打印前1000字符
    print("\n... (省略部分内容) ...")
    print(f"\n总长度: {len(prompt)} 字符")

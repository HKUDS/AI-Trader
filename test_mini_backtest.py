#!/usr/bin/env python3
"""
Ultra-simple backtest test
"""

import asyncio
import os
import sys

# Set environment variables directly
os.environ["OPENAI_API_BASE"] = "https://api.siliconflow.cn/v1"
# Read from .env file
with open('/home/user/AI-Trader/.env') as f:
    for line in f:
        if line.startswith('OPENAI_API_KEY='):
            os.environ["OPENAI_API_KEY"] = line.split('=', 1)[1].strip().strip('"')

sys.path.insert(0, '/home/user/AI-Trader')

from langchain_openai import ChatOpenAI
from tools.price_tools import get_open_prices

async def mini_backtest():
    print("🚀 Mini Backtest Test\n")
    
    # Initialize model
    model = ChatOpenAI(
        model='zai-org/GLM-4.5',
        base_url=os.environ["OPENAI_API_BASE"],
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=30
    )
    
    # Get prices
    today = "2025-01-02"
    symbols = ["AAPL", "MSFT", "GOOGL"]
    prices = get_open_prices(today, symbols, market="us")
    
    print(f"📅 Date: {today}")
    print(f"💰 Cash: $10,000")
    print(f"\n📈 Today's Prices:")
    for sym in symbols:
        print(f"  {sym}: ${prices.get(f'{sym}_price', 0):.2f}")
    
    # Create prompt
    prompt = f"""You are a stock trading AI. Today is {today}. You have $10,000 cash.

Today's opening prices:
- AAPL: ${prices['AAPL_price']:.2f}
- MSFT: ${prices['MSFT_price']:.2f}  
- GOOGL: ${prices['GOOGL_price']:.2f}

Make 1-2 trading decisions. Respond ONLY with valid JSON (no markdown):
{{"decisions": [{{"action": "buy", "symbol": "AAPL", "amount": 10}}]}}

Your decision:"""
    
    print(f"\n🤖 Sending request to AI...")
    response = await model.ainvoke(prompt)
    print(f"\n📝 AI Response:")
    print(response.content[:500])
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(mini_backtest())

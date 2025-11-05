"""
Minimal test of simple agent
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

async def test():
    print("🧪 Testing Simple Agent Components...")
    
    # Test 1: Model initialization
    print("\n1️⃣ Testing model initialization...")
    try:
        model = ChatOpenAI(
            model='deepseek-ai/DeepSeek-R1',
            base_url=os.getenv('OPENAI_API_BASE'),
            api_key=os.getenv('OPENAI_API_KEY'),
            timeout=30
        )
        print("✅ Model initialized")
    except Exception as e:
        print(f"❌ Model init failed: {e}")
        return
    
    # Test 2: Simple API call
    print("\n2️⃣ Testing simple API call...")
    try:
        response = await model.ainvoke("Say 'test successful' in 3 words")
        print(f"✅ API call successful")
        print(f"Response: {response.content}")
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return
    
    # Test 3: JSON parsing from response
    print("\n3️⃣ Testing JSON response...")
    prompt = """Please respond in this exact JSON format:
```json
{
  "status": "ok",
  "message": "test"
}
```
"""
    try:
        response = await model.ainvoke(prompt)
        print(f"✅ JSON request successful")
        print(f"Response:\n{response.content}")
    except Exception as e:
        print(f"❌ JSON request failed: {e}")
        return
    
    # Test 4: Import price tools
    print("\n4️⃣ Testing price tools import...")
    try:
        from tools.price_tools import get_open_prices, is_trading_day
        print("✅ Price tools imported")
        
        # Test if we can check trading day
        is_trading = is_trading_day("2025-01-02", market="us")
        print(f"✅ is_trading_day works: 2025-01-02 is {'trading' if is_trading else 'not trading'}")
        
        # Test getting prices
        prices = get_open_prices("2025-01-02", ["AAPL", "MSFT"], market="us")
        print(f"✅ get_open_prices works: AAPL=${prices.get('AAPL_price', 0):.2f}")
        
    except Exception as e:
        print(f"❌ Price tools failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    asyncio.run(test())

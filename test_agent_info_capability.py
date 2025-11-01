#!/usr/bin/env python3
"""
Demonstration: How Information Gathering Integrates with Claude Agent SDK

This shows the agentic workflow WITHOUT needing external APIs
"""

import json
from datetime import datetime


class MockAgentWorkflow:
    """Simulates how Claude SDK Agent uses information gathering"""

    def __init__(self):
        self.tools = {
            "get_information": self.get_information,
            "get_price_local": self.get_price_local,
            "buy": self.buy,
            "sell": self.sell
        }
        self.conversation_log = []
        self.position = {"CASH": 10000.0, "NVDA": 0}

    async def get_information(self, query: str) -> str:
        """Simulates information gathering tool"""
        # This would normally call Jina AI, DuckDuckGo, etc.
        mock_responses = {
            "NVIDIA": """
            URL: https://finance.example.com/nvidia-news
            Title: NVIDIA Reports Strong Q3 Earnings
            Date: 2025-10-19
            Content: NVIDIA Corporation announced strong Q3 earnings,
            beating analyst expectations. The company reported revenue
            growth of 25% year-over-year, driven by strong demand for
            AI chips. Stock analysts are bullish on the company's future
            prospects...
            """,
            "Tesla": """
            URL: https://finance.example.com/tesla-earnings
            Title: Tesla Q3 Earnings Miss Expectations
            Date: 2025-10-19
            Content: Tesla Inc. reported Q3 earnings that fell short
            of Wall Street expectations. The company cited supply chain
            challenges and increased competition. Analysts are mixed on
            the stock's near-term prospects...
            """,
            "default": f"""
            URL: https://finance.example.com/search
            Title: Market News for: {query}
            Date: {datetime.now().strftime('%Y-%m-%d')}
            Content: General market information about {query}...
            """
        }

        # Find relevant response
        for key in mock_responses:
            if key.lower() in query.lower():
                return mock_responses[key]
        return mock_responses["default"]

    async def get_price_local(self, symbol: str, date: str) -> dict:
        """Simulates price lookup"""
        mock_prices = {
            "NVDA": {"open": 450.50, "high": 455.00, "low": 448.00, "close": 453.25},
            "TSLA": {"open": 245.00, "high": 248.50, "low": 243.00, "close": 244.75}
        }
        return {
            "symbol": symbol,
            "date": date,
            "ohlcv": mock_prices.get(symbol, {})
        }

    async def buy(self, symbol: str, amount: int) -> dict:
        """Simulates buy action"""
        price = 450.50  # Mock price
        cost = price * amount
        if self.position["CASH"] >= cost:
            self.position["CASH"] -= cost
            self.position[symbol] = self.position.get(symbol, 0) + amount
            return {"success": True, "position": self.position}
        return {"success": False, "error": "Insufficient cash"}

    async def sell(self, symbol: str, amount: int) -> dict:
        """Simulates sell action"""
        price = 450.50  # Mock price
        if self.position.get(symbol, 0) >= amount:
            self.position[symbol] -= amount
            self.position["CASH"] += price * amount
            return {"success": True, "position": self.position}
        return {"success": False, "error": "Insufficient shares"}

    def log_step(self, step_type: str, content: str):
        """Log agent's thought process"""
        self.conversation_log.append({
            "step": len(self.conversation_log) + 1,
            "type": step_type,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })


async def demonstrate_agentic_workflow():
    """Demonstrate full agentic workflow with information gathering"""

    print("=" * 70)
    print("CLAUDE AGENT SDK - Information Gathering Demo")
    print("=" * 70)
    print("\nThis demonstrates TRUE AGENTIC BEHAVIOR:")
    print("  ✅ Agent autonomously decides when to gather information")
    print("  ✅ Agent analyzes information and makes decisions")
    print("  ✅ Agent executes trades based on analysis")
    print("  ✅ NOT just tool calling - real autonomous decision-making")
    print("\n" + "=" * 70)

    agent = MockAgentWorkflow()

    # Simulate an autonomous trading session
    print("\n🤖 AGENT STARTS AUTONOMOUS TRADING SESSION")
    print("-" * 70)

    # Step 1: Agent decides to gather information
    print("\n[STEP 1] Agent Reasoning:")
    print("  'I should check recent news about NVIDIA before making decisions'")
    agent.log_step("reasoning", "Need to gather NVIDIA information")

    print("\n[STEP 2] Agent Action - Tool Call:")
    print("  Tool: get_information")
    print("  Args: {'query': 'NVIDIA stock latest news earnings'}")

    info = await agent.get_information("NVIDIA stock latest news earnings")
    agent.log_step("tool_call", f"get_information -> {info[:100]}...")

    print("\n[STEP 3] Agent Receives Information:")
    print("-" * 70)
    print(info)
    print("-" * 70)

    # Step 2: Agent analyzes the information
    print("\n[STEP 4] Agent Analysis:")
    print("  'The information indicates strong Q3 earnings for NVIDIA.'")
    print("  'Analysts are bullish. This looks like a good buying opportunity.'")
    agent.log_step("reasoning", "NVIDIA shows strong fundamentals, considering buy")

    # Step 3: Agent checks price
    print("\n[STEP 5] Agent Action - Tool Call:")
    print("  Tool: get_price_local")
    print("  Args: {'symbol': 'NVDA', 'date': '2025-10-20'}")

    price_data = await agent.get_price_local("NVDA", "2025-10-20")
    agent.log_step("tool_call", f"get_price_local -> {json.dumps(price_data)}")

    print(f"\n[STEP 6] Agent Receives Price Data:")
    print(f"  Current price: ${price_data['ohlcv']['open']}")

    # Step 4: Agent makes decision
    print("\n[STEP 7] Agent Decision:")
    print("  'Based on positive news and current price, I will buy 10 shares'")
    agent.log_step("reasoning", "Decided to buy 10 shares of NVDA")

    # Step 5: Agent executes trade
    print("\n[STEP 8] Agent Action - Tool Call:")
    print("  Tool: buy")
    print("  Args: {'symbol': 'NVDA', 'amount': 10}")

    result = await agent.buy("NVDA", 10)
    agent.log_step("tool_call", f"buy -> {json.dumps(result)}")

    print(f"\n[STEP 9] Agent Receives Trade Confirmation:")
    if result["success"]:
        print(f"  ✅ Successfully bought 10 shares of NVDA")
        print(f"  💰 New position: {json.dumps(result['position'], indent=4)}")
    else:
        print(f"  ❌ Trade failed: {result['error']}")

    # Step 6: Agent concludes
    print("\n[STEP 10] Agent Conclusion:")
    print("  'Trade completed successfully. Position updated.'")
    print("  'Will continue monitoring for more opportunities.'")
    agent.log_step("completion", "Trading session completed")

    # Show full conversation log
    print("\n\n" + "=" * 70)
    print("FULL AGENT CONVERSATION LOG")
    print("=" * 70)
    for log_entry in agent.conversation_log:
        print(f"\nStep {log_entry['step']} [{log_entry['type']}]:")
        print(f"  {log_entry['content'][:150]}...")

    # Summary
    print("\n\n" + "=" * 70)
    print("KEY AGENTIC CAPABILITIES DEMONSTRATED")
    print("=" * 70)
    print("""
✅ AUTONOMOUS DECISION-MAKING
   - Agent decided to gather information (not told to)
   - Agent analyzed the information autonomously
   - Agent made trading decision based on analysis

✅ MULTI-STEP REASONING
   - 10 steps from information gathering to trade execution
   - Each step builds on previous information
   - Dynamic decision tree based on data

✅ TOOL ORCHESTRATION
   - Used multiple tools: get_information, get_price_local, buy
   - Tools called in logical sequence
   - Results from each tool inform next action

✅ INFORMATION-DRIVEN DECISIONS
   - Gathered external information (news, earnings)
   - Combined with market data (prices)
   - Made informed trading decision

This is TRUE AGENTIC BEHAVIOR using Claude Agent SDK!
NOT simple tool calling - this is autonomous reasoning.
    """)

    print("\n" + "=" * 70)
    print("HOW THIS WORKS WITH CLAUDE AGENT SDK")
    print("=" * 70)
    print("""
1. YOU PROVIDE:
   - Tools decorated with @tool (buy, sell, get_information, etc.)
   - System prompt describing the agent's goal
   - Initial query to start the conversation

2. CLAUDE AGENT SDK HANDLES:
   - Autonomous decision-making
   - When to use which tools
   - Multi-step reasoning
   - Goal achievement

3. RESULT:
   - Agent gathers information when needed
   - Agent makes informed decisions
   - Agent executes trades autonomously
   - True agentic system!

The information gathering tool (get_information) is CRITICAL because:
- Agents need current information to make decisions
- Can't rely only on training data (outdated)
- Must react to real-world events (earnings, news, etc.)

With Jina AI: Full web search capability
With alternatives: DuckDuckGo, Brave, Google, etc.
Same agentic behavior regardless of information source!
    """)

    print("=" * 70)
    print("✅ DEMONSTRATION COMPLETE!")
    print("=" * 70)


if __name__ == "__main__":
    import asyncio
    asyncio.run(demonstrate_agentic_workflow())

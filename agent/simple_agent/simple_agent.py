"""
Simple Agent without MCP tools
Agent outputs trading decisions in JSON format based on price data in prompt
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI

from tools.price_tools import (
    get_open_prices,
    get_yesterday_date,
    is_trading_day,
)


class SimpleAgent:
    """Simplified trading agent that doesn't use MCP tools"""

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        log_path: str = "./data/agent_data",
        max_steps: int = 1,  # Simplified: only one decision per day
        max_retries: int = 3,
        base_delay: float = 1.0,
        initial_cash: float = 10000.0,
        market: str = "us",
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.signature = signature
        self.basemodel = basemodel
        self.stock_symbols = stock_symbols or []
        self.base_log_path = log_path
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.market = market
        
        # API configuration
        self.openai_base_url = openai_base_url or os.getenv("OPENAI_API_BASE")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        
        # Data paths
        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")
        
        # Initialize LLM
        self._init_model()
        
        print(f"✅ Agent {self.signature} initialization completed")

    def _init_model(self):
        """Initialize the LLM model"""
        try:
            # Special handling for Qwen models
            model_kwargs = {}
            if "qwen" in self.basemodel.lower():
                model_kwargs["extra_body"] = {"enable_thinking": False}
            
            self.model = ChatOpenAI(
                model=self.basemodel,
                base_url=self.openai_base_url,
                api_key=self.openai_api_key,
                max_retries=3,
                timeout=120,
                model_kwargs=model_kwargs,
            )
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

    def register_agent(self) -> None:
        """Register new agent, create initial positions"""
        if os.path.exists(self.position_file):
            print(f"⚠️ Position file {self.position_file} already exists, skipping registration")
            return

        # Create directory
        position_dir = os.path.join(self.data_path, "position")
        os.makedirs(position_dir, exist_ok=True)
        print(f"📁 Created position directory: {position_dir}")

        # Initialize positions (all stocks start with 0, only CASH has value)
        init_position = {symbol: 0 for symbol in self.stock_symbols}
        init_position["CASH"] = self.initial_cash

        # Write to file
        with open(self.position_file, "w") as f:
            f.write(
                json.dumps(
                    {
                        "date": "init",
                        "id": 0,
                        "positions": init_position,
                    }
                )
                + "\n"
            )

        print(f"✅ Agent {self.signature} registration completed")
        print(f"📁 Position file: {self.position_file}")
        print(f"💰 Initial cash: ${self.initial_cash:,.2f}")
        print(f"📊 Number of stocks: {len(self.stock_symbols)}")

    def get_latest_position(self, today_date: str) -> tuple[Dict[str, int], int]:
        """Get the latest position and action ID"""
        current_position = {symbol: 0 for symbol in self.stock_symbols}
        current_position["CASH"] = self.initial_cash
        current_action_id = 0

        if not os.path.exists(self.position_file):
            return current_position, current_action_id

        with open(self.position_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                doc = json.loads(line)
                if doc.get("date") == today_date:
                    continue
                current_position = doc.get("positions", current_position)
                current_action_id = doc.get("id", current_action_id)

        return current_position, current_action_id

    def execute_trades(
        self, 
        decisions: List[Dict[str, Any]], 
        today_date: str,
        prices: Dict[str, float]
    ) -> Dict[str, Any]:
        """Execute trading decisions and update positions"""
        current_position, current_action_id = self.get_latest_position(today_date)
        
        for decision in decisions:
            action = decision.get("action", "").lower()
            symbol = decision.get("symbol", "")
            amount = decision.get("amount", 0)
            
            if action not in ["buy", "sell"] or symbol not in self.stock_symbols:
                continue
            
            price = prices.get(f"{symbol}_price", 0)
            if price == 0:
                print(f"⚠️ No price data for {symbol}, skipping")
                continue
            
            # Validate and execute trade
            if action == "buy":
                cost = price * amount
                if current_position["CASH"] >= cost:
                    current_position["CASH"] -= cost
                    current_position[symbol] += amount
                    current_action_id += 1
                    
                    # Write to position file
                    with open(self.position_file, "a") as f:
                        f.write(json.dumps({
                            "date": today_date,
                            "id": current_action_id,
                            "this_action": {
                                "action": "buy",
                                "symbol": symbol,
                                "amount": amount,
                                "price": price
                            },
                            "positions": current_position.copy()
                        }) + "\n")
                    
                    print(f"✅ BUY {amount} shares of {symbol} @ ${price:.2f}")
                else:
                    print(f"⚠️ Insufficient cash to buy {symbol}")
            
            elif action == "sell":
                if current_position[symbol] >= amount:
                    revenue = price * amount
                    current_position["CASH"] += revenue
                    current_position[symbol] -= amount
                    current_action_id += 1
                    
                    # Write to position file
                    with open(self.position_file, "a") as f:
                        f.write(json.dumps({
                            "date": today_date,
                            "id": current_action_id,
                            "this_action": {
                                "action": "sell",
                                "symbol": symbol,
                                "amount": amount,
                                "price": price
                            },
                            "positions": current_position.copy()
                        }) + "\n")
                    
                    print(f"✅ SELL {amount} shares of {symbol} @ ${price:.2f}")
                else:
                    print(f"⚠️ Insufficient shares to sell {symbol}")
        
        # If no trades, record no-trade
        if current_action_id == self.get_latest_position(today_date)[1]:
            with open(self.position_file, "a") as f:
                f.write(json.dumps({
                    "date": today_date,
                    "id": current_action_id + 1,
                    "this_action": {
                        "action": "no_trade",
                        "symbol": "",
                        "amount": 0
                    },
                    "positions": current_position.copy()
                }) + "\n")
            print(f"📊 No trading for {today_date}")
        
        return current_position

    async def run_trading_session(self, today_date: str) -> None:
        """Run one trading session for a specific date"""
        print(f"📈 Starting trading session: {today_date}")
        
        # Get current position
        current_position, _ = self.get_latest_position(today_date)
        
        # Get today's opening prices
        try:
            prices = get_open_prices(today_date, self.stock_symbols, market=self.market)
        except Exception as e:
            print(f"❌ Failed to get prices: {e}")
            return
        
        # Get yesterday's date and prices for reference
        yesterday = get_yesterday_date(today_date)
        try:
            yesterday_prices = get_open_prices(yesterday, self.stock_symbols, market=self.market)
        except:
            yesterday_prices = {}
        
        # Build prompt with all necessary information
        prompt = self._build_trading_prompt(
            today_date, 
            current_position, 
            prices,
            yesterday_prices
        )
        
        # Get AI decision
        try:
            response = await self.model.ainvoke(prompt)
            decision_text = response.content
            print(f"🤖 AI Response:\n{decision_text}\n")
            
            # Parse decisions from response
            decisions = self._parse_decisions(decision_text)
            
            # Execute trades
            if decisions:
                self.execute_trades(decisions, today_date, prices)
            else:
                print(f"📊 No valid trading decisions for {today_date}")
                # Record no-trade
                _, current_action_id = self.get_latest_position(today_date)
                with open(self.position_file, "a") as f:
                    f.write(json.dumps({
                        "date": today_date,
                        "id": current_action_id + 1,
                        "this_action": {"action": "no_trade", "symbol": "", "amount": 0},
                        "positions": current_position.copy()
                    }) + "\n")
        
        except Exception as e:
            print(f"❌ Trading session error: {str(e)}")
            raise

    def _build_trading_prompt(
        self,
        today_date: str,
        current_position: Dict[str, Any],
        today_prices: Dict[str, float],
        yesterday_prices: Dict[str, float]
    ) -> str:
        """Build the trading prompt with all necessary data"""
        
        # Calculate portfolio value
        portfolio_value = current_position["CASH"]
        holdings_info = []
        
        for symbol in self.stock_symbols:
            shares = current_position.get(symbol, 0)
            if shares > 0:
                price = today_prices.get(f"{symbol}_price", 0)
                value = shares * price
                portfolio_value += value
                holdings_info.append(f"  - {symbol}: {shares} shares @ ${price:.2f} = ${value:.2f}")
        
        holdings_text = "\n".join(holdings_info) if holdings_info else "  (No holdings)"
        
        # Format price data
        price_data_lines = []
        for symbol in self.stock_symbols[:20]:  # Limit to first 20 to avoid token limits
            today_price = today_prices.get(f"{symbol}_price", 0)
            yesterday_price = yesterday_prices.get(f"{symbol}_price", 0)
            
            if today_price > 0:
                if yesterday_price > 0:
                    change = ((today_price - yesterday_price) / yesterday_price) * 100
                    price_data_lines.append(
                        f"  {symbol}: ${today_price:.2f} (Yesterday: ${yesterday_price:.2f}, "
                        f"Change: {change:+.2f}%)"
                    )
                else:
                    price_data_lines.append(f"  {symbol}: ${today_price:.2f}")
        
        price_data_text = "\n".join(price_data_lines)
        
        prompt = f"""You are an expert stock trading AI agent. Today is {today_date}.

CURRENT PORTFOLIO:
- Cash: ${current_position['CASH']:,.2f}
- Total Portfolio Value: ${portfolio_value:,.2f}
- Holdings:
{holdings_text}

TODAY'S MARKET DATA (Opening Prices):
{price_data_text}

YOUR TASK:
Analyze the market data and make trading decisions. You can BUY or SELL stocks based on:
1. Price trends (comparing today vs yesterday)
2. Your current portfolio allocation
3. Risk management principles
4. Market momentum

RULES:
- You have ${current_position['CASH']:,.2f} cash available
- You can only sell stocks you currently own
- Consider diversification (don't put all money in one stock)
- Each trade should be for reasonable amounts (e.g., multiples of 10 shares)

OUTPUT FORMAT:
Please respond with your trading decisions in the following JSON format:

```json
{{
  "analysis": "Brief market analysis and reasoning",
  "decisions": [
    {{"action": "buy", "symbol": "AAPL", "amount": 10}},
    {{"action": "sell", "symbol": "MSFT", "amount": 5}}
  ]
}}
```

If you decide not to trade today, return:
```json
{{
  "analysis": "Reason for not trading",
  "decisions": []
}}
```

Make your decision now:"""
        
        return prompt

    def _parse_decisions(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse trading decisions from AI response"""
        try:
            # Try to find JSON in markdown code blocks first
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON directly
                json_match = re.search(r'\{.*?"decisions".*?\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    return []
            
            data = json.loads(json_str)
            decisions = data.get("decisions", [])
            
            print(f"📋 Parsed {len(decisions)} trading decisions")
            if data.get("analysis"):
                print(f"💭 Analysis: {data['analysis']}")
            
            return decisions
        
        except Exception as e:
            print(f"⚠️ Failed to parse decisions: {e}")
            print(f"Response was:\n{response_text}")
            return []

    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """Get trading date list"""
        dates = []
        max_date = None

        if not os.path.exists(self.position_file):
            self.register_agent()
            max_date = init_date
        else:
            # Read existing position file
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc["date"]
                    if current_date == "init":
                        continue
                    if max_date is None:
                        max_date = current_date
                    else:
                        current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
                        max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
                        if current_date_obj > max_date_obj:
                            max_date = current_date

        # Check if new dates need to be processed
        max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")

        if end_date_obj <= max_date_obj:
            return []

        # Generate trading date list
        trading_dates = []
        current_date = max_date_obj + timedelta(days=1)

        while current_date <= end_date_obj:
            date_str = current_date.strftime("%Y-%m-%d")
            if is_trading_day(date_str, market=self.market):
                trading_dates.append(date_str)
            current_date += timedelta(days=1)

        return trading_dates

    async def run_date_range(self, init_date: str, end_date: str) -> None:
        """Run trading for a date range"""
        print(f"📅 Running date range: {init_date} to {end_date}")

        trading_dates = self.get_trading_dates(init_date, end_date)

        if not trading_dates:
            print(f"ℹ️ No trading days to process")
            return

        print(f"📊 Trading days to process: {trading_dates}")

        for date in trading_dates:
            print(f"\n{'='*60}")
            print(f"🔄 Processing {self.signature} - Date: {date}")
            print(f"{'='*60}")

            for attempt in range(1, self.max_retries + 1):
                try:
                    print(f"🔄 Attempt {attempt}/{self.max_retries}")
                    await self.run_trading_session(date)
                    print(f"✅ {date} completed successfully")
                    break
                except Exception as e:
                    print(f"❌ Attempt {attempt} failed: {str(e)}")
                    if attempt < self.max_retries:
                        delay = self.base_delay * (2 ** (attempt - 1))
                        print(f"⏳ Waiting {delay} seconds before retry...")
                        await asyncio.sleep(delay)
                    else:
                        print(f"💥 All retries failed for {date}")
                        raise

        print(f"\n✅ {self.signature} processing completed")

"""
BaseAgentCrypto - Advanced Cryptocurrency Trading Agent

Features:
- 24/7 trading (no market close)
- Multi-exchange support (ByBit, Binance, Coinbase, Kraken)
- Derivatives trading (USDT perpetual futures)
- 30s to 1h intervals
- Symbol sorting by 24h change
- Multi-provider AI support
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp import MCPToolkit
from dotenv import load_dotenv

load_dotenv()

# Import tools and prompts
from tools.general_tools import get_config_value, write_config_value
from prompts.agent_prompt_crypto import get_crypto_trading_prompt


class BaseAgentCrypto:
    """
    Cryptocurrency Trading Agent
    
    Supports:
    - Multiple exchanges (ByBit primary)
    - Derivatives/Perpetual futures
    - 24/7 trading
    - Dynamic symbol selection by 24h change
    - Multi-timeframe analysis (30s - 1h)
    """
    
    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        log_path: str = "./data/agent_data_crypto",
        max_steps: int = 30,
        max_retries: int = 3,
        base_delay: float = 1.0,
        initial_cash: float = 10000.0,
        init_date: Optional[str] = None,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        exchange: str = "bybit",
        trading_interval: str = "1m",
        asset_type: str = "derivatives",
        top_symbols: int = 50,
        testnet: bool = True
    ):
        """
        Initialize Crypto Trading Agent
        
        Args:
            signature: Model signature for logging
            basemodel: AI model identifier
            stock_symbols: Crypto symbols (auto-fetched if None)
            log_path: Path for trading logs
            max_steps: Maximum reasoning steps
            max_retries: Retry attempts for failed operations
            base_delay: Delay between operations
            initial_cash: Starting capital (USDT)
            init_date: Start date (supports datetime format)
            openai_base_url: Custom API endpoint
            openai_api_key: API key
            exchange: Primary exchange (bybit, binance, coinbase, kraken)
            trading_interval: Trading timeframe (30s, 1m, 5m, 15m, 30m, 1h)
            asset_type: derivatives or spot
            top_symbols: Number of top symbols by 24h change
            testnet: Use testnet mode (True recommended for testing)
        """
        self.signature = signature
        self.basemodel = basemodel
        self.market = "crypto"
        self.exchange = exchange
        self.trading_interval = trading_interval
        self.asset_type = asset_type
        self.top_symbols = top_symbols
        self.testnet = testnet
        
        # Trading parameters
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        
        # Paths
        self.log_path = Path(log_path)
        self.position_dir = self.log_path / signature / "position"
        self.log_dir = self.log_path / signature / "log"
        self.position_file = self.position_dir / "position.jsonl"
        
        # Create directories
        self.position_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # API configuration
        self.openai_base_url = openai_base_url or os.getenv("OPENAI_API_BASE")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        
        # Initialize components (will be set in initialize())
        self.llm = None
        self.agent_executor = None
        self.current_date = None
        
        # Stock symbols (crypto pairs)
        if stock_symbols is None:
            # Auto-fetch top symbols by 24h change
            self.stock_symbols = self._get_top_crypto_symbols()
        else:
            self.stock_symbols = stock_symbols
        
        # Initialize date
        if init_date:
            if ' ' in init_date:  # Datetime format
                self.current_date = datetime.strptime(init_date, "%Y-%m-%d %H:%M:%S")
            else:  # Date only
                self.current_date = datetime.strptime(init_date, "%Y-%m-%d")
        else:
            self.current_date = datetime.now()
        
        # Initialize position
        self._initialize_position()
        
        print(f"✅ BaseAgentCrypto initialized:")
        print(f"   - Exchange: {self.exchange}")
        print(f"   - Asset type: {self.asset_type}")
        print(f"   - Trading interval: {self.trading_interval}")
        print(f"   - Top symbols: {self.top_symbols}")
        print(f"   - Testnet: {self.testnet}")
        print(f"   - Initial cash: ${self.initial_cash:,.2f} USDT")
        print(f"   - Start date: {self.current_date}")
        print(f"   - Symbols: {len(self.stock_symbols)} pairs")
    
    def _get_top_crypto_symbols(self) -> List[str]:
        """
        Fetch top cryptocurrency symbols sorted by 24h change
        
        Returns:
            List of crypto trading pairs (e.g., ['BTCUSDT', 'ETHUSDT', ...])
        """
        try:
            from agent_tools.tool_crypto_exchange import get_top_derivatives
            
            symbols = get_top_derivatives(
                exchange=self.exchange,
                sort_by="24h_change",
                order="desc",
                limit=self.top_symbols,
                asset_type=self.asset_type,
                testnet=self.testnet
            )
            
            print(f"✅ Fetched {len(symbols)} top crypto symbols by 24h change")
            return symbols
            
        except Exception as e:
            print(f"⚠️ Failed to fetch symbols, using defaults: {e}")
            # Default fallback symbols
            return [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                "ADAUSDT", "DOGEUSDT", "MATICUSDT", "DOTUSDT", "AVAXUSDT"
            ]
    
    def _initialize_position(self):
        """Initialize position file if not exists"""
        if not self.position_file.exists():
            initial_position = {
                "date": self.current_date.strftime("%Y-%m-%d %H:%M:%S"),
                "id": 0,
                "this_action": {
                    "action": "initialize",
                    "exchange": self.exchange,
                    "testnet": self.testnet
                },
                "positions": {
                    "CASH": self.initial_cash
                }
            }
            
            with open(self.position_file, "w") as f:
                json.dump(initial_position, f)
                f.write("\n")
            
            print(f"✅ Initialized position file: {self.position_file}")
    
    async def initialize(self):
        """Initialize MCP connection and AI model"""
        try:
            # Initialize LLM with custom API endpoint
            self.llm = ChatOpenAI(
                model=self.basemodel,
                base_url=self.openai_base_url,
                api_key=self.openai_api_key,
                temperature=0.7,
            )
            
            # Initialize MCP toolkit
            toolkit = MCPToolkit()
            
            # MCP server configurations
            mcp_servers = {
                "math": {
                    "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT', 8000)}/sse"
                },
                "search": {
                    "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT', 8001)}/sse"
                },
                "trade": {
                    "url": f"http://localhost:{os.getenv('TRADE_HTTP_PORT', 8002)}/sse"
                },
                "getprice": {
                    "url": f"http://localhost:{os.getenv('GETPRICE_HTTP_PORT', 8003)}/sse"
                }
            }
            
            # Add all MCP tools
            for server_name, config in mcp_servers.items():
                try:
                    await toolkit.add_mcp_server(server_name, config["url"])
                    print(f"✅ Connected to MCP server: {server_name}")
                except Exception as e:
                    print(f"⚠️ Failed to connect to {server_name}: {e}")
            
            # Get crypto trading prompt
            prompt = get_crypto_trading_prompt(
                exchange=self.exchange,
                asset_type=self.asset_type,
                trading_interval=self.trading_interval,
                symbols=self.stock_symbols[:10]  # Show first 10 in prompt
            )
            
            # Create agent
            agent = create_tool_calling_agent(
                llm=self.llm,
                tools=toolkit.get_tools(),
                prompt=prompt
            )
            
            # Create agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=toolkit.get_tools(),
                max_iterations=self.max_steps,
                verbose=True,
                handle_parsing_errors=True,
                return_intermediate_steps=True
            )
            
            print(f"✅ Agent executor created successfully")
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            raise
    
    async def trade_single_interval(self, timestamp: datetime):
        """
        Execute trading for a single time interval
        
        Args:
            timestamp: Current trading timestamp
        """
        try:
            # Update current date
            self.current_date = timestamp
            
            # Write current date to config
            write_config_value("CURRENT_DATE", timestamp.strftime("%Y-%m-%d %H:%M:%S"))
            
            print(f"\n{'='*60}")
            print(f"🕐 Trading interval: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            # Read current position
            current_position = self._read_current_position()
            cash = current_position.get("CASH", self.initial_cash)
            
            # Create trading input
            trading_input = {
                "input": f"""
Current time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Exchange: {self.exchange} ({'TESTNET' if self.testnet else 'LIVE'})
Asset type: {self.asset_type}
Trading interval: {self.trading_interval}
Available cash: ${cash:,.2f} USDT
Current positions: {json.dumps(current_position, indent=2)}

Available symbols (top {self.top_symbols} by 24h change):
{', '.join(self.stock_symbols[:20])}

Analyze the market and make your trading decision.
You can:
1. Open new positions (long/short)
2. Close existing positions
3. Hold current positions
4. Adjust position sizes

Consider:
- 24h price changes and volatility
- Market sentiment and news
- Technical indicators
- Risk management (position sizing, stop loss)
- Funding rates (for perpetual futures)

Make your decision and execute trades if needed.
"""
            }
            
            # Execute agent
            result = await self.agent_executor.ainvoke(trading_input)
            
            # Log results
            log_file = self.log_dir / timestamp.strftime("%Y-%m-%d") / "log.jsonl"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(log_file, "a") as f:
                log_entry = {
                    "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "interval": self.trading_interval,
                    "exchange": self.exchange,
                    "output": result.get("output", ""),
                    "intermediate_steps": str(result.get("intermediate_steps", []))
                }
                json.dump(log_entry, f)
                f.write("\n")
            
            print(f"✅ Trading interval completed: {timestamp}")
            
        except Exception as e:
            print(f"❌ Error in trading interval {timestamp}: {e}")
            import traceback
            traceback.print_exc()
    
    def _read_current_position(self) -> Dict[str, Any]:
        """Read current position from position file"""
        if not self.position_file.exists():
            return {"CASH": self.initial_cash}
        
        try:
            with open(self.position_file, "r") as f:
                lines = f.readlines()
                if lines:
                    last_position = json.loads(lines[-1])
                    return last_position.get("positions", {"CASH": self.initial_cash})
        except Exception as e:
            print(f"⚠️ Failed to read position: {e}")
        
        return {"CASH": self.initial_cash}
    
    async def run_date_range(self, start_date: str, end_date: str):
        """
        Run trading for a date range with specified interval
        
        Args:
            start_date: Start datetime (YYYY-MM-DD HH:MM:SS or YYYY-MM-DD)
            end_date: End datetime (YYYY-MM-DD HH:MM:SS or YYYY-MM-DD)
        """
        # Parse dates
        if ' ' in start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        else:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        
        if ' ' in end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        else:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Parse trading interval
        interval_map = {
            "30s": timedelta(seconds=30),
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
        }
        
        interval_delta = interval_map.get(self.trading_interval, timedelta(minutes=1))
        
        print(f"\n🚀 Starting crypto trading backtest:")
        print(f"   - Exchange: {self.exchange}")
        print(f"   - Period: {start_dt} to {end_dt}")
        print(f"   - Interval: {self.trading_interval}")
        print(f"   - Total periods: {int((end_dt - start_dt) / interval_delta)}")
        
        current_dt = start_dt
        interval_count = 0
        
        while current_dt <= end_dt:
            interval_count += 1
            print(f"\n📊 Interval {interval_count}: {current_dt}")
            
            await self.trade_single_interval(current_dt)
            
            # Move to next interval
            current_dt += interval_delta
            
            # Small delay to avoid rate limits
            await asyncio.sleep(self.base_delay)
        
        print(f"\n✅ Backtest completed: {interval_count} intervals processed")
        
        # Print final summary
        self.print_summary()
    
    def print_summary(self):
        """Print trading summary"""
        try:
            with open(self.position_file, "r") as f:
                lines = f.readlines()
                
            print(f"\n{'='*60}")
            print(f"📊 TRADING SUMMARY - {self.signature}")
            print(f"{'='*60}")
            print(f"Exchange: {self.exchange}")
            print(f"Asset type: {self.asset_type}")
            print(f"Total intervals: {len(lines)}")
            
            if lines:
                final_position = json.loads(lines[-1])
                positions = final_position.get("positions", {})
                cash = positions.get("CASH", 0)
                
                print(f"\n💰 Final Position:")
                print(f"   - Cash: ${cash:,.2f} USDT")
                print(f"   - P&L: ${cash - self.initial_cash:,.2f} USDT")
                print(f"   - Return: {((cash / self.initial_cash - 1) * 100):.2f}%")
                
                # Show open positions
                open_positions = {k: v for k, v in positions.items() if k != "CASH" and v != 0}
                if open_positions:
                    print(f"\n📈 Open Positions:")
                    for symbol, amount in open_positions.items():
                        print(f"   - {symbol}: {amount}")
            
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"⚠️ Failed to print summary: {e}")
    
    def get_position_summary(self) -> Dict[str, Any]:
        """Get position summary"""
        try:
            with open(self.position_file, "r") as f:
                lines = f.readlines()
                
            if lines:
                final_position = json.loads(lines[-1])
                return {
                    "latest_date": final_position.get("date"),
                    "total_records": len(lines),
                    "positions": final_position.get("positions", {}),
                    "exchange": self.exchange,
                    "testnet": self.testnet
                }
        except Exception as e:
            print(f"⚠️ Failed to get summary: {e}")
        
        return {
            "latest_date": None,
            "total_records": 0,
            "positions": {"CASH": self.initial_cash}
        }
"""
EnhancedClaudeSDKAgent - Enhanced agent using official Claude Agent SDK with memory

This extends ClaudeSDKAgent with:
- Trading memory across sessions
- Market context awareness
- Portfolio analytics tools
- Technical analysis tools
- Enhanced prompting with investment philosophy
"""

import os
import json
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import add_no_trade_record
from prompts.enhanced_agent_prompt import get_enhanced_agent_system_prompt, STOP_SIGNAL
from agent.claude_sdk_agent.enhanced_sdk_tools import create_enhanced_trading_server

load_dotenv()


class EnhancedClaudeSDKAgent:
    """
    Enhanced trading agent using official Claude Agent SDK with memory and analytics.

    Features:
    - Full trading memory (5 days of history by default)
    - Portfolio analytics (concentration, metrics, position analysis)
    - Technical analysis (momentum, volatility, market movers)
    - Enhanced prompt with investment philosophy
    - Risk management framework
    """

    DEFAULT_STOCK_SYMBOLS = [
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

    def __init__(
        self,
        signature: str,
        basemodel: str = "sonnet",  # Use latest sonnet
        stock_symbols: Optional[List[str]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 30,  # Increased for thorough analysis
        max_retries: int = 3,
        base_delay: float = 0.5,
        anthropic_api_key: Optional[str] = None,
        initial_cash: float = 10000.0,
        init_date: str = "2025-10-13",
        memory_lookback_days: int = 5,  # NEW: Days of memory to include
    ):
        """
        Initialize EnhancedClaudeSDKAgent

        Args:
            signature: Agent signature/name
            basemodel: Model name (default: "sonnet" for latest)
            stock_symbols: List of stock symbols
            log_path: Log path
            max_steps: Maximum reasoning steps (30 for enhanced analysis)
            max_retries: Maximum retry attempts
            base_delay: Base delay for retries
            anthropic_api_key: Anthropic API key
            initial_cash: Initial cash amount
            init_date: Initialization date
            memory_lookback_days: Days of trading history to include in context
        """
        self.signature = signature
        self.basemodel = basemodel
        self.stock_symbols = stock_symbols or self.DEFAULT_STOCK_SYMBOLS
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date
        self.memory_lookback_days = memory_lookback_days  # NEW

        # Set log path
        self.base_log_path = log_path or "./data/agent_data"

        # Set Anthropic API key
        if anthropic_api_key is None:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        else:
            self.anthropic_api_key = anthropic_api_key

        # Initialize SDK client (will be set during initialize)
        self.client: Optional[ClaudeSDKClient] = None
        self.trading_server = None

        # Data paths
        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")

    async def initialize(self) -> None:
        """Initialize Claude SDK client with enhanced tools"""
        print(f"🚀 Initializing Enhanced Claude SDK agent: {self.signature}")
        print(f"   Model: {self.basemodel}")
        print(f"   Memory lookback: {self.memory_lookback_days} days")
        print(f"   Max steps: {self.max_steps}")

        # Validate API key
        if not self.anthropic_api_key:
            raise ValueError(
                "❌ Anthropic API key not set. "
                "Please configure ANTHROPIC_API_KEY in environment or config file."
            )

        try:
            # Create ENHANCED trading MCP server (10 tools vs 4)
            self.trading_server = create_enhanced_trading_server()
            print(f"✅ Enhanced trading tools server created (10 tools)")

            # Create SDK client with options
            options = ClaudeAgentOptions(
                model=self.basemodel,
                mcp_servers=[self.trading_server],
                max_turns=self.max_steps
            )

            self.client = ClaudeSDKClient(options)
            print(f"✅ Claude SDK client initialized")

        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize Enhanced Claude SDK client: {e}")

        print(f"✅ Enhanced agent {self.signature} initialization completed")

    def _setup_logging(self, today_date: str) -> str:
        """Set up log file path"""
        log_path = os.path.join(self.base_log_path, self.signature, 'log', today_date)
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        return os.path.join(log_path, "log.jsonl")

    def _log_message(self, log_file: str, message: Dict[str, Any]) -> None:
        """Log message to log file"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "signature": self.signature,
            "message": message
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session with enhanced prompt and memory

        Args:
            today_date: Trading date
        """
        print(f"📈 Starting ENHANCED trading session: {today_date}")

        # Set up logging
        log_file = self._setup_logging(today_date)

        # Get ENHANCED system prompt with memory and market context
        system_prompt = get_enhanced_agent_system_prompt(
            today_date=today_date,
            signature=self.signature,
            lookback_days=self.memory_lookback_days,
            initial_cash=self.initial_cash
        )

        print(f"   Prompt length: {len(system_prompt)} characters (vs ~500 for base)")
        print(f"   Memory: {self.memory_lookback_days} days of trading history")
        print(f"   Tools: 10 (4 original + 6 enhanced)")

        # Update client options with enhanced system prompt
        self.client.options.system_prompt = system_prompt

        # Enhanced initial user query
        user_query = (
            f"Good morning! Today is {today_date}. "
            f"Review your portfolio, analyze market conditions, and make "
            f"your trading decisions for today. Remember to:\n"
            f"1. Review recent performance and learn from past trades\n"
            f"2. Research current holdings and potential opportunities\n"
            f"3. Consider risk management and portfolio balance\n"
            f"4. Execute trades with clear reasoning\n\n"
            f"Take your time to analyze thoroughly before trading."
        )

        # Log initial message
        self._log_message(log_file, {"role": "user", "content": user_query})

        print(f"🤖 Starting enhanced agent conversation...")

        # Use the SDK's query method for agent interaction
        try:
            # Send query and receive agent responses
            await self.client.query(user_query)

            # Get responses from agent
            step_count = 0
            session_complete = False

            while step_count < self.max_steps and not session_complete:
                step_count += 1
                print(f"🔄 Step {step_count}/{self.max_steps}")

                # Receive response from agent
                response = await self.client.receive_response()

                # Log response
                self._log_message(log_file, {
                    "role": "assistant",
                    "content": response.get("content", ""),
                    "step": step_count
                })

                # Check response content
                content = response.get("content", "")
                if isinstance(content, str):
                    # Print first 200 chars
                    preview = content[:200] + "..." if len(content) > 200 else content
                    print(f"   Agent: {preview}")

                    # Check for stop signal
                    if STOP_SIGNAL in content:
                        print("✅ Received stop signal, trading session ended")
                        session_complete = True
                        break

                # Check if agent is done
                if response.get("is_done", False):
                    print("✅ Agent completed task")
                    session_complete = True
                    break

            if not session_complete:
                print(f"⚠️ Reached max steps ({self.max_steps}), ending session")

        except Exception as e:
            print(f"❌ Trading session error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

        # Handle trading results
        await self._handle_trading_result(today_date)

        print(f"✅ Enhanced trading session completed for {today_date}")

    async def _handle_trading_result(self, today_date: str) -> None:
        """Handle trading results"""
        if_trade = get_config_value("IF_TRADE")
        if if_trade:
            write_config_value("IF_TRADE", False)
            print("✅ Trading completed")
        else:
            print("📊 No trading, maintaining positions")
            try:
                add_no_trade_record(today_date, self.signature)
            except Exception as e:
                print(f"❌ Error adding no-trade record: {e}")
            write_config_value("IF_TRADE", False)

    async def run_date_range(self, start_date: str, end_date: str) -> None:
        """
        Run trading sessions for a date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        from datetime import datetime, timedelta

        print(f"📅 Running enhanced trading from {start_date} to {end_date}")

        current_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        while current_dt <= end_dt:
            # Skip weekends
            if current_dt.weekday() < 5:  # Monday = 0, Friday = 4
                current_date = current_dt.strftime("%Y-%m-%d")

                # Update TODAY_DATE config
                write_config_value("TODAY_DATE", current_date)

                # Run trading session
                await self.run_trading_session(current_date)

            current_dt += timedelta(days=1)

        print(f"🎉 Completed enhanced trading from {start_date} to {end_date}")

    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of current positions"""
        from tools.price_tools import get_latest_position

        today_date = get_config_value("TODAY_DATE")
        if not today_date:
            return {"error": "TODAY_DATE not configured"}

        try:
            positions, action_id = get_latest_position(today_date, self.signature)

            return {
                "date": today_date,
                "action_id": action_id,
                "positions": positions,
                "num_positions": len([k for k, v in positions.items() if k != "CASH" and v > 0]),
                "cash": positions.get("CASH", 0)
            }
        except Exception as e:
            return {"error": str(e)}


if __name__ == "__main__":
    # Test the enhanced agent
    import anyio

    async def test():
        agent = EnhancedClaudeSDKAgent(
            signature="test-enhanced-sdk",
            basemodel="sonnet",  # Latest Claude Sonnet
            initial_cash=10000.0,
            max_steps=30,
            memory_lookback_days=5
        )

        await agent.initialize()
        print("\n✅ Enhanced Claude SDK Agent initialized successfully!")
        print(f"   Tools available: 10 (vs 4 in base agent)")
        print(f"   Memory: {agent.memory_lookback_days} days")
        print(f"   Model: {agent.basemodel}")

    anyio.run(test)

"""
ClaudeSDKAgent class - Agent using official Claude Agent SDK

This uses the official claude-agent-sdk package with proper agentic capabilities,
not just tool calling. It creates a true autonomous agent with the SDK.
"""

import os
import json
import anyio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from dotenv import load_dotenv
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

# Import project tools
import sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import add_no_trade_record
from prompts.agent_prompt import get_agent_system_prompt, STOP_SIGNAL
from agent.claude_sdk_agent.sdk_tools import create_trading_server

# Load environment variables
load_dotenv()


class ClaudeSDKAgent:
    """
    Trading agent using official Claude Agent SDK

    This is a proper agentic system using:
    - ClaudeSDKClient for bidirectional conversations
    - In-process MCP servers for tools
    - Full agent autonomy with decision-making capabilities
    """

    # Default NASDAQ 100 stock symbols
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
        basemodel: str = "claude-sonnet-4-20250514",
        stock_symbols: Optional[List[str]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 10,
        max_retries: int = 3,
        base_delay: float = 0.5,
        anthropic_api_key: Optional[str] = None,
        initial_cash: float = 10000.0,
        init_date: str = "2025-10-13"
    ):
        """
        Initialize ClaudeSDKAgent

        Args:
            signature: Agent signature/name
            basemodel: Model name (e.g., "claude-sonnet-4-20250514")
            stock_symbols: List of stock symbols
            log_path: Log path
            max_steps: Maximum reasoning steps per trading session
            max_retries: Maximum retry attempts
            base_delay: Base delay time for retries
            anthropic_api_key: Anthropic API key
            initial_cash: Initial cash amount
            init_date: Initialization date
        """
        self.signature = signature
        self.basemodel = basemodel
        self.stock_symbols = stock_symbols or self.DEFAULT_STOCK_SYMBOLS
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date

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
        """Initialize Claude SDK client and tools"""
        print(f"🚀 Initializing Claude SDK agent: {self.signature}")

        # Validate API key
        if not self.anthropic_api_key:
            raise ValueError(
                "❌ Anthropic API key not set. "
                "Please configure ANTHROPIC_API_KEY in environment or config file."
            )

        try:
            # Create trading MCP server
            self.trading_server = create_trading_server()
            print(f"✅ Trading tools server created")

            # Create SDK client with options
            options = ClaudeAgentOptions(
                model=self.basemodel,
                mcp_servers=[self.trading_server],
                max_turns=self.max_steps
            )

            self.client = ClaudeSDKClient(options)
            print(f"✅ Claude SDK client initialized")

        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize Claude SDK client: {e}")

        print(f"✅ Agent {self.signature} initialization completed")

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
        Run single day trading session using Claude SDK

        Args:
            today_date: Trading date
        """
        print(f"📈 Starting trading session: {today_date}")

        # Set up logging
        log_file = self._setup_logging(today_date)

        # Get system prompt with current market data
        system_prompt = get_agent_system_prompt(today_date, self.signature)

        # Update client options with system prompt
        self.client.options.system_prompt = system_prompt

        # Initial user query
        user_query = f"Please analyze and update today's ({today_date}) positions."

        # Log initial message
        self._log_message(log_file, {"role": "user", "content": user_query})

        print(f"🤖 Starting agent conversation...")

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
                    print(f"   Agent: {content[:200]}...")

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
            raise

        # Handle trading results
        await self._handle_trading_result(today_date)

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
            except NameError as e:
                print(f"❌ NameError: {e}")
                raise
            write_config_value("IF_TRADE", False)

    def register_agent(self) -> None:
        """Register new agent, create initial positions"""
        # Check if position file already exists
        if os.path.exists(self.position_file):
            print(f"⚠️ Position file {self.position_file} already exists, skipping registration")
            return

        # Ensure directory structure exists
        position_dir = os.path.join(self.data_path, "position")
        if not os.path.exists(position_dir):
            os.makedirs(position_dir)
            print(f"📁 Created position directory: {position_dir}")

        # Create initial positions
        init_position = {symbol: 0 for symbol in self.stock_symbols}
        init_position['CASH'] = self.initial_cash

        with open(self.position_file, "w") as f:
            f.write(json.dumps({
                "date": self.init_date,
                "id": 0,
                "positions": init_position
            }) + "\n")

        print(f"✅ Agent {self.signature} registration completed")
        print(f"📁 Position file: {self.position_file}")
        print(f"💰 Initial cash: ${self.initial_cash}")
        print(f"📊 Number of stocks: {len(self.stock_symbols)}")

    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """
        Get trading date list

        Args:
            init_date: Start date
            end_date: End date

        Returns:
            List of trading dates
        """
        max_date = None

        if not os.path.exists(self.position_file):
            self.register_agent()
            max_date = init_date
        else:
            # Read existing position file, find latest date
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc['date']
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
            if current_date.weekday() < 5:  # Weekdays
                trading_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        return trading_dates

    async def run_with_retry(self, today_date: str) -> None:
        """Run method with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"🔄 Attempting to run {self.signature} - {today_date} (Attempt {attempt})")
                await self.run_trading_session(today_date)
                print(f"✅ {self.signature} - {today_date} run successful")
                return
            except Exception as e:
                print(f"❌ Attempt {attempt} failed: {str(e)}")
                if attempt == self.max_retries:
                    print(f"💥 {self.signature} - {today_date} all retries failed")
                    raise
                else:
                    wait_time = self.base_delay * attempt
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    await anyio.sleep(wait_time)

    async def run_date_range(self, init_date: str, end_date: str) -> None:
        """
        Run all trading days in date range

        Args:
            init_date: Start date
            end_date: End date
        """
        print(f"📅 Running date range: {init_date} to {end_date}")

        # Get trading date list
        trading_dates = self.get_trading_dates(init_date, end_date)

        if not trading_dates:
            print(f"ℹ️ No trading days to process")
            return

        print(f"📊 Trading days to process: {trading_dates}")

        # Process each trading day
        for date in trading_dates:
            print(f"🔄 Processing {self.signature} - Date: {date}")

            # Set configuration
            write_config_value("TODAY_DATE", date)
            write_config_value("SIGNATURE", self.signature)

            try:
                await self.run_with_retry(date)
            except Exception as e:
                print(f"❌ Error processing {self.signature} - Date: {date}")
                print(e)
                raise

        print(f"✅ {self.signature} processing completed")

    def get_position_summary(self) -> Dict[str, Any]:
        """Get position summary"""
        if not os.path.exists(self.position_file):
            return {"error": "Position file does not exist"}

        positions = []
        with open(self.position_file, "r") as f:
            for line in f:
                positions.append(json.loads(line))

        if not positions:
            return {"error": "No position records"}

        latest_position = positions[-1]
        return {
            "signature": self.signature,
            "latest_date": latest_position.get("date"),
            "positions": latest_position.get("positions", {}),
            "total_records": len(positions)
        }

    def __str__(self) -> str:
        return f"ClaudeSDKAgent(signature='{self.signature}', basemodel='{self.basemodel}', stocks={len(self.stock_symbols)})"

    def __repr__(self) -> str:
        return self.__str__()

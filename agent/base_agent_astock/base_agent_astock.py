"""
BaseAgentAStock class - A股专用交易Agent基类
Chinese A-shares specific trading agent base class
Encapsulates core functionality for A-shares trading including MCP tool management, AI agent creation, and trading execution
"""

import asyncio
import json
import os
# Import project tools
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


class DeepSeekChatOpenAI(ChatOpenAI):
    """
    Custom ChatOpenAI wrapper for DeepSeek API compatibility.
    Handles the case where DeepSeek returns tool_calls.args as JSON strings instead of dicts.
    """

    def _create_message_dicts(self, messages: list, stop: Optional[list] = None) -> list:
        """Override to handle response parsing"""
        message_dicts = super()._create_message_dicts(messages, stop)
        return message_dicts

    def _generate(self, messages: list, stop: Optional[list] = None, **kwargs):
        """Override generation to fix tool_calls format in responses"""
        # Call parent's generate method
        result = super()._generate(messages, stop, **kwargs)

        # Fix tool_calls format in the generated messages
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                # If arguments is a string, parse it
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass  # Keep as string if parsing fails

        return result

    async def _agenerate(self, messages: list, stop: Optional[list] = None, **kwargs):
        """Override async generation to fix tool_calls format in responses"""
        # Call parent's async generate method
        result = await super()._agenerate(messages, stop, **kwargs)

        # Fix tool_calls format in the generated messages
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                # If arguments is a string, parse it
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass  # Keep as string if parsing fails

        return result


from prompts.agent_prompt_astock import (STOP_SIGNAL,
                                         get_agent_system_prompt_astock)
from tools.general_tools import (extract_conversation, extract_tool_messages,
                                 get_config_value, write_config_value)
from tools.price_tools import add_no_trade_record

# Load environment variables
load_dotenv()


class BaseAgentAStock:
    """
    A股专用交易Agent基类
    Chinese A-shares specific trading agent base class

    Main functionalities:
    1. MCP tool management and connection
    2. AI agent creation and configuration
    3. Trading execution and decision loops (with A-shares specific rules)
    4. Logging and management
    5. Position and configuration management
    """

    # Default SSE 50 stock symbols (A-shares only)
    DEFAULT_SSE50_SYMBOLS = [
        "600519.SH",
        "601318.SH",
        "600036.SH",
        "601899.SH",
        "600900.SH",
        "601166.SH",
        "600276.SH",
        "600030.SH",
        "603259.SH",
        "688981.SH",
        "688256.SH",
        "601398.SH",
        "688041.SH",
        "601211.SH",
        "601288.SH",
        "601328.SH",
        "688008.SH",
        "600887.SH",
        "600150.SH",
        "601816.SH",
        "601127.SH",
        "600031.SH",
        "688012.SH",
        "603501.SH",
        "601088.SH",
        "600309.SH",
        "601601.SH",
        "601668.SH",
        "603993.SH",
        "601012.SH",
        "601728.SH",
        "600690.SH",
        "600809.SH",
        "600941.SH",
        "600406.SH",
        "601857.SH",
        "601766.SH",
        "601919.SH",
        "600050.SH",
        "600760.SH",
        "601225.SH",
        "600028.SH",
        "601988.SH",
        "688111.SH",
        "601985.SH",
        "601888.SH",
        "601628.SH",
        "601600.SH",
        "601658.SH",
        "600048.SH",
    ]

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 10,
        max_retries: int = 3,
        base_delay: float = 0.5,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_cash: float = 100000.0,  # 默认10万人民币
        init_date: str = "2025-10-09",
        market: str = "cn",  # 接受但忽略此参数，始终使用"cn"
    ):
        """
        Initialize BaseAgentAStock

        Args:
            signature: Agent signature/name
            basemodel: Base model name
            stock_symbols: List of stock symbols, defaults to SSE 50
            mcp_config: MCP tool configuration, including port and URL information
            log_path: Log path, defaults to ./data/agent_data_astock
            max_steps: Maximum reasoning steps
            max_retries: Maximum retry attempts
            base_delay: Base delay time for retries
            openai_base_url: OpenAI API base URL
            openai_api_key: OpenAI API key
            initial_cash: Initial cash amount (default: 100000.0 RMB)
            init_date: Initialization date
            market: Market type (accepted for compatibility, but always uses "cn")
        """
        self.signature = signature
        self.basemodel = basemodel
        self.market = "cn"  # 硬编码为A股市场

        # 默认使用上证50成分股
        if stock_symbols is None:
            self.stock_symbols = self.DEFAULT_SSE50_SYMBOLS
        else:
            self.stock_symbols = stock_symbols

        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date

        # Set MCP configuration
        self.mcp_config = mcp_config or self._get_default_mcp_config()

        # Set log path - A股专用路径
        self.base_log_path = log_path or "./data/agent_data_astock"

        # Set OpenAI configuration
        if openai_base_url == None:
            self.openai_base_url = os.getenv("OPENAI_API_BASE")
        else:
            self.openai_base_url = openai_base_url
        if openai_api_key == None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        else:
            self.openai_api_key = openai_api_key

        # Initialize components
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: Optional[List] = None
        self.model: Optional[ChatOpenAI] = None
        self.agent: Optional[Any] = None

        # Data paths
        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")

    def _get_default_mcp_config(self) -> Dict[str, Dict[str, Any]]:
        """Get default MCP configuration"""
        return {
            "math": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT', '8000')}/mcp",
            },
            "stock_local": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('GETPRICE_HTTP_PORT', '8003')}/mcp",
            },
            "search": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT', '8004')}/mcp",
            },
            "trade": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('TRADE_HTTP_PORT', '8002')}/mcp",
            },
        }

    async def initialize(self) -> None:
        """Initialize MCP client and AI model"""
        print(f"🚀 Initializing A-shares agent: {self.signature}")

        # Validate OpenAI configuration
        if not self.openai_api_key:
            raise ValueError(
                "❌ OpenAI API key not set. Please configure OPENAI_API_KEY in environment or config file."
            )
        if not self.openai_base_url:
            print("⚠️  OpenAI base URL not set, using default")

        try:
            # Create MCP client
            self.client = MultiServerMCPClient(self.mcp_config)

            # Get tools
            self.tools = await self.client.get_tools()
            if not self.tools:
                print("⚠️  Warning: No MCP tools loaded. MCP services may not be running.")
                print(f"   MCP configuration: {self.mcp_config}")
            else:
                print(f"✅ Loaded {len(self.tools)} MCP tools")
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to initialize MCP client: {e}\n"
                f"   Please ensure MCP services are running at the configured ports.\n"
                f"   Run: python agent_tools/start_mcp_services.py"
            )

        try:
            # Create AI model - use custom DeepSeekChatOpenAI for DeepSeek models
            # to handle tool_calls.args format differences (JSON string vs dict)
            if "deepseek" in self.basemodel.lower():
                self.model = DeepSeekChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30,
                )
            else:
                self.model = ChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30,
                )
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

        # Note: agent will be created in run_trading_session() based on specific date
        # because system_prompt needs the current date and price information

        print(f"✅ A-shares agent {self.signature} initialization completed")

    def _setup_logging(self, today_date: str) -> str:
        """Set up log file path"""
        log_path = os.path.join(self.base_log_path, self.signature, "log", today_date)
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        return os.path.join(log_path, "log.jsonl")

    def _log_message(self, log_file: str, new_messages: List[Dict[str, str]]) -> None:
        """Log messages to log file"""
        log_entry = {"timestamp": datetime.now().isoformat(), "signature": self.signature, "new_messages": new_messages}
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    async def _ainvoke_with_retry(self, message: List[Dict[str, str]]) -> Any:
        """Agent invocation with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.agent.ainvoke({"messages": message}, {"recursion_limit": 100})
            except Exception as e:
                if attempt == self.max_retries:
                    raise e
                print(f"⚠️ Attempt {attempt} failed, retrying after {self.base_delay * attempt} seconds...")
                print(f"Error details: {e}")
                await asyncio.sleep(self.base_delay * attempt)

    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session (A-shares specific)

        Args:
            today_date: Trading date
        """
        print(f"📈 Starting A-shares trading session: {today_date}")

        # Set up logging
        log_file = self._setup_logging(today_date)

        # Update system prompt - 使用A股专用提示词
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=get_agent_system_prompt_astock(today_date, self.signature, self.stock_symbols),
        )

        # Initial user query
        user_query = [{"role": "user", "content": f"请分析并更新今日（{today_date}）的持仓。"}]
        message = user_query.copy()

        # Log initial message
        self._log_message(log_file, user_query)

        # Trading loop
        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            print(f"🔄 Step {current_step}/{self.max_steps}")

            try:
                # Call agent
                response = await self._ainvoke_with_retry(message)

                # Extract agent response
                agent_response = extract_conversation(response, "final")

                # Check stop signal
                if STOP_SIGNAL in agent_response:
                    print("✅ Received stop signal, trading session ended")
                    print(agent_response)
                    self._log_message(log_file, [{"role": "assistant", "content": agent_response}])
                    break

                # Extract tool messages
                tool_msgs = extract_tool_messages(response)
                tool_response = "\n".join([msg.content for msg in tool_msgs])

                # Prepare new messages
                new_messages = [
                    {"role": "assistant", "content": agent_response},
                    {"role": "user", "content": f"Tool results: {tool_response}"},
                ]

                # Add new messages
                message.extend(new_messages)

                # Log messages
                self._log_message(log_file, new_messages[0])
                self._log_message(log_file, new_messages[1])

            except Exception as e:
                print(f"❌ Trading session error: {str(e)}")
                print(f"Error details: {e}")
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
        # Check if position.jsonl file already exists
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
        init_position["CASH"] = self.initial_cash
        # Normalize init_date to zero-padded HH if time exists
        init_date_str = self.init_date
        if " " in init_date_str:
            try:
                # If already proper format, keep it
                datetime.strptime(init_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    date_part, time_part = init_date_str.split(" ", 1)
                    hh, mm, ss = time_part.split(":")
                    init_date_str = f"{date_part} {hh.zfill(2)}:{mm}:{ss}"
                except Exception:
                    # Fallback: keep original if unexpected
                    pass

        with open(self.position_file, "w") as f:  # Use "w" mode to ensure creating new file
            f.write(json.dumps({"date": init_date_str, "id": 0, "positions": init_position}) + "\n")

        print(f"✅ A-shares agent {self.signature} registration completed")
        print(f"📁 Position file: {self.position_file}")
        print(f"💰 Initial cash: ¥{self.initial_cash:,.2f}")
        print(f"📊 Number of stocks: {len(self.stock_symbols)}")

    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """
        Get trading date list, filtered by actual trading days in A-shares market

        Args:
            init_date: Start date
            end_date: End date

        Returns:
            List of trading dates (excluding weekends and holidays)
        """
        from tools.price_tools import is_trading_day

        dates = []
        max_date = None

        if not os.path.exists(self.position_file):
            self.register_agent()
            max_date = init_date
        else:
            # Read existing position file, find latest date
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc["date"]
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

        # Generate trading date list, filtered by actual trading days (A-shares market)
        trading_dates = []
        current_date = max_date_obj + timedelta(days=1)

        while current_date <= end_date_obj:
            date_str = current_date.strftime("%Y-%m-%d")
            # Check if this is an actual trading day in A-shares market
            if is_trading_day(date_str, market="cn"):
                trading_dates.append(date_str)
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
                    await asyncio.sleep(wait_time)

    async def run_date_range(self, init_date: str, end_date: str) -> None:
        """
        Run all trading days in date range

        Args:
            init_date: Start date
            end_date: End date
        """
        print(f"📅 Running A-shares date range: {init_date} to {end_date}")

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
            "total_records": len(positions),
        }

    def __str__(self) -> str:
        return (
            f"BaseAgentAStock(signature='{self.signature}', basemodel='{self.basemodel}', "
            f"market='cn', stocks={len(self.stock_symbols)})"
        )

    def __repr__(self) -> str:
        return self.__str__()

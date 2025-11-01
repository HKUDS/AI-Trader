"""
EnhancedAgent class - Advanced trading agent with memory, market context, and analytics.

This agent extends BaseAgent with:
- Trading memory across sessions
- Market context awareness
- Portfolio analytics tools
- Technical analysis tools
- Risk management framework
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from agent.base_agent.base_agent import BaseAgent
from prompts.enhanced_agent_prompt import get_enhanced_agent_system_prompt
from langchain.agents import create_agent
from typing import Optional, List, Dict, Any


class EnhancedAgent(BaseAgent):
    """
    Enhanced trading agent with memory and advanced analytics.

    Inherits from BaseAgent but uses:
    - Enhanced prompt system with memory and market context
    - Additional MCP tools for portfolio and technical analysis
    - Same execution framework for backward compatibility
    """

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 30,  # Increased from 10 for more thorough analysis
        max_retries: int = 3,
        base_delay: float = 0.5,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_cash: float = 10000.0,
        init_date: str = "2025-10-13",
        memory_lookback_days: int = 5,
    ):
        """
        Initialize EnhancedAgent.

        Args:
            signature: Agent signature/name
            basemodel: Base model name
            stock_symbols: List of stock symbols
            mcp_config: MCP tool configuration
            log_path: Log path
            max_steps: Maximum reasoning steps (default 30 for enhanced analysis)
            max_retries: Maximum retry attempts
            base_delay: Base delay for retries
            openai_base_url: OpenAI API base URL
            openai_api_key: OpenAI API key
            initial_cash: Initial cash amount
            init_date: Initialization date
            memory_lookback_days: Days of trading history to include in context
        """
        # Get enhanced MCP config if not provided
        if mcp_config is None:
            mcp_config = self._get_enhanced_mcp_config()

        # Initialize parent
        super().__init__(
            signature=signature,
            basemodel=basemodel,
            stock_symbols=stock_symbols,
            mcp_config=mcp_config,
            log_path=log_path,
            max_steps=max_steps,
            max_retries=max_retries,
            base_delay=base_delay,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
            initial_cash=initial_cash,
            init_date=init_date
        )

        # Enhanced agent specific settings
        self.memory_lookback_days = memory_lookback_days

    def _get_enhanced_mcp_config(self) -> Dict[str, Dict[str, Any]]:
        """Get MCP configuration including enhanced tools."""
        base_config = super()._get_default_mcp_config()

        # Add enhanced tools
        base_config["portfolio_analytics"] = {
            "transport": "streamable_http",
            "url": f"http://localhost:{os.getenv('PORTFOLIO_HTTP_PORT', '8004')}/mcp",
        }

        base_config["technical_analysis"] = {
            "transport": "streamable_http",
            "url": f"http://localhost:{os.getenv('TECHNICAL_HTTP_PORT', '8005')}/mcp",
        }

        return base_config

    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session with enhanced prompt.

        Args:
            today_date: Trading date
        """
        print(f"📈 Starting enhanced trading session: {today_date}")

        # Set up logging
        log_file = self._setup_logging(today_date)

        # Use enhanced prompt system
        enhanced_prompt = get_enhanced_agent_system_prompt(
            today_date=today_date,
            signature=self.signature,
            lookback_days=self.memory_lookback_days,
            initial_cash=self.initial_cash
        )

        # Create agent with enhanced prompt
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=enhanced_prompt,
        )

        # Enhanced initial user query
        user_query = [{
            "role": "user",
            "content": (
                f"Good morning! Today is {today_date}. "
                f"Review your portfolio, analyze market conditions, and make "
                f"your trading decisions for today. Remember to:\n"
                f"1. Review recent performance and learn from past trades\n"
                f"2. Research current holdings and potential opportunities\n"
                f"3. Consider risk management and portfolio balance\n"
                f"4. Execute trades with clear reasoning\n\n"
                f"Take your time to analyze thoroughly before trading."
            )
        }]

        message = user_query.copy()

        # Log initial message
        self._log_message(log_file, user_query)

        # Trading loop (inherited from BaseAgent)
        from prompts.enhanced_agent_prompt import STOP_SIGNAL
        from tools.general_tools import extract_conversation, extract_tool_messages

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
                tool_response = '\n'.join([msg.content for msg in tool_msgs])

                # Prepare new messages
                new_messages = [
                    {"role": "assistant", "content": agent_response},
                    {"role": "user", "content": f'Tool results: {tool_response}'}
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

        # Handle trading results (inherited)
        await self._handle_trading_result(today_date)

        print(f"✅ Enhanced trading session completed for {today_date}")


if __name__ == "__main__":
    # Test the enhanced agent
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()

    async def test():
        agent = EnhancedAgent(
            signature="test-enhanced-agent",
            basemodel="openai/gpt-4",
            initial_cash=10000.0,
            max_steps=30,
            memory_lookback_days=5
        )

        await agent.initialize()
        await agent.run_trading_session("2025-10-15")

    # asyncio.run(test())
    print("EnhancedAgent class loaded successfully")

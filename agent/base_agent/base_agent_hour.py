"""
BaseAgent_Hour class - Trading agent for hour-level trading
Extends BaseAgent with hour-level specific functionality
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from dotenv import load_dotenv

# Import project tools
import sys
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tools.general_tools import extract_conversation, extract_tool_messages, get_config_value, write_config_value
from tools.price_tools import add_no_trade_record
from prompts.agent_prompt import get_agent_system_prompt, STOP_SIGNAL

# Load environment variables
load_dotenv()

from agent.base_agent.base_agent import BaseAgent

class BaseAgent_Hour(BaseAgent):
    """
    Trading agent for hour-level trading operations
    
    Inherits all functionality from BaseAgent and overrides specific methods
    to support hour-level trading logic:
    - get_trading_dates: Reads from merged.jsonl for hour-level timestamps
    - run_trading_session: Enhanced error handling for tool messages
    """
    
    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session with enhanced error handling
        
        Args:
            today_date: Trading date
        """
        print(f"📈 Starting trading session: {today_date}")
        
        # Set up logging
        log_file = self._setup_logging(today_date)
        write_config_value("LOG_FILE", log_file)
        
        # Update system prompt
        from langchain.agents import create_agent
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=get_agent_system_prompt(today_date, self.signature),
        )
        # If verbose, try to attach console callbacks to the agent itself
        if getattr(self, "verbose", False):
            try:
                from agent.base_agent.base_agent import _ConsoleHandler  # reuse resolved handler
                if _ConsoleHandler is not None:
                    handler = _ConsoleHandler()
                    self.agent = self.agent.with_config({
                        "callbacks": [handler],
                        "tags": [self.signature, today_date],
                        "run_name": f"{self.signature}-session"
                    })
                else:
                    print("⚠️ Verbose requested but no StdOut/Console callback handler found in current LangChain version.")
            except Exception:
                pass

        # Initial user query
        user_query = [{"role": "user", "content": f"Please analyze and update today's ({today_date}) positions."}]
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
                
                # Extract tool messages with None check
                tool_msgs = extract_tool_messages(response)
                tool_response = '\n'.join([msg.content for msg in tool_msgs if msg.content is not None])
                
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
        
        # Handle trading results
        await self._handle_trading_result(today_date)
    
    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """
        Get trading date list from merged.jsonl for hour-level data
        
        Args:
            init_date: Start date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            end_date: End date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            
        Returns:
            List of trading dates/times within the range
        """
        print()
        # Determine output format based on input format
        has_time1 = ' ' in init_date
        has_time2 = ' ' in end_date
        assert has_time1 == has_time2, "init_date and end_date must have the same time format"
        has_time = has_time1
        if has_time:
            init_dt = datetime.strptime(init_date, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        else:
            raise ValueError("Only support hour-level trading. Please use YYYY-MM-DD HH:MM:SS format.")
        
        # Get merged.jsonl path
        base_dir = Path(__file__).resolve().parents[2]
        merged_file = base_dir / "data" / "merged.jsonl"
        
        if not merged_file.exists():
            return []
        
        # Collect all timestamps from merged.jsonl
        all_timestamps = set()
        
        with merged_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    # 查找所有以 "Time Series" 开头的键
                    for key, value in doc.items():
                        if key.startswith("Time Series"):
                            if isinstance(value, dict):
                                all_timestamps.update(value.keys())
                            break
                except Exception:
                    continue
        
        if not all_timestamps:
            return []
        # Determine min_datetime based on init_date and last processed date in position file
        min_datetime = init_dt
        
        last_processed_dt = None
        if os.path.exists(self.position_file):
            max_date = None
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc['date']
                    if max_date is None:
                        max_date = current_date
                    else:
                        if ' ' in current_date:
                            current_date_obj = datetime.strptime(current_date, "%Y-%m-%d %H:%M:%S")
                        else:
                            current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
                        
                        if ' ' in max_date:
                            max_date_obj = datetime.strptime(max_date, "%Y-%m-%d %H:%M:%S")
                        else:
                            max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")
                        
                        if current_date_obj > max_date_obj:
                            max_date = current_date
            
            if max_date:
                if has_time:
                    last_processed_dt = datetime.strptime(max_date, "%Y-%m-%d %H:%M:%S")
                else:
                    last_processed_dt = datetime.strptime(max_date, "%Y-%m-%d")
            REGISTER = False
        else:
            # ensure agent registration if no position file yet
            self.register_agent()
            REGISTER = True
        # Take the larger lower bound between init_dt and last_processed_dt
        if last_processed_dt is not None:
            # If last processed has time, we will filter strictly greater than it;
            min_datetime = max(init_dt, last_processed_dt)
            if not has_time:
                last_processed_dt = last_processed_dt.date()
        
        # Filter timestamps within the range
        trading_times = []
        if not has_time:
            min_datetime = min_datetime.date()
            end_dt = end_dt.date()
    
        for ts_str in all_timestamps:
            try:
                if has_time:
                    ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                else:
                    ts_dt = datetime.strptime(ts_str, "%Y-%m-%d").date()
                # Check if timestamp is in range with boundary rules
                in_lower = False
                if last_processed_dt is None:
                    in_lower = ts_dt >= min_datetime
                else:
                    in_lower = ts_dt > min_datetime
                if in_lower and ts_dt <= end_dt:
                    trading_times.append(ts_str)
                    
            except Exception as e:
                print(f"❌ Error processing timestamp: {ts_str}")
                print(e)
                continue
        
        # Sort and remove duplicates
        trading_times = sorted(list(set(trading_times)))
        if REGISTER:
            print("REGISTER date will not be considered")
            trading_times = trading_times[1:]
        return trading_times

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

    def __str__(self) -> str:
        return f"BaseAgent_Hour(signature='{self.signature}', basemodel='{self.basemodel}', stocks={len(self.stock_symbols)})"
    
    def __repr__(self) -> str:
        return self.__str__()

"""
BaseAgentAStock_Hour class - A股小时级交易Agent
A-shares hourly trading agent

Inherits from BaseAgentAStock and overrides methods for hourly trading:
1. get_trading_dates: Reads from /data/A_stock/merged_hourly.jsonl
2. run_trading_session: Enhanced None check for tool messages
3. Supports hourly timestamps: YYYY-MM-DD HH:MM:SS

Key features:
- A-shares specific rules (T+1, 100-share lots, price limits)
- DeepSeek API compatibility
- Chinese prompts and queries
- Hourly trading times: 10:30, 11:30, 14:00, 15:00
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent

# Import project tools
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from agent.base_agent_astock.base_agent_astock import BaseAgentAStock
from prompts.agent_prompt_astock import STOP_SIGNAL, get_agent_system_prompt_astock
from tools.general_tools import (extract_conversation, extract_tool_messages,
                                 get_config_value, write_config_value)
from tools.price_tools import add_no_trade_record

# Load environment variables
load_dotenv()


class BaseAgentAStock_Hour(BaseAgentAStock):
    """
    A股小时级交易Agent
    Chinese A-shares hourly trading agent

    This class extends BaseAgentAStock to support hourly-level trading for Chinese A-shares market.
    It inherits all A-shares specific features including:
    - T+1 settlement rules (buy today, sell tomorrow)
    - 100-share lot trading requirements
    - Price limit restrictions (±10% for most stocks, ±20% for ST stocks)
    - DeepSeek API compatibility for Chinese LLM models
    - Chinese language prompts and responses

    Hourly Trading Features:
    - Data source: /data/A_stock/merged_hourly.jsonl
    - Trading hours: 10:30, 11:30, 14:00, 15:00 (4 time points per day)
    - Timestamp format: YYYY-MM-DD HH:MM:SS
    - Position file supports mixed daily/hourly timestamps

    Key Differences from BaseAgentAStock (daily):
    1. get_trading_dates: Reads hourly data from merged_hourly.jsonl instead of using is_trading_day
    2. run_trading_session: Enhanced error handling with None check for tool messages
    3. Default log path: ./data/agent_data_astock_hour (vs ./data/agent_data_astock)
    4. Default init_date: Hour-level timestamp (vs daily timestamp)

    Inherited Features (from BaseAgentAStock):
    - DeepSeekChatOpenAI wrapper for API compatibility
    - A-shares specific system prompts with trading rules
    - SSE 50 (上证50) stock symbols as default
    - CNY (¥) currency display
    - Market hardcoded to "cn"

    Example Usage:
        >>> agent = BaseAgentAStock_Hour(
        ...     signature="astock_hour_demo",
        ...     basemodel="deepseek-chat",
        ...     stock_symbols=None  # Defaults to SSE 50
        ... )
        >>> await agent.initialize()
        >>> await agent.run_date_range(
        ...     "2025-10-09 10:30:00",
        ...     "2025-10-10 15:00:00"
        ... )

    Note:
        - DeepSeek API support is automatically inherited from BaseAgentAStock.initialize()
        - RMB (¥) symbol display is automatically inherited from BaseAgentAStock.register_agent()
        - All MCP tools and trading logic are identical to daily A-shares trading
    """

    # A-shares hourly trading time points (Beijing time)
    ASTOCK_TRADING_HOURS = ["10:30:00", "11:30:00", "14:00:00", "15:00:00"]

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        log_path: Optional[str] = None,
        init_date: str = "2025-10-09 10:30:00",  # Hourly timestamp format
        **kwargs
    ):
        """
        Initialize BaseAgentAStock_Hour

        Args:
            signature: Agent signature/name
            basemodel: Base model name
            stock_symbols: List of stock symbols, defaults to SSE 50
            log_path: Log path, defaults to ./data/agent_data_astock_hour
            init_date: Initialization date with time (YYYY-MM-DD HH:MM:SS)
            **kwargs: Additional arguments passed to parent class
        """
        # Set default log path for hourly A-shares agent
        if log_path is None:
            log_path = "./data/agent_data_astock_hour"

        # Call parent class initialization (preserves all A-shares logic)
        super().__init__(
            signature=signature,
            basemodel=basemodel,
            stock_symbols=stock_symbols,
            log_path=log_path,
            init_date=init_date,
            **kwargs
        )

    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """
        Get trading date list from merged_hourly.jsonl for hourly data

        Args:
            init_date: Start date (YYYY-MM-DD HH:MM:SS)
            end_date: End date (YYYY-MM-DD HH:MM:SS)

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

        # Get merged_hourly.jsonl path (A-shares specific)
        base_dir = Path(__file__).resolve().parents[2]
        merged_file = base_dir / "data" / "A_stock" / "merged_hourly.jsonl"

        if not merged_file.exists():
            return []

        # Collect all timestamps from merged_hourly.jsonl
        all_timestamps = set()

        with merged_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    # Find all keys starting with "Time Series"
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
            # Only skip the very first timestamp if it exactly equals init_date to avoid double-processing
            if trading_times and trading_times[0] == init_date:
                print("REGISTER: init_date equals first timestamp; skipping first to avoid duplication")
                trading_times = trading_times[1:]
        return trading_times

    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session with enhanced error handling (A-shares hourly)

        Args:
            today_date: Trading date with time (YYYY-MM-DD HH:MM:SS)
        """
        print(f"📈 Starting A-shares hourly trading session: {today_date}")

        # Set up logging
        log_file = self._setup_logging(today_date)
        write_config_value("LOG_FILE", log_file)

        # Update system prompt - use A-shares specific prompt
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=get_agent_system_prompt_astock(today_date, self.signature, self.stock_symbols),
        )

        # Initial user query in Chinese
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

                # Extract tool messages with None check (enhanced error handling)
                tool_msgs = extract_tool_messages(response)
                tool_response = "\n".join([msg.content for msg in tool_msgs if msg.content is not None])

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

    def _is_valid_astock_trading_time(self, timestamp: str) -> bool:
        """
        Validate if timestamp is a valid A-shares trading time

        A-shares market trading hours (Beijing time):
        - Morning session: 09:30 - 11:30 (data points at 10:30, 11:30)
        - Afternoon session: 13:00 - 15:00 (data points at 14:00, 15:00)

        Args:
            timestamp: Timestamp string in format "YYYY-MM-DD HH:MM:SS"

        Returns:
            True if timestamp is within valid A-shares trading hours, False otherwise

        Example:
            >>> agent._is_valid_astock_trading_time("2025-10-09 10:30:00")
            True
            >>> agent._is_valid_astock_trading_time("2025-10-09 16:00:00")
            False
        """
        try:
            # Extract time component
            if " " not in timestamp:
                return False

            time_str = timestamp.split()[1]  # Get "HH:MM:SS"

            # Check if time is in the expected trading hour list
            if time_str in self.ASTOCK_TRADING_HOURS:
                return True

            # Alternative: Check time range (more flexible)
            hour, minute, second = map(int, time_str.split(":"))
            time_in_minutes = hour * 60 + minute

            # Morning session: 09:30 - 11:30 (570 - 690 minutes)
            morning_start = 9 * 60 + 30  # 570
            morning_end = 11 * 60 + 30  # 690

            # Afternoon session: 13:00 - 15:00 (780 - 900 minutes)
            afternoon_start = 13 * 60  # 780
            afternoon_end = 15 * 60  # 900

            return (morning_start <= time_in_minutes <= morning_end) or \
                   (afternoon_start <= time_in_minutes <= afternoon_end)

        except Exception as e:
            print(f"⚠️  Error validating trading time '{timestamp}': {e}")
            return False

    def _check_daily_completeness(self, trading_times: List[str], date: str) -> Dict[str, Any]:
        """
        Check if a trading day has all 4 expected time points

        A-shares hourly data should have exactly 4 time points per day:
        - 10:30:00 (morning mid-point)
        - 11:30:00 (morning close)
        - 14:00:00 (afternoon mid-point)
        - 15:00:00 (afternoon close)

        Args:
            trading_times: List of all trading timestamps
            date: Date to check (YYYY-MM-DD)

        Returns:
            Dictionary with completeness information:
            {
                "date": "2025-10-09",
                "expected": 4,
                "found": 3,
                "missing": ["14:00:00"],
                "is_complete": False
            }

        Example:
            >>> times = ["2025-10-09 10:30:00", "2025-10-09 11:30:00", "2025-10-09 15:00:00"]
            >>> agent._check_daily_completeness(times, "2025-10-09")
            {"date": "2025-10-09", "expected": 4, "found": 3, "missing": ["14:00:00"], "is_complete": False}
        """
        # Filter times for this specific date
        date_times = [t for t in trading_times if t.startswith(date)]

        # Extract hour:minute:second from timestamps
        found_times = set()
        for ts in date_times:
            if " " in ts:
                time_part = ts.split()[1]
                found_times.add(time_part)

        # Check against expected times
        expected_times = set(self.ASTOCK_TRADING_HOURS)
        missing_times = expected_times - found_times

        result = {
            "date": date,
            "expected": len(expected_times),
            "found": len(found_times),
            "found_times": sorted(list(found_times)),
            "missing": sorted(list(missing_times)),
            "is_complete": len(missing_times) == 0
        }

        # Print warning if incomplete
        if not result["is_complete"]:
            print(f"⚠️  警告: {date} 数据不完整")
            print(f"   预期时间点: {len(expected_times)} 个 {sorted(expected_times)}")
            print(f"   实际时间点: {len(found_times)} 个 {sorted(found_times)}")
            print(f"   缺失时间点: {sorted(missing_times)}")

        return result

    def validate_trading_times(self, trading_times: List[str], verbose: bool = True) -> Dict[str, Any]:
        """
        Validate and analyze a list of trading times

        This method performs comprehensive validation including:
        1. Checking if all timestamps are in valid A-shares trading hours
        2. Checking daily completeness (4 time points per day)
        3. Detecting duplicates
        4. Verifying timestamp format

        Args:
            trading_times: List of trading timestamps
            verbose: If True, print detailed validation results

        Returns:
            Dictionary with validation results:
            {
                "total_times": 8,
                "valid_times": 7,
                "invalid_times": 1,
                "invalid_list": ["2025-10-09 16:00:00"],
                "unique_dates": ["2025-10-09", "2025-10-10"],
                "daily_completeness": {...},
                "has_duplicates": False,
                "is_valid": True
            }

        Example:
            >>> times = ["2025-10-09 10:30:00", "2025-10-09 11:30:00", ...]
            >>> result = agent.validate_trading_times(times)
            >>> print(f"Valid: {result['is_valid']}")
        """
        # Count valid/invalid times
        valid_times = []
        invalid_times = []

        for ts in trading_times:
            if self._is_valid_astock_trading_time(ts):
                valid_times.append(ts)
            else:
                invalid_times.append(ts)

        # Extract unique dates
        unique_dates = set()
        for ts in valid_times:
            if " " in ts:
                date = ts.split()[0]
                unique_dates.add(date)

        # Check daily completeness for each date
        daily_checks = {}
        for date in sorted(unique_dates):
            daily_checks[date] = self._check_daily_completeness(trading_times, date)

        # Check for duplicates
        has_duplicates = len(trading_times) != len(set(trading_times))

        # Compile results
        result = {
            "total_times": len(trading_times),
            "valid_times": len(valid_times),
            "invalid_times": len(invalid_times),
            "invalid_list": invalid_times,
            "unique_dates": sorted(list(unique_dates)),
            "num_trading_days": len(unique_dates),
            "daily_completeness": daily_checks,
            "has_duplicates": has_duplicates,
            "is_valid": len(invalid_times) == 0 and not has_duplicates
        }

        # Print summary if verbose
        if verbose:
            print("=" * 60)
            print("交易时间验证结果")
            print("=" * 60)
            print(f"总时间点数: {result['total_times']}")
            print(f"有效时间点: {result['valid_times']}")
            print(f"无效时间点: {result['invalid_times']}")

            if result['invalid_times'] > 0:
                print(f"\n⚠️  无效时间点列表:")
                for ts in result['invalid_list']:
                    print(f"   - {ts}")

            print(f"\n交易日数: {result['num_trading_days']}")
            print(f"日期范围: {result['unique_dates'][0] if result['unique_dates'] else 'N/A'} 至 "
                  f"{result['unique_dates'][-1] if result['unique_dates'] else 'N/A'}")

            # Summary of daily completeness
            complete_days = sum(1 for check in daily_checks.values() if check['is_complete'])
            incomplete_days = len(daily_checks) - complete_days

            print(f"\n完整交易日: {complete_days}/{len(daily_checks)}")
            if incomplete_days > 0:
                print(f"不完整交易日: {incomplete_days}")

            if has_duplicates:
                print("\n⚠️  检测到重复时间点")

            print(f"\n总体验证: {'✅ 通过' if result['is_valid'] else '❌ 失败'}")
            print("=" * 60)

        return result

    def __str__(self) -> str:
        return (
            f"BaseAgentAStock_Hour(signature='{self.signature}', basemodel='{self.basemodel}', "
            f"market='cn', stocks={len(self.stock_symbols)})"
        )

    def __repr__(self) -> str:
        return self.__str__()

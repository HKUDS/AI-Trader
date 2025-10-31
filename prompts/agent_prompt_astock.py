"""
A股专用Agent提示词模块
Chinese A-shares specific agent prompt module
"""

import os

from dotenv import load_dotenv

load_dotenv()
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from tools.general_tools import get_config_value
from tools.price_tools import (all_sse_50_symbols,
                               format_price_dict_with_names, get_open_prices,
                               get_today_init_position, get_yesterday_date,
                               get_yesterday_open_and_close_price,
                               get_yesterday_profit)

STOP_SIGNAL = "<FINISH_SIGNAL>"

agent_system_prompt_astock = """
你是一位A股基本面分析交易助手。

你的目标是：
- 通过调用可用的工具进行思考和推理
- 你需要思考各个股票的价格和收益情况
- 你的长期目标是通过这个投资组合最大化收益
- 在做出决策之前，尽可能通过搜索工具收集信息以辅助决策

思考标准：
- 清晰展示关键的中间步骤：
  - 读取昨日持仓和今日价格的输入
  - 更新估值并调整每个目标的权重（如果策略需要）

注意事项：
- 你不需要在操作时请求用户许可，可以直接执行
- 你必须通过调用工具来执行操作，直接输出操作不会被接受

🇨🇳 重要 - A股交易规则（适用于所有 .SH 和 .SZ 股票代码）：
1. **一手交易要求**: 所有买卖订单必须是100股的整数倍（1手 = 100股）
   - ✅ 正确: buy("600519.SH", 100), buy("600519.SH", 300), sell("600519.SH", 200)
   - ❌ 错误: buy("600519.SH", 13), buy("600519.SH", 497), sell("600519.SH", 50)

2. **T+1结算规则**: 当天买入的股票不能当天卖出
   - 你只能卖出在今天之前购买的股票
   - 如果你今天买入100股600519.SH，必须等到明天才能卖出
   - 你仍然可以卖出之前持有的股票

3. **涨跌停限制**: 
   - 普通股票：±10%
   - ST股票：±5%
   - 科创板/创业板：±20%

以下是你需要的信息：

今日日期：
{date}

昨日收盘持仓（股票代码后的数字代表你持有的股数，CASH后的数字代表你的可用现金）：
{positions}

昨日收盘价格：
{yesterday_close_price}

今日买入价格：
{today_buy_price}

昨日收益情况：
{yesterday_profit}

当你认为任务完成时，输出
{STOP_SIGNAL}
"""


def get_agent_system_prompt_astock(today_date: str, signature: str, stock_symbols: Optional[List[str]] = None) -> str:
    """
    生成A股专用系统提示词

    Args:
        today_date: 今日日期
        signature: Agent签名
        stock_symbols: 股票代码列表，默认为上证50成分股

    Returns:
        格式化的系统提示词字符串
    """
    print(f"signature: {signature}")
    print(f"today_date: {today_date}")
    print(f"market: cn (A-shares)")

    # 默认使用上证50成分股
    if stock_symbols is None:
        stock_symbols = all_sse_50_symbols

    # 获取昨日买入和卖出价格，硬编码market="cn"
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(
        today_date, stock_symbols, market="cn"
    )
    today_buy_price = get_open_prices(today_date, stock_symbols, market="cn")
    today_init_position = get_today_init_position(today_date, signature)
    yesterday_profit = get_yesterday_profit(
        today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position, stock_symbols
    )

    # A股市场显示中文股票名称
    yesterday_sell_prices_display = format_price_dict_with_names(yesterday_sell_prices, market="cn")
    today_buy_price_display = format_price_dict_with_names(today_buy_price, market="cn")

    return agent_system_prompt_astock.format(
        date=today_date,
        positions=today_init_position,
        STOP_SIGNAL=STOP_SIGNAL,
        yesterday_close_price=yesterday_sell_prices_display,
        today_buy_price=today_buy_price_display,
        yesterday_profit=yesterday_profit,
    )


if __name__ == "__main__":
    today_date = get_config_value("TODAY_DATE")
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")
    print(get_agent_system_prompt_astock(today_date, signature))

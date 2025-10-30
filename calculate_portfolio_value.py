#!/usr/bin/env python3
"""
计算投资组合总市值的脚本

使用方法:
    python calculate_portfolio_value.py gpt-4.1 2025-10-29

参数:
    modelname: 模型名称 (如 gpt-4.1)
    date: 日期 (如 2025-10-29)，可选，默认为最新日期
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import get_open_prices, get_latest_position


def calculate_portfolio_value(
    modelname: str,
    date: Optional[str] = None,
    market: str = "cn"
) -> Dict:
    """
    计算投资组合的总市值
    
    Args:
        modelname: 模型名称
        date: 日期，如果为None则使用position文件中的最新日期
        market: 市场类型 ("us" 或 "cn")
    
    Returns:
        包含详细信息的字典
    """
    # Set up config
    write_config_value("LOG_PATH", f"./data/agent_data_astock" if market == "cn" else "./data/agent_data")
    
    # Get position file path
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]
    
    position_file = project_root / "data" / log_path / modelname / "position" / "position.jsonl"
    
    if not position_file.exists():
        print(f"❌ Position file not found: {position_file}")
        return {}
    
    # Get latest position
    if date is None:
        # Find the latest date in position file
        latest_date = None
        with position_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    record_date = doc.get("date")
                    if latest_date is None or (record_date and record_date > latest_date):
                        latest_date = record_date
                except Exception:
                    continue
        date = latest_date
    
    if not date:
        print("❌ No valid date found")
        return {}
    
    # Get position for the date
    positions, _ = get_latest_position(date, modelname)
    
    if not positions:
        print(f"❌ No position found for date: {date}")
        return {}
    
    # Extract cash and stock positions
    cash = positions.get("CASH", 0.0)
    stock_positions = {k: v for k, v in positions.items() if k != "CASH" and v > 0}
    
    if not stock_positions:
        print(f"\n📊 Portfolio Summary for {date}")
        print("=" * 60)
        print(f"💰 Cash: ¥{cash:,.2f}")
        print(f"📈 Total Portfolio Value: ¥{cash:,.2f}")
        print("\n✅ No stock holdings")
        return {
            "date": date,
            "cash": cash,
            "total_value": cash,
            "stock_values": {},
            "return_rate": (cash - 100000.0) / 100000.0 * 100
        }
    
    # Get prices for all stocks
    stock_symbols = list(stock_positions.keys())
    prices = get_open_prices(date, stock_symbols, market=market)
    
    # Calculate stock values
    stock_values = {}
    total_stock_value = 0.0
    
    for symbol, shares in stock_positions.items():
        price = prices.get(f"{symbol}_price")
        if price is not None:
            value = shares * price
            stock_values[symbol] = {
                "shares": shares,
                "price": price,
                "value": value
            }
            total_stock_value += value
        else:
            print(f"⚠️  Warning: No price found for {symbol} on {date}")
            stock_values[symbol] = {
                "shares": shares,
                "price": None,
                "value": 0.0
            }
    
    # Calculate total portfolio value
    total_value = cash + total_stock_value
    
    # Calculate return
    initial_cash = 100000.0
    return_value = total_value - initial_cash
    return_rate = return_value / initial_cash * 100
    
    # Print summary
    print(f"\n📊 Portfolio Summary for {date}")
    print("=" * 60)
    print(f"\n💰 Cash: ¥{cash:,.2f}")
    print(f"\n📈 Stock Holdings:")
    print("-" * 60)
    
    for symbol, info in sorted(stock_values.items(), key=lambda x: x[1]["value"], reverse=True):
        shares = info["shares"]
        price = info["price"]
        value = info["value"]
        if price is not None:
            weight = (value / total_value * 100) if total_value > 0 else 0
            print(f"  {symbol:12} | {shares:>6} shares × ¥{price:>8.2f} = ¥{value:>12,.2f} ({weight:>5.2f}%)")
        else:
            print(f"  {symbol:12} | {shares:>6} shares × (no price) = ¥{value:>12,.2f}")
    
    print("-" * 60)
    print(f"Stock Subtotal: ¥{total_stock_value:,.2f}")
    
    print("\n" + "=" * 60)
    print(f"📊 Total Portfolio Value: ¥{total_value:,.2f}")
    print(f"📈 Return: ¥{return_value:,.2f} ({return_rate:+.2f}%)")
    print("=" * 60)
    
    return {
        "date": date,
        "cash": cash,
        "stock_value": total_stock_value,
        "total_value": total_value,
        "stock_details": stock_values,
        "initial_cash": initial_cash,
        "return_value": return_value,
        "return_rate": return_rate
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python calculate_portfolio_value.py <modelname> [date] [market]")
        print("Example: python calculate_portfolio_value.py gpt-4.1")
        print("Example: python calculate_portfolio_value.py gpt-4.1 2025-10-29")
        print("Example: python calculate_portfolio_value.py gpt-4.1 2025-10-29 cn")
        sys.exit(1)
    
    modelname = sys.argv[1]
    date = sys.argv[2] if len(sys.argv) > 2 else None
    market = sys.argv[3] if len(sys.argv) > 3 else "cn"
    
    result = calculate_portfolio_value(modelname, date, market)


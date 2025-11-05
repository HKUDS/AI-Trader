#!/usr/bin/env python3
"""
分析回测结果
"""
import json
import sys
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools.price_tools import get_open_prices

def analyze_backtest(position_file):
    """分析回测结果"""
    # 读取所有交易记录
    trades = []
    with open(position_file, 'r') as f:
        for line in f:
            trades.append(json.loads(line))
    
    if not trades:
        print("❌ 没有找到交易记录")
        return
    
    # 获取初始和最终状态
    first_trade = trades[0]
    last_trade = trades[-1]
    
    # 计算初始现金
    initial_cash = 10000.0
    
    # 最终状态
    final_date = last_trade['date']
    final_cash = last_trade['positions']['CASH']
    final_positions = {k: v for k, v in last_trade['positions'].items() 
                      if k != 'CASH' and v > 0}
    
    # 获取最终日期的股票价格
    symbols_to_check = list(final_positions.keys())
    final_prices = {}
    
    # 从交易记录中提取每个股票的最后交易价格
    print(f"📍 使用最后交易价格估算持仓市值...")
    for trade in reversed(trades):
        action_info = trade.get('this_action', {})
        symbol = action_info.get('symbol')
        price = action_info.get('price', 0)
        if symbol and price > 0 and symbol in final_positions and symbol not in final_prices:
            final_prices[symbol] = price
    
    # 计算最终持仓市值
    final_stock_value = 0
    for symbol, amount in final_positions.items():
        if symbol in final_prices:
            final_stock_value += final_prices[symbol] * amount
    
    # 总资产 = 现金 + 股票市值
    total_value = final_cash + final_stock_value
    
    # 收益率
    total_return = total_value - initial_cash
    return_pct = (total_return / initial_cash) * 100
    
    # 统计买卖金额
    total_buy_value = 0
    total_sell_value = 0
    
    for trade in trades:
        action_info = trade.get('this_action', {})
        action = action_info.get('action')
        price = action_info.get('price', 0)
        amount = action_info.get('amount', 0)
        
        if action == 'buy':
            total_buy_value += price * amount
        elif action == 'sell':
            total_sell_value += price * amount
    
    print("=" * 60)
    print("📊 回测结果分析")
    print("=" * 60)
    print(f"\n📅 回测期间: {first_trade['date']} 到 {last_trade['date']}")
    print(f"📈 总交易次数: {len(trades)}")
    
    print(f"\n💰 资产统计:")
    print(f"  初始资金: ${initial_cash:,.2f}")
    print(f"  最终现金: ${final_cash:,.2f}")
    print(f"  最终持仓市值: ${final_stock_value:,.2f}")
    print(f"  最终总资产: ${total_value:,.2f}")
    print(f"\n📈 收益分析:")
    print(f"  绝对收益: ${total_return:,.2f}")
    print(f"  收益率: {return_pct:+.2f}%")
    print(f"\n💼 交易统计:")
    print(f"  总买入金额: ${total_buy_value:,.2f}")
    print(f"  总卖出金额: ${total_sell_value:,.2f}")
    
    print(f"\n📦 最终持仓({len(final_positions)}只股票):")
    for symbol, amount in sorted(final_positions.items()):
        price = final_prices.get(symbol, 0)
        value = price * amount
        print(f"  {symbol}: {amount:3d} 股 @ ${price:7.2f} = ${value:10,.2f}")
    
    # 交易统计
    buy_count = sum(1 for t in trades if t.get('this_action', {}).get('action') == 'buy')
    sell_count = sum(1 for t in trades if t.get('this_action', {}).get('action') == 'sell')
    
    print(f"\n� 交易次数统计:")
    print(f"  买入次数: {buy_count}")
    print(f"  卖出次数: {sell_count}")
    
    # 展示每天的交易
    print(f"\n📋 交易明细:")
    current_date = None
    for trade in trades:
        date = trade['date']
        action_info = trade.get('this_action', {})
        
        if date != current_date:
            print(f"\n  📅 {date}:")
            current_date = date
        
        action = action_info.get('action', 'N/A')
        symbol = action_info.get('symbol', 'N/A')
        amount = action_info.get('amount', 0)
        price = action_info.get('price', 0)
        total = price * amount
        
        action_emoji = "🟢" if action == "buy" else "🔴"
        print(f"    {action_emoji} {action.upper():4s} {amount:3d} x {symbol:6s} @ ${price:7.2f} = ${total:,.2f}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    position_file = sys.argv[1] if len(sys.argv) > 1 else "./data/agent_data/GLM-4.5-simple/position/position.jsonl"
    analyze_backtest(position_file)

#!/usr/bin/env python3
"""
回测结果分析 - 包含与纳斯达克100指数对比
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools.price_tools import get_open_prices
from datetime import datetime

def get_qqq_prices(date_list):
    """获取QQQ在指定日期的价格"""
    qqq_prices = {}
    try:
        with open('./data/daily_prices_QQQ.json', 'r') as f:
            data = json.load(f)
            time_series = data.get('Time Series (Daily)', {})
            
            for date in date_list:
                if date in time_series:
                    # 使用开盘价
                    qqq_prices[date] = float(time_series[date]['1. buy price'])
    except Exception as e:
        print(f"⚠️ 无法读取QQQ数据: {e}")
    
    return qqq_prices

def calculate_portfolio_value(trades, date, stock_prices):
    """计算指定日期的投资组合价值"""
    # 找到该日期之前的最后一条交易记录
    last_trade = None
    for trade in trades:
        if trade['date'] <= date:
            last_trade = trade
        else:
            break
    
    if not last_trade:
        return 10000.0  # 初始资金
    
    # 现金
    cash = last_trade['positions']['CASH']
    
    # 股票市值
    stock_value = 0
    for symbol, amount in last_trade['positions'].items():
        if symbol != 'CASH' and amount > 0:
            price = stock_prices.get(symbol, 0)
            stock_value += price * amount
    
    return cash + stock_value

def analyze_with_benchmark(position_file):
    """分析回测结果并与纳斯达克100指数对比"""
    # 读取所有交易记录
    trades = []
    with open(position_file, 'r') as f:
        for line in f:
            trades.append(json.loads(line))
    
    if not trades:
        print("❌ 没有找到交易记录")
        return
    
    # 获取回测日期范围
    trading_dates = sorted(set(t['date'] for t in trades if t['date'] != 'init'))
    start_date = trading_dates[0]
    end_date = trading_dates[-1]
    
    initial_cash = 10000.0
    
    print("=" * 70)
    print("📊 AI交易策略 vs 纳斯达克100指数对比分析")
    print("=" * 70)
    print(f"\n📅 回测期间: {start_date} 到 {end_date}")
    print(f"💰 初始资金: ${initial_cash:,.2f}")
    
    # 获取QQQ价格数据
    print("\n📈 获取纳斯达克100指数(QQQ)数据...")
    qqq_prices = get_qqq_prices(trading_dates)
    
    if not qqq_prices:
        print("❌ 无法获取QQQ数据,无法进行对比")
        return
    
    # 计算QQQ的买入持有策略
    qqq_start_price = qqq_prices.get(start_date, 0)
    qqq_end_price = qqq_prices.get(end_date, 0)
    
    if qqq_start_price == 0 or qqq_end_price == 0:
        print("❌ QQQ价格数据不完整")
        return
    
    # 买入持有QQQ的收益
    qqq_shares = initial_cash / qqq_start_price
    qqq_final_value = qqq_shares * qqq_end_price
    qqq_return = qqq_final_value - initial_cash
    qqq_return_pct = (qqq_return / initial_cash) * 100
    
    # 计算AI策略的最终价值
    last_trade = trades[-1]
    final_cash = last_trade['positions']['CASH']
    final_positions = {k: v for k, v in last_trade['positions'].items() 
                      if k != 'CASH' and v > 0}
    
    # 获取最后交易价格
    final_prices = {}
    for trade in reversed(trades):
        action_info = trade.get('this_action', {})
        symbol = action_info.get('symbol')
        price = action_info.get('price', 0)
        if symbol and price > 0 and symbol in final_positions and symbol not in final_prices:
            final_prices[symbol] = price
    
    # 计算持仓市值
    final_stock_value = sum(final_prices.get(s, 0) * a for s, a in final_positions.items())
    ai_final_value = final_cash + final_stock_value
    ai_return = ai_final_value - initial_cash
    ai_return_pct = (ai_return / initial_cash) * 100
    
    # 对比结果
    print("\n" + "=" * 70)
    print("📊 最终收益对比")
    print("=" * 70)
    
    print(f"\n💼 AI交易策略:")
    print(f"  最终资产: ${ai_final_value:,.2f}")
    print(f"  绝对收益: ${ai_return:,.2f}")
    print(f"  收益率:   {ai_return_pct:+.2f}%")
    
    print(f"\n📈 纳斯达克100 (QQQ买入持有):")
    print(f"  初始价格: ${qqq_start_price:.2f}")
    print(f"  最终价格: ${qqq_end_price:.2f}")
    print(f"  买入数量: {qqq_shares:.2f} 股")
    print(f"  最终资产: ${qqq_final_value:,.2f}")
    print(f"  绝对收益: ${qqq_return:,.2f}")
    print(f"  收益率:   {qqq_return_pct:+.2f}%")
    
    # 对比分析
    outperformance = ai_return_pct - qqq_return_pct
    print(f"\n🎯 相对表现:")
    if outperformance > 0:
        print(f"  ✅ AI策略跑赢指数 {outperformance:+.2f}个百分点")
    else:
        print(f"  ❌ AI策略跑输指数 {abs(outperformance):.2f}个百分点")
    
    # 计算每日收益曲线
    print(f"\n📉 计算逐日收益曲线...")
    
    # 为每个交易日计算投资组合价值
    ai_values = []
    qqq_values = []
    dates_for_plot = []
    
    for date in trading_dates:
        if date not in qqq_prices:
            continue
            
        # AI策略价值
        # 需要获取该日所有持仓股票的价格
        positions_on_date = None
        for trade in trades:
            if trade['date'] == date:
                positions_on_date = trade['positions']
                break
        
        if positions_on_date:
            # 从当天和之前的交易中获取价格
            date_prices = {}
            for trade in trades:
                if trade['date'] <= date:
                    action = trade.get('this_action', {})
                    symbol = action.get('symbol')
                    price = action.get('price', 0)
                    if symbol and price > 0:
                        date_prices[symbol] = price
            
            cash = positions_on_date['CASH']
            stock_value = sum(date_prices.get(s, 0) * a 
                            for s, a in positions_on_date.items() 
                            if s != 'CASH' and a > 0)
            ai_value = cash + stock_value
        else:
            ai_value = initial_cash
        
        # QQQ价值
        qqq_value = qqq_shares * qqq_prices[date]
        
        ai_values.append(ai_value)
        qqq_values.append(qqq_value)
        dates_for_plot.append(date)
    
    # 输出CSV格式便于绘图
    print(f"\n📊 逐日收益数据 (共{len(dates_for_plot)}个交易日):")
    print("=" * 70)
    print(f"{'日期':<12} {'AI策略($)':<15} {'QQQ($)':<15} {'AI收益率%':<12} {'QQQ收益率%':<12}")
    print("-" * 70)
    
    # 每隔一定天数显示一次,避免输出过长
    step = max(1, len(dates_for_plot) // 20)  # 最多显示20行
    for i in range(0, len(dates_for_plot), step):
        date = dates_for_plot[i]
        ai_val = ai_values[i]
        qqq_val = qqq_values[i]
        ai_ret = ((ai_val - initial_cash) / initial_cash) * 100
        qqq_ret = ((qqq_val - initial_cash) / initial_cash) * 100
        print(f"{date:<12} ${ai_val:>12,.2f} ${qqq_val:>12,.2f} {ai_ret:>10.2f}% {qqq_ret:>10.2f}%")
    
    # 最后一天
    if len(dates_for_plot) - 1 not in range(0, len(dates_for_plot), step):
        date = dates_for_plot[-1]
        ai_val = ai_values[-1]
        qqq_val = qqq_values[-1]
        ai_ret = ((ai_val - initial_cash) / initial_cash) * 100
        qqq_ret = ((qqq_val - initial_cash) / initial_cash) * 100
        print(f"{date:<12} ${ai_val:>12,.2f} ${qqq_val:>12,.2f} {ai_ret:>10.2f}% {qqq_ret:>10.2f}%")
    
    # 保存完整数据到CSV文件
    csv_filename = position_file.replace('position.jsonl', 'comparison.csv')
    try:
        with open(csv_filename, 'w') as f:
            f.write("date,ai_value,qqq_value,ai_return_pct,qqq_return_pct\n")
            for i, date in enumerate(dates_for_plot):
                ai_val = ai_values[i]
                qqq_val = qqq_values[i]
                ai_ret = ((ai_val - initial_cash) / initial_cash) * 100
                qqq_ret = ((qqq_val - initial_cash) / initial_cash) * 100
                f.write(f"{date},{ai_val:.2f},{qqq_val:.2f},{ai_ret:.2f},{qqq_ret:.2f}\n")
        print(f"\n💾 完整数据已保存到: {csv_filename}")
    except Exception as e:
        print(f"\n⚠️ 保存CSV失败: {e}")
    
    # 统计信息
    print("\n" + "=" * 70)
    print("📈 策略统计")
    print("=" * 70)
    
    # 交易统计
    buy_count = sum(1 for t in trades if t.get('this_action', {}).get('action') == 'buy')
    sell_count = sum(1 for t in trades if t.get('this_action', {}).get('action') == 'sell')
    
    print(f"\n🔄 交易统计:")
    print(f"  总交易次数: {len(trades)-1}")  # 减去init
    print(f"  买入次数:   {buy_count}")
    print(f"  卖出次数:   {sell_count}")
    print(f"  最终持仓:   {len(final_positions)} 只股票")
    print(f"  资金利用率: {(final_stock_value/(final_cash+final_stock_value))*100:.1f}%")
    
    # 计算最大回撤
    max_value = initial_cash
    max_drawdown = 0
    for val in ai_values:
        if val > max_value:
            max_value = val
        drawdown = (max_value - val) / max_value * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    print(f"\n📉 风险指标:")
    print(f"  最大回撤:   {max_drawdown:.2f}%")
    
    # QQQ最大回撤
    qqq_max_value = initial_cash
    qqq_max_drawdown = 0
    for val in qqq_values:
        if val > qqq_max_value:
            qqq_max_value = val
        drawdown = (qqq_max_value - val) / qqq_max_value * 100
        if drawdown > qqq_max_drawdown:
            qqq_max_drawdown = drawdown
    
    print(f"  QQQ最大回撤: {qqq_max_drawdown:.2f}%")
    
    # 夏普比率简化计算 (假设无风险利率为0)
    ai_returns = [(ai_values[i] - ai_values[i-1])/ai_values[i-1] for i in range(1, len(ai_values))]
    qqq_returns = [(qqq_values[i] - qqq_values[i-1])/qqq_values[i-1] for i in range(1, len(qqq_values))]
    
    if ai_returns:
        ai_avg_return = sum(ai_returns) / len(ai_returns)
        ai_std = (sum((r - ai_avg_return)**2 for r in ai_returns) / len(ai_returns)) ** 0.5
        ai_sharpe = (ai_avg_return / ai_std) if ai_std > 0 else 0
        
        qqq_avg_return = sum(qqq_returns) / len(qqq_returns)
        qqq_std = (sum((r - qqq_avg_return)**2 for r in qqq_returns) / len(qqq_returns)) ** 0.5
        qqq_sharpe = (qqq_avg_return / qqq_std) if qqq_std > 0 else 0
        
        print(f"\n📊 收益风险比 (简化夏普比率):")
        print(f"  AI策略:   {ai_sharpe:.3f}")
        print(f"  QQQ指数:  {qqq_sharpe:.3f}")
    
    print("\n" + "=" * 70)
    print("✅ 分析完成!")
    print("=" * 70)

if __name__ == "__main__":
    position_file = sys.argv[1] if len(sys.argv) > 1 else "./data/agent_data/GLM-4.5-simple/position/position.jsonl"
    analyze_with_benchmark(position_file)

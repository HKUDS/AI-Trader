#!/usr/bin/env python3
"""
绘制AI策略 vs 纳斯达克100收益对比图
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import sys

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def plot_comparison(csv_file):
    """绘制收益对比图"""
    # 读取数据
    df = pd.read_csv(csv_file)
    df['date'] = pd.to_datetime(df['date'])
    
    # 计算收益率
    initial_cash = 10000.0
    df['ai_return_pct'] = (df['ai_value'] - initial_cash) / initial_cash * 100
    df['qqq_return_pct'] = (df['qqq_value'] - initial_cash) / initial_cash * 100
    
    # 创建图表
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    
    # 第一个子图: 资产价值对比
    ax1 = axes[0]
    ax1.plot(df['date'], df['ai_value'], label='AI Trading Strategy', 
             linewidth=2, color='#2E86DE', marker='o', markersize=3)
    ax1.plot(df['date'], df['qqq_value'], label='NASDAQ-100 (QQQ)', 
             linewidth=2, color='#EE5A6F', marker='s', markersize=3)
    ax1.axhline(y=initial_cash, color='gray', linestyle='--', alpha=0.5, label='Initial Capital')
    
    ax1.set_xlabel('Date', fontsize=12)
    ax1.set_ylabel('Portfolio Value ($)', fontsize=12)
    ax1.set_title('AI Trading Strategy vs NASDAQ-100 Index - Portfolio Value', 
                  fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 添加最终值标注
    final_ai = df['ai_value'].iloc[-1]
    final_qqq = df['qqq_value'].iloc[-1]
    ax1.annotate(f'${final_ai:,.0f}', 
                xy=(df['date'].iloc[-1], final_ai),
                xytext=(10, 10), textcoords='offset points',
                fontsize=10, color='#2E86DE', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    ax1.annotate(f'${final_qqq:,.0f}', 
                xy=(df['date'].iloc[-1], final_qqq),
                xytext=(10, -20), textcoords='offset points',
                fontsize=10, color='#EE5A6F', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    # 第二个子图: 收益率对比
    ax2 = axes[1]
    ax2.plot(df['date'], df['ai_return_pct'], label='AI Trading Strategy', 
             linewidth=2, color='#2E86DE', marker='o', markersize=3)
    ax2.plot(df['date'], df['qqq_return_pct'], label='NASDAQ-100 (QQQ)', 
             linewidth=2, color='#EE5A6F', marker='s', markersize=3)
    ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax2.fill_between(df['date'], df['ai_return_pct'], df['qqq_return_pct'],
                     where=(df['ai_return_pct'] >= df['qqq_return_pct']),
                     alpha=0.2, color='green', label='Outperformance')
    ax2.fill_between(df['date'], df['ai_return_pct'], df['qqq_return_pct'],
                     where=(df['ai_return_pct'] < df['qqq_return_pct']),
                     alpha=0.2, color='red', label='Underperformance')
    
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Return (%)', fontsize=12)
    ax2.set_title('Cumulative Return Comparison', fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 添加最终收益率标注
    final_ai_ret = df['ai_return_pct'].iloc[-1]
    final_qqq_ret = df['qqq_return_pct'].iloc[-1]
    ax2.annotate(f'{final_ai_ret:+.2f}%', 
                xy=(df['date'].iloc[-1], final_ai_ret),
                xytext=(10, 10), textcoords='offset points',
                fontsize=10, color='#2E86DE', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    ax2.annotate(f'{final_qqq_ret:+.2f}%', 
                xy=(df['date'].iloc[-1], final_qqq_ret),
                xytext=(10, -20), textcoords='offset points',
                fontsize=10, color='#EE5A6F', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    
    # 保存图表
    output_file = csv_file.replace('.csv', '_chart.png')
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"📊 图表已保存到: {output_file}")
    
    # 显示图表
    plt.show()

if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "./data/agent_data/GLM-4.5-simple/position/comparison.csv"
    
    try:
        plot_comparison(csv_file)
    except ImportError as e:
        print(f"❌ 缺少依赖包: {e}")
        print("请安装: pip install pandas matplotlib")
    except Exception as e:
        print(f"❌ 绘图失败: {e}")

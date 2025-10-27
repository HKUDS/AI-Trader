#!/usr/bin/env python3
"""
信号检测器演示程序
不依赖真实数据，使用模拟数据展示功能
"""

import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from signal_detector.signal_engine import SignalEngine


def demo_basic_detection():
    """基础检测演示"""
    print("\n" + "="*70)
    print("🎯 演示1: 基础风险/机会检测")
    print("="*70)

    # 创建引擎
    engine = SignalEngine()

    # 场景1: 市场暴跌 + NVDA权重过高
    print("\n📊 场景1: 市场暴跌 + 持仓集中风险")
    print("-" * 70)

    market_data = {
        'market_change': -0.036,  # -3.6%
        'vix': 28.5,
        'current_prices': {
            'NVDA': 180.50,
            'MSFT': 420.00,
            'AMD': 115.00,
            'ASML': 1020.00
        },
        'previous_prices': {
            'NVDA': 189.00,
            'MSFT': 425.00,
            'AMD': 122.50,
            'ASML': 1030.00
        }
    }

    portfolio = {
        'positions': {
            'NVDA': 60,   # 权重26%
            'MSFT': 10,   # 权重10%
            'AMD': 15     # 权重4%
        },
        'cash': 200.0,
        'total_value': 14200.0
    }

    signals = engine.generate_daily_signals(
        market_data,
        portfolio,
        theme_stocks=['NVDA', 'AMD', 'ASML']
    )

    print_signals(signals)


def demo_opportunity_detection():
    """机会检测演示"""
    print("\n" + "="*70)
    print("🎯 演示2: 超跌机会识别")
    print("="*70)

    engine = SignalEngine()

    # 场景2: 主题股超跌
    print("\n📊 场景2: AI芯片股超跌，抄底机会")
    print("-" * 70)

    market_data = {
        'market_change': -0.015,  # -1.5%
        'vix': 22.0,
        'current_prices': {
            'NVDA': 182.23,   # 下跌5.8%
            'AMD': 118.50,    # 下跌3.2%
            'MSFT': 422.00,   # 微跌
            'ASML': 1000.00   # 下跌2.9%
        },
        'previous_prices': {
            'NVDA': 193.50,
            'AMD': 122.50,
            'MSFT': 425.00,
            'ASML': 1030.00
        }
    }

    portfolio = {
        'positions': {
            'NVDA': 5,    # 权重低
            'MSFT': 10,
            'AMD': 0      # 没有持仓
        },
        'cash': 5000.0,
        'total_value': 11000.0
    }

    signals = engine.generate_daily_signals(
        market_data,
        portfolio,
        theme_stocks=['NVDA', 'AMD', 'ASML']
    )

    print_signals(signals)


def demo_deepseek_oct10():
    """DeepSeek 2025-10-10 实战场景复现"""
    print("\n" + "="*70)
    print("🎯 演示3: DeepSeek 2025-10-10 贸易战日复现")
    print("="*70)

    engine = SignalEngine()

    print("\n📰 背景: Trump威胁对华征收'massive'关税")
    print("📉 市场: 纳斯达克暴跌 -3.6%，科技股大量抛售")
    print("-" * 70)

    market_data = {
        'market_change': -0.036,
        'vix': 28.5,
        'current_prices': {
            'NVDA': 193.50,
            'MSFT': 519.64,
            'AMD': 214.85,
            'AAPL': 254.94,
            'GOOGL': 241.43,
            'AVGO': 345.39,
            'ASML': 970.69
        },
        'previous_prices': {
            'NVDA': 200.80,
            'MSFT': 535.00,
            'AMD': 225.00,
            'AAPL': 262.00,
            'GOOGL': 248.00,
            'AVGO': 358.00,
            'ASML': 1000.00
        }
    }

    # DeepSeek当时的持仓
    portfolio = {
        'positions': {
            'NVDA': 8,
            'MSFT': 4,
            'AMD': 8,
            'AAPL': 3,
            'GOOGL': 2,
            'AVGO': 4,
            'ASML': 2
        },
        'cash': 632.0,
        'total_value': 10668.0
    }

    signals = engine.generate_daily_signals(
        market_data,
        portfolio,
        theme_stocks=['NVDA', 'AMD', 'ASML', 'AVGO']
    )

    print_signals(signals)

    print("\n💡 DeepSeek实际操作:")
    print("   ✅ 卖出NVDA 5股（减仓62.5%）")
    print("   ✅ 卖出AMD、ASML大部分仓位")
    print("   ✅ 买入PEP（防御）、AEP（公用事业）")
    print("   ✅ 现金比例提至17.3%")
    print("\n📊 结果: 成功避免进一步下跌")


def demo_deepseek_oct16():
    """DeepSeek 2025-10-16 抄底场景复现"""
    print("\n" + "="*70)
    print("🎯 演示4: DeepSeek 2025-10-16 恐慌后抄底")
    print("="*70)

    engine = SignalEngine()

    print("\n📰 背景: 中美贸易紧张缓和，市场反弹")
    print("📈 市场: 道指反弹 +0.52%")
    print("-" * 70)

    market_data = {
        'market_change': 0.005,  # +0.5%
        'vix': 22.0,
        'current_prices': {
            'NVDA': 182.23,   # 比之前卖出价便宜
            'MSFT': 520.56,
            'AMD': 218.00,
            'ASML': 1019.09
        },
        'previous_prices': {
            'NVDA': 193.50,   # 之前的卖出价
            'MSFT': 519.64,
            'AMD': 214.85,
            'ASML': 970.69
        }
    }

    # DeepSeek减仓后的持仓
    portfolio = {
        'positions': {
            'NVDA': 5,    # 已大幅减仓
            'MSFT': 4,
            'AMD': 3,
            'ASML': 2
        },
        'cash': 1905.0,  # 现金充足
        'total_value': 10853.0
    }

    signals = engine.generate_daily_signals(
        market_data,
        portfolio,
        theme_stocks=['NVDA', 'AMD', 'ASML']
    )

    print_signals(signals)

    print("\n💡 DeepSeek实际操作:")
    print("   ✅ 买入NVDA 2股 @ $182.23")
    print("   ✅ 买入AMD加仓")
    print("\n📊 收益: 赚取$11.27/股价差（5.8%）")
    print("   卖出价: $193.50")
    print("   买入价: $182.23")


def print_signals(signals: dict):
    """打印信号"""
    summary = signals['summary']
    risk_signals = signals['risk_signals']
    opportunity_signals = signals['opportunity_signals']

    # 概览
    print(f"\n📊 概览:")
    print(f"   总资产: ${summary['portfolio_value']:,.2f}")
    print(f"   现金比例: {summary['cash_ratio']*100:.2f}%")
    print(f"   风险数量: {summary['total_risks']}项 (极高:{summary['critical_risks']}, 高:{summary['high_risks']})")
    print(f"   机会数量: {summary['total_opportunities']}个 (高置信度:{summary['high_confidence_opportunities']})")

    # 风险警告
    if risk_signals:
        print(f"\n⚠️  风险警告:")
        for i, risk in enumerate(risk_signals[:3], 1):
            level_emoji = {
                '极高': '🔴',
                '高': '🟠',
                '中等': '🟡',
                '低': '🟢'
            }.get(risk['level'], '⚪')

            print(f"\n   {i}. {level_emoji} {risk['signal_type']} [{risk['level']}风险]")
            print(f"      描述: {risk['description']}")
            print(f"      建议: {risk['action']}")
            print(f"      评分: {risk['score']}/100")

    # 买入机会
    if opportunity_signals:
        print(f"\n💡 买入机会:")
        for i, opp in enumerate(opportunity_signals[:3], 1):
            confidence_emoji = {
                '极高': '🔥',
                '高': '⭐',
                '中等': '💫',
                '低': '✨'
            }.get(opp['confidence'], '⚪')

            print(f"\n   {i}. {confidence_emoji} {opp['symbol']} - {opp['opportunity_type']} [{opp['confidence']}置信度]")
            print(f"      价格: ${opp['price']:.2f} ({opp['price_change']*100:+.2f}%)")
            print(f"      建议: {opp['action']}")
            print(f"      原因: {opp['reason']}")
            print(f"      评分: {opp['score']}/100")


def main():
    """主程序"""
    print("\n" + "="*70)
    print("🎯 风险/机会信号检测器 - 功能演示")
    print("="*70)
    print("\n本演示展示信号检测器的核心功能，基于DeepSeek的实战案例")

    # 演示1: 基础检测
    demo_basic_detection()

    # 演示2: 机会检测
    demo_opportunity_detection()

    # 演示3: DeepSeek 贸易战日
    demo_deepseek_oct10()

    # 演示4: DeepSeek 抄底日
    demo_deepseek_oct16()

    print("\n" + "="*70)
    print("✅ 演示完成！")
    print("="*70)
    print("\n💡 使用建议:")
    print("   1. 将此工具集成到每日交易流程")
    print("   2. 关注🔴极高风险和🔥高置信度机会")
    print("   3. 结合自己的判断，不要盲目跟随信号")
    print("\n📚 完整文档: signal_detector/README.md")
    print("🚀 独立运行: python signal_detector/detector_runner.py --help")
    print()


if __name__ == "__main__":
    main()

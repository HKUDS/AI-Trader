#!/usr/bin/env python3
"""
独立运行的风险/机会信号检测器

使用方法:
    python detector_runner.py --date 2025-10-24
    python detector_runner.py --date 2025-10-24 --model deepseek-chat-v3.1
    python detector_runner.py --live  # 实时监控模式

功能：
1. 分析指定日期的市场风险
2. 识别买入/卖出机会
3. 生成可视化报告
4. 实时监控模式
"""

import os
import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from signal_detector.signal_engine import SignalEngine, SignalLevel
from tools.price_tools import (
    get_open_prices,
    get_yesterday_open_and_close_price,
    get_today_init_position
)


class SignalDetectorRunner:
    """信号检测器运行器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化运行器

        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.engine = SignalEngine(self.config)

        # NASDAQ 100 股票列表
        self.all_symbols = [
            "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
            "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
            "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
            "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
            "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
            "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
            "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
            "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
            "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
            "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
            "ON", "BIIB", "LULU", "CDW", "GFS"
        ]

        # 主题股票
        self.theme_stocks = {
            'ai_semiconductor': ["NVDA", "AMD", "MSFT", "GOOGL", "ASML", "AVGO", "QCOM", "AMAT", "ARM", "INTC", "MU"],
            'tech_giants': ["MSFT", "AAPL", "GOOGL", "AMZN", "META"],
            'cloud': ["MSFT", "AMZN", "GOOGL"]
        }

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """加载配置"""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        return None

    def get_market_data(self, date: str) -> Dict:
        """
        获取市场数据

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            {
                'market_change': float,
                'vix': float,
                'current_prices': {symbol: price},
                'previous_prices': {symbol: price}
            }
        """
        # 获取今日和昨日价格
        current_prices_dict = get_open_prices(date, self.all_symbols)
        prev_buy, prev_sell = get_yesterday_open_and_close_price(date, self.all_symbols)

        # 转换价格格式
        current_prices = {}
        previous_prices = {}

        for symbol in self.all_symbols:
            price_key = f'{symbol}_price'
            if price_key in current_prices_dict:
                current_prices[symbol] = current_prices_dict[price_key]
            if price_key in prev_sell:
                previous_prices[symbol] = prev_sell[price_key]

        # 计算市场整体变化（简化：使用QQQ代表或平均值）
        market_change = 0
        if current_prices and previous_prices:
            changes = []
            for symbol in ['NVDA', 'MSFT', 'AAPL', 'GOOGL', 'AMZN']:  # 大盘股代表
                if symbol in current_prices and symbol in previous_prices:
                    curr = current_prices[symbol]
                    prev = previous_prices[symbol]
                    if prev > 0:
                        changes.append((curr - prev) / prev)

            if changes:
                market_change = sum(changes) / len(changes)

        return {
            'market_change': market_change,
            'vix': abs(market_change) * 100 + 15,  # 简化计算VIX
            'current_prices': current_prices,
            'previous_prices': previous_prices
        }

    def get_portfolio_data(self, date: str, model_name: str = None) -> Dict:
        """
        获取组合数据

        Args:
            date: 日期
            model_name: 模型名称（如果为空则创建空组合）

        Returns:
            {
                'positions': {symbol: shares},
                'cash': float,
                'total_value': float
            }
        """
        if model_name:
            # 从文件读取实际持仓
            positions = get_today_init_position(date, model_name)
            cash = positions.get('CASH', 0)

            # 计算总价值
            current_prices = get_open_prices(date, self.all_symbols)
            total_value = cash

            positions_dict = {}
            for symbol in self.all_symbols:
                shares = positions.get(symbol, 0)
                if shares > 0:
                    price_key = f'{symbol}_price'
                    price = current_prices.get(price_key, 0)
                    total_value += shares * price
                    positions_dict[symbol] = shares

            return {
                'positions': positions_dict,
                'cash': cash,
                'total_value': total_value
            }
        else:
            # 创建空组合
            return {
                'positions': {},
                'cash': 10000.0,
                'total_value': 10000.0
            }

    def analyze(
        self,
        date: str,
        model_name: Optional[str] = None,
        theme: str = 'ai_semiconductor'
    ) -> Dict:
        """
        执行信号分析

        Args:
            date: 分析日期
            model_name: 模型名称（可选）
            theme: 主题类型

        Returns:
            完整的信号报告
        """
        print(f"\n{'='*70}")
        print(f"🔍 信号检测分析 - {date}")
        print(f"{'='*70}\n")

        # 1. 获取市场数据
        print("📊 正在获取市场数据...")
        market_data = self.get_market_data(date)
        print(f"   市场变化: {market_data['market_change']*100:+.2f}%")
        print(f"   波动率VIX: {market_data['vix']:.1f}")

        # 2. 获取组合数据
        print("\n💼 正在获取组合数据...")
        portfolio = self.get_portfolio_data(date, model_name)
        print(f"   总资产: ${portfolio['total_value']:,.2f}")
        print(f"   现金: ${portfolio['cash']:,.2f} ({portfolio['cash']/portfolio['total_value']*100:.1f}%)")
        print(f"   持仓数量: {len([p for p in portfolio['positions'].values() if p > 0])}只")

        # 3. 生成信号
        print("\n🎯 正在分析信号...")
        theme_stocks_list = self.theme_stocks.get(theme, [])
        signals = self.engine.generate_daily_signals(
            market_data,
            portfolio,
            theme_stocks=theme_stocks_list
        )

        return signals

    def print_report(self, signals: Dict):
        """
        打印信号报告

        Args:
            signals: 信号数据
        """
        print("\n" + "="*70)
        print("📋 信号检测报告")
        print("="*70)

        summary = signals['summary']
        risk_signals = signals['risk_signals']
        opportunity_signals = signals['opportunity_signals']

        # 1. 概览
        print(f"\n📊 概览:")
        print(f"   时间: {summary['timestamp']}")
        print(f"   总资产: ${summary['portfolio_value']:,.2f}")
        print(f"   现金比例: {summary['cash_ratio']*100:.2f}%")

        # 2. 风险警告
        print(f"\n⚠️  风险警告 ({summary['total_risks']}项):")

        if summary['critical_risks'] > 0:
            print(f"   🔴 极高风险: {summary['critical_risks']}项")
        if summary['high_risks'] > 0:
            print(f"   🟠 高风险: {summary['high_risks']}项")

        if risk_signals:
            # 按优先级排序
            sorted_risks = sorted(
                risk_signals,
                key=lambda x: {'极高': 4, '高': 3, '中等': 2, '低': 1}.get(x['level'], 0),
                reverse=True
            )

            for i, risk in enumerate(sorted_risks[:5], 1):  # 只显示前5个
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
        else:
            print("   ✅ 暂无明显风险")

        # 3. 买入机会
        print(f"\n💡 买入机会 ({summary['total_opportunities']}个):")

        if summary['high_confidence_opportunities'] > 0:
            print(f"   🔥 高置信度机会: {summary['high_confidence_opportunities']}个")

        if opportunity_signals:
            # 按评分排序
            sorted_opps = sorted(
                opportunity_signals,
                key=lambda x: x['score'],
                reverse=True
            )

            for i, opp in enumerate(sorted_opps[:5], 1):  # 只显示前5个
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
        else:
            print("   暂无明显机会")

        print("\n" + "="*70)

    def save_report(self, signals: Dict, output_path: str):
        """
        保存报告到文件

        Args:
            signals: 信号数据
            output_path: 输出路径
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 保存JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)

        print(f"\n✅ 报告已保存至: {output_path}")


def main():
    """主程序"""
    parser = argparse.ArgumentParser(
        description='独立风险/机会信号检测器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析指定日期
  python detector_runner.py --date 2025-10-24

  # 分析指定模型的持仓
  python detector_runner.py --date 2025-10-24 --model deepseek-chat-v3.1

  # 指定主题
  python detector_runner.py --date 2025-10-24 --theme tech_giants

  # 保存报告
  python detector_runner.py --date 2025-10-24 --output report.json
        """
    )

    parser.add_argument(
        '--date',
        type=str,
        default=datetime.now().strftime('%Y-%m-%d'),
        help='分析日期 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='模型名称 (如: deepseek-chat-v3.1)'
    )

    parser.add_argument(
        '--theme',
        type=str,
        default='ai_semiconductor',
        choices=['ai_semiconductor', 'tech_giants', 'cloud'],
        help='投资主题'
    )

    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='输出报告路径'
    )

    args = parser.parse_args()

    # 创建运行器
    runner = SignalDetectorRunner(args.config)

    try:
        # 执行分析
        signals = runner.analyze(
            date=args.date,
            model_name=args.model,
            theme=args.theme
        )

        # 打印报告
        runner.print_report(signals)

        # 保存报告
        if args.output:
            runner.save_report(signals, args.output)
        else:
            # 默认保存位置
            default_output = f"signal_detector/reports/signal_report_{args.date}.json"
            runner.save_report(signals, default_output)

    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

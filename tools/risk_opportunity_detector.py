"""
风险/机会检测工具
基于DeepSeek成功策略的实战信号检测系统
"""

import os
import sys
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.price_tools import get_open_prices, get_yesterday_open_and_close_price


class RiskOpportunityDetector:
    """
    风险/机会检测器

    基于DeepSeek的成功经验，提供：
    1. 宏观风险评估
    2. 个股风险检测
    3. 买入机会识别
    4. 权重再平衡建议
    """

    def __init__(
        self,
        max_single_weight: float = 0.20,
        min_cash_ratio: float = 0.01,
        max_cash_ratio: float = 0.03
    ):
        """
        初始化检测器

        Args:
            max_single_weight: 单股最大权重（默认20%）
            min_cash_ratio: 最小现金比例（默认1%）
            max_cash_ratio: 最大现金比例（默认3%）
        """
        self.max_single_weight = max_single_weight
        self.min_cash_ratio = min_cash_ratio
        self.max_cash_ratio = max_cash_ratio

    def calculate_portfolio_weights(
        self,
        positions: Dict[str, float],
        prices: Dict[str, float]
    ) -> Dict[str, Dict]:
        """
        计算组合权重

        Args:
            positions: 持仓数量 {symbol: shares}
            prices: 当前价格 {symbol: price}

        Returns:
            {
                'total_value': 总资产,
                'cash_ratio': 现金比例,
                'weights': {symbol: {'shares': x, 'value': y, 'weight': z}}
            }
        """
        # 计算各股票价值
        stock_values = {}
        for symbol, shares in positions.items():
            if symbol == 'CASH':
                continue

            price = prices.get(f'{symbol}_price', 0)
            if price > 0 and shares > 0:
                stock_values[symbol] = {
                    'shares': shares,
                    'price': price,
                    'value': shares * price
                }

        # 计算总资产
        cash = positions.get('CASH', 0)
        total_stock_value = sum(info['value'] for info in stock_values.values())
        total_value = total_stock_value + cash

        # 计算权重
        weights = {}
        for symbol, info in stock_values.items():
            weights[symbol] = {
                **info,
                'weight': info['value'] / total_value if total_value > 0 else 0
            }

        return {
            'total_value': total_value,
            'cash': cash,
            'cash_ratio': cash / total_value if total_value > 0 else 0,
            'weights': weights
        }

    def check_position_risks(
        self,
        portfolio_analysis: Dict
    ) -> List[Dict]:
        """
        检查个股风险

        Returns:
            [
                {
                    'symbol': 'NVDA',
                    'risk_type': 'OVERWEIGHT',
                    'current_weight': 0.25,
                    'target_weight': 0.18,
                    'action': '卖出超额部分',
                    'suggest_sell_shares': 5
                }
            ]
        """
        risks = []
        weights = portfolio_analysis['weights']
        total_value = portfolio_analysis['total_value']

        for symbol, info in weights.items():
            weight = info['weight']
            shares = info['shares']
            price = info['price']

            # 风险1：权重过高
            if weight > self.max_single_weight:
                target_weight = self.max_single_weight * 0.9  # 目标降至18%
                target_value = total_value * target_weight
                current_value = info['value']
                excess_value = current_value - target_value
                suggest_sell = int(excess_value / price)

                risks.append({
                    'symbol': symbol,
                    'risk_type': 'OVERWEIGHT',
                    'severity': 'HIGH',
                    'current_weight': round(weight, 4),
                    'target_weight': round(target_weight, 4),
                    'action': f'卖出{suggest_sell}股，降低权重至{target_weight*100:.1f}%',
                    'suggest_sell_shares': suggest_sell,
                    'reason': f'当前权重{weight*100:.1f}%超过{self.max_single_weight*100:.0f}%上限'
                })

            # 风险2：权重过低但是主题股
            elif weight < 0.05 and weight > 0:
                risks.append({
                    'symbol': symbol,
                    'risk_type': 'UNDERWEIGHT',
                    'severity': 'LOW',
                    'current_weight': round(weight, 4),
                    'action': f'考虑加仓至10-15%',
                    'reason': f'主题股权重仅{weight*100:.1f}%，配置过低'
                })

        return risks

    def check_cash_risks(
        self,
        portfolio_analysis: Dict
    ) -> Optional[Dict]:
        """
        检查现金管理风险

        Returns:
            {
                'risk_type': 'EXCESSIVE_CASH' | 'INSUFFICIENT_CASH',
                'current_ratio': 0.05,
                'action': '买入优质标的',
                'reason': '...'
            }
        """
        cash_ratio = portfolio_analysis['cash_ratio']

        if cash_ratio > self.max_cash_ratio:
            return {
                'risk_type': 'EXCESSIVE_CASH',
                'severity': 'MEDIUM',
                'current_ratio': round(cash_ratio, 4),
                'target_ratio': self.max_cash_ratio,
                'action': '寻找买入机会，部署闲置现金',
                'reason': f'现金比例{cash_ratio*100:.1f}%过高，降低资金利用效率'
            }
        elif cash_ratio < self.min_cash_ratio:
            return {
                'risk_type': 'INSUFFICIENT_CASH',
                'severity': 'MEDIUM',
                'current_ratio': round(cash_ratio, 4),
                'target_ratio': self.min_cash_ratio,
                'action': '卖出部分持仓，增加现金储备',
                'reason': f'现金比例仅{cash_ratio*100:.1f}%，缺乏调仓灵活性'
            }

        return None

    def identify_buying_opportunities(
        self,
        today_prices: Dict[str, float],
        yesterday_prices: Dict[str, float],
        theme_stocks: List[str],
        portfolio_analysis: Dict
    ) -> List[Dict]:
        """
        识别买入机会

        Args:
            today_prices: 今日价格
            yesterday_prices: 昨日价格
            theme_stocks: 主题股票列表
            portfolio_analysis: 组合分析

        Returns:
            [
                {
                    'symbol': 'NVDA',
                    'opportunity_type': 'PULLBACK',
                    'confidence': 'HIGH',
                    'price_change': -0.035,
                    'action': '逢低买入',
                    'reason': '...'
                }
            ]
        """
        opportunities = []
        current_weights = portfolio_analysis['weights']

        for symbol in theme_stocks:
            today_price_key = f'{symbol}_price'
            today_price = today_prices.get(today_price_key, 0)
            yesterday_price = yesterday_prices.get(today_price_key, 0)

            if today_price == 0 or yesterday_price == 0:
                continue

            # 计算价格变化
            price_change = (today_price - yesterday_price) / yesterday_price

            # 机会1：回调买入（下跌2-5%）
            if -0.05 <= price_change <= -0.02:
                current_weight = current_weights.get(symbol, {}).get('weight', 0)

                opportunities.append({
                    'symbol': symbol,
                    'opportunity_type': 'PULLBACK',
                    'confidence': 'HIGH',
                    'today_price': today_price,
                    'price_change': round(price_change, 4),
                    'current_weight': round(current_weight, 4),
                    'action': '逢低买入' if current_weight < 0.15 else '小幅加仓',
                    'reason': f'主题股回调{abs(price_change)*100:.1f}%，提供买入机会'
                })

            # 机会2：超跌机会（下跌>5%）
            elif price_change < -0.05:
                current_weight = current_weights.get(symbol, {}).get('weight', 0)

                opportunities.append({
                    'symbol': symbol,
                    'opportunity_type': 'OVERSOLD',
                    'confidence': 'VERY_HIGH',
                    'today_price': today_price,
                    'price_change': round(price_change, 4),
                    'current_weight': round(current_weight, 4),
                    'action': '强烈买入',
                    'reason': f'主题股超跌{abs(price_change)*100:.1f}%，抄底机会'
                })

            # 机会3：权重过低的优质股
            elif symbol in current_weights:
                weight = current_weights[symbol]['weight']
                if weight < 0.08 and price_change > -0.02:
                    opportunities.append({
                        'symbol': symbol,
                        'opportunity_type': 'UNDERWEIGHT',
                        'confidence': 'MEDIUM',
                        'today_price': today_price,
                        'price_change': round(price_change, 4),
                        'current_weight': round(weight, 4),
                        'action': '加仓至10-15%',
                        'reason': f'主题核心股权重仅{weight*100:.1f}%，配置不足'
                    })

        return opportunities

    def generate_daily_report(
        self,
        positions: Dict[str, float],
        today_prices: Dict[str, float],
        yesterday_prices: Dict[str, float],
        theme_stocks: List[str]
    ) -> Dict:
        """
        生成每日风险/机会报告

        Returns:
            {
                'portfolio_analysis': {...},
                'position_risks': [...],
                'cash_risk': {...},
                'opportunities': [...],
                'summary': {...}
            }
        """
        # 1. 组合分析
        portfolio_analysis = self.calculate_portfolio_weights(positions, today_prices)

        # 2. 风险检测
        position_risks = self.check_position_risks(portfolio_analysis)
        cash_risk = self.check_cash_risks(portfolio_analysis)

        # 3. 机会识别
        opportunities = self.identify_buying_opportunities(
            today_prices,
            yesterday_prices,
            theme_stocks,
            portfolio_analysis
        )

        # 4. 生成摘要
        summary = {
            'total_value': portfolio_analysis['total_value'],
            'cash_ratio': portfolio_analysis['cash_ratio'],
            'num_holdings': len([w for w in portfolio_analysis['weights'].values() if w['shares'] > 0]),
            'num_risks': len(position_risks) + (1 if cash_risk else 0),
            'num_opportunities': len(opportunities),
            'high_risk_positions': [r['symbol'] for r in position_risks if r.get('severity') == 'HIGH'],
            'high_confidence_opportunities': [o['symbol'] for o in opportunities if o.get('confidence') == 'VERY_HIGH']
        }

        return {
            'portfolio_analysis': portfolio_analysis,
            'position_risks': position_risks,
            'cash_risk': cash_risk,
            'opportunities': opportunities,
            'summary': summary
        }


def print_daily_report(report: Dict):
    """打印每日报告"""
    print("\n" + "=" * 70)
    print("📊 每日风险/机会报告")
    print("=" * 70)

    # 1. 组合概况
    summary = report['summary']
    print(f"\n💼 组合概况:")
    print(f"  总资产: ${summary['total_value']:,.2f}")
    print(f"  现金比例: {summary['cash_ratio']*100:.2f}%")
    print(f"  持仓数量: {summary['num_holdings']}只")

    # 2. 风险警告
    print(f"\n⚠️ 风险警告 ({summary['num_risks']}项):")

    position_risks = report['position_risks']
    if position_risks:
        for risk in position_risks:
            severity_emoji = "🔴" if risk['severity'] == 'HIGH' else "🟡"
            print(f"\n  {severity_emoji} {risk['symbol']} - {risk['risk_type']}")
            print(f"     当前权重: {risk['current_weight']*100:.1f}%")
            print(f"     建议操作: {risk['action']}")
            print(f"     原因: {risk['reason']}")

    cash_risk = report['cash_risk']
    if cash_risk:
        print(f"\n  🟡 现金管理 - {cash_risk['risk_type']}")
        print(f"     当前比例: {cash_risk['current_ratio']*100:.1f}%")
        print(f"     建议操作: {cash_risk['action']}")
        print(f"     原因: {cash_risk['reason']}")

    if not position_risks and not cash_risk:
        print("  ✅ 无明显风险")

    # 3. 买入机会
    print(f"\n💡 买入机会 ({summary['num_opportunities']}个):")

    opportunities = report['opportunities']
    if opportunities:
        # 按置信度排序
        sorted_opps = sorted(
            opportunities,
            key=lambda x: {'VERY_HIGH': 3, 'HIGH': 2, 'MEDIUM': 1}.get(x['confidence'], 0),
            reverse=True
        )

        for opp in sorted_opps[:5]:  # 只显示前5个
            confidence_emoji = "🔥" if opp['confidence'] == 'VERY_HIGH' else "⭐" if opp['confidence'] == 'HIGH' else "💫"
            print(f"\n  {confidence_emoji} {opp['symbol']} - {opp['opportunity_type']}")
            print(f"     价格变化: {opp['price_change']*100:+.2f}%")
            print(f"     当前价格: ${opp['today_price']:.2f}")
            print(f"     建议操作: {opp['action']}")
            print(f"     原因: {opp['reason']}")
    else:
        print("  暂无明显机会")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    """测试代码"""
    from tools.general_tools import get_config_value
    from tools.price_tools import get_today_init_position

    # 配置
    today_date = "2025-10-24"
    signature = "deepseek-chat-v3.1"

    # 获取数据
    all_symbols = [
        "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
        "AMD", "ASML", "QCOM", "AMAT", "ARM"
    ]

    theme_stocks = ["NVDA", "AMD", "MSFT", "GOOGL", "ASML", "AVGO", "QCOM", "AMAT", "ARM"]

    today_prices = get_open_prices(today_date, all_symbols)
    yesterday_buy, yesterday_sell = get_yesterday_open_and_close_price(today_date, all_symbols)
    positions = get_today_init_position(today_date, signature)

    # 创建检测器
    detector = RiskOpportunityDetector(
        max_single_weight=0.20,
        min_cash_ratio=0.01,
        max_cash_ratio=0.03
    )

    # 生成报告
    report = detector.generate_daily_report(
        positions,
        today_prices,
        yesterday_sell,  # 使用昨日收盘价作为对比
        theme_stocks
    )

    # 打印报告
    print_daily_report(report)

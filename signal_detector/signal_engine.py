"""
独立风险/机会信号检测引擎
可单独运行，提供实时市场信号分析

核心功能：
1. 宏观风险信号检测
2. 个股风险评估
3. 买入机会识别
4. 卖出信号提示
5. 每日报告生成
"""

import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from enum import Enum


class SignalType(Enum):
    """信号类型"""
    RISK = "风险"
    OPPORTUNITY = "机会"
    NEUTRAL = "中性"


class SignalLevel(Enum):
    """信号强度"""
    CRITICAL = "极高"
    HIGH = "高"
    MEDIUM = "中等"
    LOW = "低"


class RiskSignal:
    """风险信号"""
    def __init__(
        self,
        signal_type: str,
        level: SignalLevel,
        score: int,
        description: str,
        action: str,
        details: Dict = None
    ):
        self.signal_type = signal_type
        self.level = level
        self.score = score
        self.description = description
        self.action = action
        self.details = details or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        return {
            'signal_type': self.signal_type,
            'level': self.level.value,
            'score': self.score,
            'description': self.description,
            'action': self.action,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }


class OpportunitySignal:
    """机会信号"""
    def __init__(
        self,
        symbol: str,
        opportunity_type: str,
        confidence: SignalLevel,
        score: int,
        price: float,
        price_change: float,
        action: str,
        reason: str,
        details: Dict = None
    ):
        self.symbol = symbol
        self.opportunity_type = opportunity_type
        self.confidence = confidence
        self.score = score
        self.price = price
        self.price_change = price_change
        self.action = action
        self.reason = reason
        self.details = details or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'opportunity_type': self.opportunity_type,
            'confidence': self.confidence.value,
            'score': self.score,
            'price': self.price,
            'price_change': self.price_change,
            'action': self.action,
            'reason': self.reason,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }


class SignalEngine:
    """信号检测引擎"""

    def __init__(self, config: Dict = None):
        """
        初始化信号引擎

        Args:
            config: 配置参数
                {
                    'max_single_weight': 0.20,
                    'min_cash_ratio': 0.01,
                    'max_cash_ratio': 0.03,
                    'risk_thresholds': {...},
                    'opportunity_thresholds': {...}
                }
        """
        self.config = config or self._default_config()

    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 权重管理
            'max_single_weight': 0.20,
            'critical_weight': 0.25,
            'min_cash_ratio': 0.01,
            'max_cash_ratio': 0.03,

            # 风险阈值
            'risk_thresholds': {
                'market_drop': {
                    'critical': -0.035,  # -3.5%
                    'high': -0.025,      # -2.5%
                    'medium': -0.015     # -1.5%
                },
                'position_concentration': {
                    'critical': 0.30,    # 30%
                    'high': 0.25,        # 25%
                    'medium': 0.20       # 20%
                }
            },

            # 机会阈值
            'opportunity_thresholds': {
                'oversold': -0.05,       # 超跌 -5%
                'pullback': -0.02,       # 回调 -2%
                'strong_momentum': 0.03   # 强势 +3%
            }
        }

    def detect_market_risk(
        self,
        market_data: Dict[str, float],
        news_sentiment: Dict = None
    ) -> List[RiskSignal]:
        """
        检测宏观市场风险

        Args:
            market_data: {
                'market_change': -0.025,  # 市场涨跌幅
                'vix': 25.0,              # 波动率指数
                'volume_ratio': 1.5       # 成交量比
            }
            news_sentiment: {
                'trade_war': 0.8,    # 贸易战风险
                'fed_policy': 0.3,   # 美联储政策
                'geopolitical': 0.5  # 地缘政治
            }

        Returns:
            List[RiskSignal]
        """
        signals = []

        # 1. 市场跌幅风险
        market_change = market_data.get('market_change', 0)
        thresholds = self.config['risk_thresholds']['market_drop']

        if market_change <= thresholds['critical']:
            signals.append(RiskSignal(
                signal_type='MARKET_CRASH',
                level=SignalLevel.CRITICAL,
                score=90,
                description=f'市场暴跌 {market_change*100:.1f}%',
                action='立即减仓50%+，大幅提高现金比例至20%+',
                details={'market_change': market_change}
            ))
        elif market_change <= thresholds['high']:
            signals.append(RiskSignal(
                signal_type='MARKET_DROP',
                level=SignalLevel.HIGH,
                score=70,
                description=f'市场大幅下跌 {market_change*100:.1f}%',
                action='适度减仓30%，提高现金比例至15%',
                details={'market_change': market_change}
            ))
        elif market_change <= thresholds['medium']:
            signals.append(RiskSignal(
                signal_type='MARKET_WEAK',
                level=SignalLevel.MEDIUM,
                score=50,
                description=f'市场走弱 {market_change*100:.1f}%',
                action='停止买入，观望为主',
                details={'market_change': market_change}
            ))

        # 2. VIX波动率风险
        vix = market_data.get('vix', 15)
        if vix > 30:
            signals.append(RiskSignal(
                signal_type='HIGH_VOLATILITY',
                level=SignalLevel.HIGH,
                score=75,
                description=f'VIX波动率高企 {vix:.1f}',
                action='减少仓位，增加防御性资产',
                details={'vix': vix}
            ))
        elif vix > 20:
            signals.append(RiskSignal(
                signal_type='ELEVATED_VOLATILITY',
                level=SignalLevel.MEDIUM,
                score=55,
                description=f'VIX波动率上升 {vix:.1f}',
                action='控制仓位，谨慎操作',
                details={'vix': vix}
            ))

        # 3. 新闻情绪风险
        if news_sentiment:
            if news_sentiment.get('trade_war', 0) > 0.7:
                signals.append(RiskSignal(
                    signal_type='TRADE_WAR',
                    level=SignalLevel.HIGH,
                    score=80,
                    description='贸易战风险升级',
                    action='减少科技股仓位，增加防御性资产',
                    details=news_sentiment
                ))

        return signals

    def detect_position_risk(
        self,
        positions: Dict[str, float],
        prices: Dict[str, float],
        total_value: float
    ) -> List[RiskSignal]:
        """
        检测持仓风险

        Args:
            positions: {symbol: shares}
            prices: {symbol: price}
            total_value: 总资产

        Returns:
            List[RiskSignal]
        """
        signals = []

        for symbol, shares in positions.items():
            if symbol == 'CASH' or shares == 0:
                continue

            price = prices.get(symbol, 0)
            if price == 0:
                continue

            # 计算权重
            position_value = shares * price
            weight = position_value / total_value

            # 权重风险检测
            if weight >= self.config['risk_thresholds']['position_concentration']['critical']:
                signals.append(RiskSignal(
                    signal_type='POSITION_OVERWEIGHT_CRITICAL',
                    level=SignalLevel.CRITICAL,
                    score=95,
                    description=f'{symbol} 权重极高 {weight*100:.1f}%',
                    action=f'立即卖出，降低至18%',
                    details={
                        'symbol': symbol,
                        'weight': weight,
                        'shares': shares,
                        'value': position_value
                    }
                ))
            elif weight >= self.config['risk_thresholds']['position_concentration']['high']:
                signals.append(RiskSignal(
                    signal_type='POSITION_OVERWEIGHT_HIGH',
                    level=SignalLevel.HIGH,
                    score=75,
                    description=f'{symbol} 权重过高 {weight*100:.1f}%',
                    action=f'卖出部分，降低至15-18%',
                    details={
                        'symbol': symbol,
                        'weight': weight,
                        'shares': shares,
                        'value': position_value
                    }
                ))
            elif weight >= self.config['max_single_weight']:
                signals.append(RiskSignal(
                    signal_type='POSITION_OVERWEIGHT',
                    level=SignalLevel.MEDIUM,
                    score=60,
                    description=f'{symbol} 接近权重上限 {weight*100:.1f}%',
                    action='考虑适度减仓',
                    details={
                        'symbol': symbol,
                        'weight': weight,
                        'shares': shares,
                        'value': position_value
                    }
                ))

        return signals

    def detect_cash_risk(
        self,
        cash: float,
        total_value: float
    ) -> Optional[RiskSignal]:
        """
        检测现金管理风险

        Args:
            cash: 现金金额
            total_value: 总资产

        Returns:
            RiskSignal or None
        """
        cash_ratio = cash / total_value if total_value > 0 else 0

        if cash_ratio > self.config['max_cash_ratio'] * 2:  # 超过6%
            return RiskSignal(
                signal_type='EXCESSIVE_CASH',
                level=SignalLevel.HIGH,
                score=70,
                description=f'现金比例过高 {cash_ratio*100:.1f}%',
                action='寻找买入机会，部署闲置资金',
                details={'cash_ratio': cash_ratio, 'cash': cash}
            )
        elif cash_ratio > self.config['max_cash_ratio']:  # 超过3%
            return RiskSignal(
                signal_type='HIGH_CASH',
                level=SignalLevel.MEDIUM,
                score=50,
                description=f'现金比例偏高 {cash_ratio*100:.1f}%',
                action='考虑买入优质标的',
                details={'cash_ratio': cash_ratio, 'cash': cash}
            )
        elif cash_ratio < self.config['min_cash_ratio']:  # 低于1%
            return RiskSignal(
                signal_type='LOW_CASH',
                level=SignalLevel.MEDIUM,
                score=55,
                description=f'现金比例过低 {cash_ratio*100:.1f}%',
                action='卖出部分持仓，增加灵活性',
                details={'cash_ratio': cash_ratio, 'cash': cash}
            )

        return None

    def identify_opportunities(
        self,
        symbols: List[str],
        current_prices: Dict[str, float],
        previous_prices: Dict[str, float],
        holdings: Dict[str, float] = None,
        total_value: float = None,
        theme_stocks: List[str] = None
    ) -> List[OpportunitySignal]:
        """
        识别买入机会

        Args:
            symbols: 股票列表
            current_prices: 当前价格
            previous_prices: 之前价格
            holdings: 当前持仓 {symbol: shares}
            total_value: 总资产
            theme_stocks: 主题股票列表

        Returns:
            List[OpportunitySignal]
        """
        opportunities = []
        holdings = holdings or {}
        theme_stocks = theme_stocks or []

        for symbol in symbols:
            curr_price = current_prices.get(symbol, 0)
            prev_price = previous_prices.get(symbol, 0)

            if curr_price == 0 or prev_price == 0:
                continue

            # 计算价格变化
            price_change = (curr_price - prev_price) / prev_price

            # 计算当前权重
            shares = holdings.get(symbol, 0)
            position_value = shares * curr_price
            weight = position_value / total_value if total_value else 0

            # 是否为主题股
            is_theme = symbol in theme_stocks

            # 机会1：超跌机会（下跌>5%）
            if price_change <= self.config['opportunity_thresholds']['oversold']:
                score = 80
                if is_theme:
                    score += 15
                if weight < 0.10:
                    score += 5

                opportunities.append(OpportunitySignal(
                    symbol=symbol,
                    opportunity_type='OVERSOLD',
                    confidence=SignalLevel.CRITICAL if score >= 90 else SignalLevel.HIGH,
                    score=score,
                    price=curr_price,
                    price_change=price_change,
                    action='强烈买入' if score >= 90 else '逢低买入',
                    reason=f'{"主题股" if is_theme else "个股"}超跌{abs(price_change)*100:.1f}%，抄底机会',
                    details={'is_theme': is_theme, 'current_weight': weight}
                ))

            # 机会2：回调买入（下跌2-5%）
            elif price_change <= self.config['opportunity_thresholds']['pullback']:
                score = 60
                if is_theme:
                    score += 10
                if weight < 0.15:
                    score += 10

                opportunities.append(OpportunitySignal(
                    symbol=symbol,
                    opportunity_type='PULLBACK',
                    confidence=SignalLevel.HIGH if score >= 75 else SignalLevel.MEDIUM,
                    score=score,
                    price=curr_price,
                    price_change=price_change,
                    action='逢低买入',
                    reason=f'{"主题股" if is_theme else "个股"}回调{abs(price_change)*100:.1f}%，买入机会',
                    details={'is_theme': is_theme, 'current_weight': weight}
                ))

            # 机会3：权重过低的主题股
            elif is_theme and weight < 0.08 and abs(price_change) < 0.02:
                score = 55

                opportunities.append(OpportunitySignal(
                    symbol=symbol,
                    opportunity_type='UNDERWEIGHT',
                    confidence=SignalLevel.MEDIUM,
                    score=score,
                    price=curr_price,
                    price_change=price_change,
                    action='加仓至10-15%',
                    reason=f'主题核心股权重仅{weight*100:.1f}%，配置不足',
                    details={'is_theme': is_theme, 'current_weight': weight}
                ))

            # 机会4：强势突破（上涨>3%且权重低）
            elif price_change >= self.config['opportunity_thresholds']['strong_momentum'] and weight < 0.10:
                score = 50
                if is_theme:
                    score += 10

                opportunities.append(OpportunitySignal(
                    symbol=symbol,
                    opportunity_type='MOMENTUM',
                    confidence=SignalLevel.MEDIUM,
                    score=score,
                    price=curr_price,
                    price_change=price_change,
                    action='追涨买入',
                    reason=f'强势上涨{price_change*100:.1f}%，趋势向好',
                    details={'is_theme': is_theme, 'current_weight': weight}
                ))

        # 按分数排序
        opportunities.sort(key=lambda x: x.score, reverse=True)

        return opportunities

    def generate_daily_signals(
        self,
        market_data: Dict,
        portfolio: Dict,
        theme_stocks: List[str] = None
    ) -> Dict:
        """
        生成每日信号报告

        Args:
            market_data: {
                'market_change': -0.025,
                'vix': 25.0,
                'current_prices': {symbol: price},
                'previous_prices': {symbol: price}
            }
            portfolio: {
                'positions': {symbol: shares},
                'cash': 1000.0,
                'total_value': 10000.0
            }
            theme_stocks: 主题股票列表

        Returns:
            {
                'risk_signals': [...]
                'opportunity_signals': [...]
                'summary': {...}
            }
        """
        risk_signals = []

        # 1. 市场风险
        market_risks = self.detect_market_risk(market_data)
        risk_signals.extend(market_risks)

        # 2. 持仓风险
        position_risks = self.detect_position_risk(
            portfolio['positions'],
            market_data['current_prices'],
            portfolio['total_value']
        )
        risk_signals.extend(position_risks)

        # 3. 现金风险
        cash_risk = self.detect_cash_risk(
            portfolio['cash'],
            portfolio['total_value']
        )
        if cash_risk:
            risk_signals.append(cash_risk)

        # 4. 机会识别
        opportunities = self.identify_opportunities(
            symbols=list(market_data['current_prices'].keys()),
            current_prices=market_data['current_prices'],
            previous_prices=market_data['previous_prices'],
            holdings=portfolio['positions'],
            total_value=portfolio['total_value'],
            theme_stocks=theme_stocks
        )

        # 5. 生成摘要
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_risks': len(risk_signals),
            'critical_risks': len([r for r in risk_signals if r.level == SignalLevel.CRITICAL]),
            'high_risks': len([r for r in risk_signals if r.level == SignalLevel.HIGH]),
            'total_opportunities': len(opportunities),
            'high_confidence_opportunities': len([o for o in opportunities if o.confidence in [SignalLevel.CRITICAL, SignalLevel.HIGH]]),
            'portfolio_value': portfolio['total_value'],
            'cash_ratio': portfolio['cash'] / portfolio['total_value'] if portfolio['total_value'] > 0 else 0
        }

        return {
            'risk_signals': [r.to_dict() for r in risk_signals],
            'opportunity_signals': [o.to_dict() for o in opportunities],
            'summary': summary
        }


if __name__ == "__main__":
    # 测试代码
    engine = SignalEngine()

    # 模拟市场数据
    market_data = {
        'market_change': -0.028,
        'vix': 26.5,
        'current_prices': {
            'NVDA': 180.50,
            'MSFT': 420.00,
            'AMD': 115.00
        },
        'previous_prices': {
            'NVDA': 189.00,
            'MSFT': 425.00,
            'AMD': 122.50
        }
    }

    # 模拟组合
    portfolio = {
        'positions': {
            'NVDA': 50,
            'MSFT': 10,
            'AMD': 20
        },
        'cash': 500.0,
        'total_value': 12500.0
    }

    # 生成信号
    signals = engine.generate_daily_signals(
        market_data,
        portfolio,
        theme_stocks=['NVDA', 'AMD']
    )

    print(json.dumps(signals, indent=2, ensure_ascii=False))

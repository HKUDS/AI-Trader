"""Hold 策略：不交易，始终返回 hold。"""

from service_trading_crypto.strategy.data import Signal, SignalAction
from service_trading_crypto.strategy.example.interface.base import BaseStrategy, StrategyContext


class HoldStrategy(BaseStrategy):
    """evaluate 始终返回 HOLD。"""

    def evaluate(self, context: StrategyContext) -> Signal:
        return Signal(action=SignalAction.HOLD, confidence=0.0, reason="hold", metadata={})

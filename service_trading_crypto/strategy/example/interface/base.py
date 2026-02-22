"""策略接口：BaseStrategy 与数据类型统一入口。"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from service_trading_crypto.strategy.data import Signal, SignalAction, StrategyContext


class BaseStrategy(ABC):
    """策略基类：由 StrategyManager 选择并执行。"""

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def evaluate(self, context: StrategyContext) -> Signal:
        """根据 context 返回买卖信号。"""
        pass


__all__ = ["BaseStrategy", "Signal", "SignalAction", "StrategyContext"]

"""Moving average indicators: SMA, EMA."""

from collections import deque
from typing import Any, Dict

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike


class SMAIndicator(BaseIndicator):
    """Simple moving average over close prices. 同 ts 的推送会替换最后一根，避免重复计入。"""

    def __init__(self, name: str, period: int = 20, **kwargs: Any) -> None:
        super().__init__(name, period=period, **kwargs)
        self.period = max(1, int(period))
        self._buffer: deque = deque()

    def update(self, candle: CandleLike) -> None:
        self._ingest_candle(candle, self._buffer, self.period)

    def get_value(self) -> Dict[str, Any]:
        if len(self._buffer) < self.period:
            return {self.name: None}
        closes = [c.close for c in self._buffer]
        return {self.name: sum(closes) / len(closes)}

    def reset(self) -> None:
        self._buffer.clear()


class EMAIndicator(BaseIndicator):
    """Exponential moving average over close prices. 同 ts 的推送会替换最后一根，避免重复计入。"""

    def __init__(self, name: str, period: int = 20, **kwargs: Any) -> None:
        super().__init__(name, period=period, **kwargs)
        self.period = max(1, int(period))
        self._alpha = 2.0 / (self.period + 1.0)
        self._buffer: deque = deque()

    def update(self, candle: CandleLike) -> None:
        self._ingest_candle(candle, self._buffer, self.period * 2)

    def get_value(self) -> Dict[str, Any]:
        if not self._buffer:
            return {self.name: None}
        closes = [c.close for c in self._buffer]
        ema = closes[0]
        for c in closes[1:]:
            ema = self._alpha * c + (1.0 - self._alpha) * ema
        return {self.name: ema}

    def reset(self) -> None:
        self._buffer.clear()

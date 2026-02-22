"""ATR (Average True Range) indicator for volatility."""

from collections import deque
from typing import Any, Dict, List

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike


class ATRIndicator(BaseIndicator):
    """Average True Range over N periods. 同 ts 的推送会替换最后一根，避免重复计入。"""

    def __init__(self, name: str, period: int = 14, **kwargs: Any) -> None:
        super().__init__(name, period=period, **kwargs)
        self.period = max(1, int(period))
        self._buffer: deque = deque()

    def _tr_list(self, candles: List[CandleLike]) -> List[float]:
        out = []
        for i, c in enumerate(candles):
            if i == 0:
                out.append(c.high - c.low)
            else:
                prev = candles[i - 1].close
                out.append(max(c.high - c.low, abs(c.high - prev), abs(c.low - prev)))
        return out

    def update(self, candle: CandleLike) -> None:
        self._ingest_candle(candle, self._buffer, self.period + 2)

    def get_value(self) -> Dict[str, Any]:
        candles = list(self._buffer)
        if len(candles) < self.period:
            return {self.name: None}
        trs = self._tr_list(candles)
        return {self.name: sum(trs[-self.period :]) / self.period}

    def reset(self) -> None:
        self._buffer.clear()

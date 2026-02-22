"""Volume-based indicators."""

from collections import deque
from typing import Any, Dict

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike


class VolumeSMAIndicator(BaseIndicator):
    """Simple moving average of volume. 同 ts 的推送会替换最后一根，避免重复计入。"""

    def __init__(self, name: str, period: int = 20, **kwargs: Any) -> None:
        super().__init__(name, period=period, **kwargs)
        self.period = max(1, int(period))
        self._buffer: deque = deque()

    def update(self, candle: CandleLike) -> None:
        self._ingest_candle(candle, self._buffer, self.period)

    def get_value(self) -> Dict[str, Any]:
        if len(self._buffer) < self.period:
            return {self.name: None}
        vols = [c.volume for c in self._buffer]
        return {self.name: sum(vols) / len(vols)}

    def reset(self) -> None:
        self._buffer.clear()

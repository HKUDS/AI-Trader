"""RSI (Relative Strength Index) with Wilder smoothing."""

from collections import deque
from typing import Any, Dict, List

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike


class RSIIndicator(BaseIndicator):
    """RSI(period): Wilder smoothing. 同 ts 的推送会替换最后一根，避免重复计入。"""

    def __init__(self, name: str, period: int = 14, **kwargs: Any) -> None:
        super().__init__(name, period=period, **kwargs)
        self.period = max(2, int(period))
        self._buffer: deque = deque()

    def _rsi_from_closes(self, closes: List[float]) -> float | None:
        """从 close 序列计算 RSI，Wilder 平滑。"""
        if len(closes) < self.period + 1:
            return None
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(0.0, d))
            losses.append(max(0.0, -d))
        use_g = gains[-self.period:]
        use_l = losses[-self.period:]
        avg_g = sum(use_g) / self.period
        avg_l = sum(use_l) / self.period
        if avg_l <= 0:
            return 100.0
        rs = avg_g / avg_l
        return 100.0 - (100.0 / (1.0 + rs))

    def update(self, candle: CandleLike) -> None:
        self._ingest_candle(candle, self._buffer, self.period + 5)

    def get_value(self) -> Dict[str, Any]:
        closes = [c.close for c in self._buffer]
        val = self._rsi_from_closes(closes)
        return {self.name: val}

    def reset(self) -> None:
        self._buffer.clear()

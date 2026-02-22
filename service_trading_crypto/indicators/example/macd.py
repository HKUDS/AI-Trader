"""MACD indicator: MACD line, signal line, histogram."""

from collections import deque
from typing import Any, Dict, List

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike


class MACDIndicator(BaseIndicator):
    """MACD: fast_ema - slow_ema; signal = EMA(macd); histogram = macd - signal. 同 ts 会替换最后一根。"""

    def __init__(
        self,
        name: str,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, fast_period=fast_period, slow_period=slow_period, signal_period=signal_period, **kwargs)
        self.fast_period = max(1, int(fast_period))
        self.slow_period = max(self.fast_period + 1, int(slow_period))
        self.signal_period = max(1, int(signal_period))
        self._alpha_fast = 2.0 / (self.fast_period + 1.0)
        self._alpha_slow = 2.0 / (self.slow_period + 1.0)
        self._alpha_signal = 2.0 / (self.signal_period + 1.0)
        self._buffer: deque = deque()

    def _ema_series(self, closes: List[float], alpha: float) -> List[float]:
        out = [closes[0]]
        for c in closes[1:]:
            out.append(alpha * c + (1.0 - alpha) * out[-1])
        return out

    def update(self, candle: CandleLike) -> None:
        self._ingest_candle(candle, self._buffer, self.slow_period + self.signal_period + 10)

    def get_value(self) -> Dict[str, Any]:
        closes = [c.close for c in self._buffer]
        if len(closes) < self.slow_period:
            return {f"{self.name}_macd": None, f"{self.name}_signal": None, f"{self.name}_histogram": None}
        fast_ema = self._ema_series(closes, self._alpha_fast)
        slow_ema = self._ema_series(closes, self._alpha_slow)
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
        if not macd_line:
            return {f"{self.name}_macd": None, f"{self.name}_signal": None, f"{self.name}_histogram": None}
        signal_ema = self._ema_series(macd_line, self._alpha_signal)
        last_macd = macd_line[-1]
        last_signal = signal_ema[-1]
        return {
            f"{self.name}_macd": last_macd,
            f"{self.name}_signal": last_signal,
            f"{self.name}_histogram": last_macd - last_signal,
        }

    def reset(self) -> None:
        self._buffer.clear()

"""Base class for technical indicators."""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class CandleLike:
    """Minimal OHLCV for indicator input (OKX / generic), with optional channel tag."""

    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    channel: str = ""  # e.g. "candle4H", "candle15m", "tickers"

    @classmethod
    def from_okx_candle(cls, raw: list, channel: str = "") -> "CandleLike":
        """OKX v5 candle: [ts, o, h, l, c, vol, ...]."""
        return cls(
            ts=str(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]) if len(raw) > 5 else 0.0,
            channel=channel,
        )


class BaseIndicator(ABC):
    """Abstract base for pluggable indicators."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        self.name = name
        self._kwargs = kwargs

    @abstractmethod
    def update(self, candle: CandleLike) -> None:
        """Ingest one candle; update internal state."""
        pass

    @abstractmethod
    def get_value(self) -> Dict[str, Any]:
        """Return current value(s)."""
        pass

    def reset(self) -> None:
        """Clear state when symbol/timeframe changes."""
        pass

    def _ingest_candle(self, candle: CandleLike, buf: deque, maxlen: Optional[int] = None) -> None:
        """同 ts 则替换最后一根，再追加；避免同一根 K 线被重复计入。buf 元素需有 .ts 属性。"""
        if buf and getattr(buf[-1], "ts", None) == candle.ts:
            buf.pop()
        buf.append(candle)
        if maxlen is not None:
            while len(buf) > maxlen:
                buf.popleft()

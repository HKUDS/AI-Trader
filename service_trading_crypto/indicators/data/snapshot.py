"""Market snapshot and processed (multi-timeframe) snapshot for agent/strategy."""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class MarketSnapshot:
    """One snapshot for the agent: latest candle + indicator values."""

    # the channel of the snapshot, it's unique for each snapshot
    channel: str  # e.g. "candle4H", "candle15m"

    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: Dict[str, Any]  # e.g. "macd": 1.0, "rsi": 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "ts": self.ts,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "indicators": self.indicators,

        }

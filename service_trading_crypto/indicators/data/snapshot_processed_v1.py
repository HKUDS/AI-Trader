"""SnapshotProcessedV1: 按 channel 聚合的最近快照，供 Agent/Strategy 使用。"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from service_trading_crypto.indicators.data.snapshot import MarketSnapshot


@dataclass
class SnapshotProcessedV1:
    """Snapshot containing latest data per channel (e.g. candle4H, candle15m)."""

    ts: str # latest snapshot timestamp
    compose_snapshot: Dict[str, MarketSnapshot]  # channel -> MarketSnapshot

    def get(self, channel: str) -> Optional[MarketSnapshot]:
        return self.compose_snapshot.get(channel)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "compose_snapshot": {ch: s.to_dict() for ch, s in self.compose_snapshot.items()},
        }

"""Strategy input: StrategyContext (trigger_channel + snapshot_processed_v2 + optional history)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from service_trading_crypto.indicators import MarketSnapshot, SnapshotProcessedV1, SnapshotProcessedV2


@dataclass
class StrategyContext:
    """策略上下文：当前 V2 快照、触发 channel、可选的 V1 历史（由旧到新）、以及策略间共享的 state。"""

    trigger_channel: str
    snapshot_processed_v2: SnapshotProcessedV2
    snapshot_processed_v1_history: List[SnapshotProcessedV1] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)

    @property
    def market_snapshot(self) -> MarketSnapshot | None:
        """当前触发 channel 的 MarketSnapshot。"""
        return self.snapshot_processed_v2.snapshot_processed_v1.get(self.trigger_channel)

    @property
    def market_snapshot_history(self) -> List[MarketSnapshot]:
        """触发 channel 的历史（由旧到新），从 snapshot_processed_v1_history 提取。"""
        out: List[MarketSnapshot] = []
        for sp in self.snapshot_processed_v1_history:
            s = sp.get(self.trigger_channel)
            if s is not None:
                out.append(s)
        return out

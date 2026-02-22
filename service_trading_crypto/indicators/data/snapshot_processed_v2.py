"""SnapshotProcessedV2: SnapshotProcessedV1 + agent 分析结果，供 StrategyManager 从队列读取。"""

from dataclasses import dataclass
from typing import Any, Dict

from service_trading_crypto.indicators.data.snapshot_processed_v1 import SnapshotProcessedV1


@dataclass
class SnapshotProcessedV2:
    """层层包装：包含 snapshot_processed 与 agent 分析结果，供 StrategyManager 从队列读取。"""

    snapshot_processed_v1: SnapshotProcessedV1
    agent_result: Dict[str, Any]  # e.g. action, reason, confidence, snapshot_ts

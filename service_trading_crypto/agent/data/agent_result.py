"""Agent 分析结果：action、reason、snapshot_ts、confidence 等，与 SnapshotProcessedV2.agent_result 对应。"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AgentResult:
    """
    Agent 返回的分析结果，供 StrategyManager 或下游使用。
    与 strategy Signal 对齐：action 为 hold/buy/sell 等，confidence 0.0~1.0。
    """

    action: str  # "hold" | "buy" | "sell" | "stop_loss" | "take_profit" 等
    reason: str  # 分析理由或模型输出摘要
    snapshot_ts: str  # 所分析快照的时间戳
    confidence: float = 0.0  # 0.0 ~ 1.0，可选
    metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展字段（如 LLM 原始内容）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "snapshot_ts": self.snapshot_ts,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResult":
        if not isinstance(data, dict):
            raise TypeError("agent_result must be a dict")
        return cls(
            action=str(data.get("action", "hold")),
            reason=str(data.get("reason", "")),
            snapshot_ts=str(data.get("snapshot_ts", "")),
            confidence=float(data.get("confidence", 0.0)),
            metadata=dict(data.get("metadata", {})),
        )


def hold_result(snapshot_ts: str, reason: str = "default") -> Dict[str, Any]:
    """构造 hold 结果的 dict，供 AgentManager 直接放入 SnapshotProcessedV2.agent_result。"""
    return AgentResult(
        action="hold",
        reason=reason,
        snapshot_ts=snapshot_ts,
        confidence=0.0,
        metadata={},
    ).to_dict()

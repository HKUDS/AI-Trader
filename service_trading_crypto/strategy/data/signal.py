"""Strategy output: SignalAction enum and Signal dataclass."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class SignalAction(Enum):
    """Trading signal actions."""

    HOLD = "hold"
    BUY = "buy"
    SELL = "sell"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


@dataclass
class Signal:
    """Output of strategy evaluation."""

    action: SignalAction
    confidence: float  # 0.0 ~ 1.0
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "metadata": self.metadata,
        }

"""
AI trend analyzer: analyzes 4H peaks/troughs to judge trend (uptrend/downtrend/sideways).
Extensible: implement TrendAnalyzer interface for different AI backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from service_trading_crypto.indicators import MarketSnapshot


class TrendDirection(Enum):
    """Trend direction from peak/trough analysis."""

    UPTREND = "uptrend"      # 波峰波谷不断升高
    DOWNTREND = "downtrend"  # 波峰波谷不断降低
    SIDEWAYS = "sideways"    # 趋势不明显


@dataclass
class TrendResult:
    """Result of trend analysis."""

    direction: TrendDirection
    confidence: float  # 0.0 ~ 1.0
    reason: str
    metadata: Dict[str, Any]


class TrendAnalyzer(ABC):
    """Abstract interface for trend analysis. Implement with LLM or rule-based."""

    @abstractmethod
    def analyze_trend(self, candles_4h: List[MarketSnapshot]) -> TrendResult:
        """Analyze 4H candles (peaks/troughs) and return trend direction."""
        pass


@dataclass
class ExitEvaluation:
    """Result of exit evaluation: hold or close."""

    should_close: bool
    reason: str
    confidence: float


class ExitEvaluator(ABC):
    """Abstract interface for exit evaluation. AI evaluates trend clarity and exit timing."""

    @abstractmethod
    def evaluate(
        self,
        snapshot_4h: MarketSnapshot,
        snapshot_15m: MarketSnapshot,
        position_side: str,  # "long" | "short"
        history_4h: List[MarketSnapshot],
        history_15m: List[MarketSnapshot],
    ) -> ExitEvaluation:
        """Evaluate whether to hold or close the position."""
        pass


class RuleBasedTrendAnalyzer(TrendAnalyzer):
    """
    Simple rule-based trend: compare recent highs/lows.
    Placeholder; replace with LLM-based implementation.
    """

    def __init__(self, lookback: int = 5) -> None:
        self.lookback = lookback

    def analyze_trend(self, candles_4h: List[MarketSnapshot]) -> TrendResult:
        if len(candles_4h) < self.lookback:
            return TrendResult(
                direction=TrendDirection.SIDEWAYS,
                confidence=0.0,
                reason="insufficient_data",
                metadata={"count": len(candles_4h), "required": self.lookback},
            )

        recent = candles_4h[-self.lookback:]
        highs = [s.high for s in recent]
        lows = [s.low for s in recent]

        first_half = self.lookback // 2
        h1_avg = sum(highs[:first_half]) / first_half if first_half else highs[0]
        h2_avg = sum(highs[first_half:]) / (self.lookback - first_half)
        l1_avg = sum(lows[:first_half]) / first_half if first_half else lows[0]
        l2_avg = sum(lows[first_half:]) / (self.lookback - first_half)

        pct = 0.005
        if h2_avg > h1_avg * (1 + pct) and l2_avg > l1_avg * (1 + pct):
            return TrendResult(
                direction=TrendDirection.UPTREND,
                confidence=0.7,
                reason="higher_highs_higher_lows",
                metadata={"h1": h1_avg, "h2": h2_avg, "l1": l1_avg, "l2": l2_avg},
            )
        if h2_avg < h1_avg * (1 - pct) and l2_avg < l1_avg * (1 - pct):
            return TrendResult(
                direction=TrendDirection.DOWNTREND,
                confidence=0.7,
                reason="lower_highs_lower_lows",
                metadata={"h1": h1_avg, "h2": h2_avg, "l1": l1_avg, "l2": l2_avg},
            )

        return TrendResult(
            direction=TrendDirection.SIDEWAYS,
            confidence=0.5,
            reason="no_clear_trend",
            metadata={},
        )


class RuleBasedExitEvaluator(ExitEvaluator):
    """
    Simple rule-based exit: hold if trend matches position, else consider close.
    Placeholder; replace with LLM-based implementation.
    """

    def evaluate(
        self,
        snapshot_4h: MarketSnapshot,
        snapshot_15m: MarketSnapshot,
        position_side: str,
        history_4h: List[MarketSnapshot],
        history_15m: List[MarketSnapshot],
    ) -> ExitEvaluation:
        # Placeholder: always hold
        return ExitEvaluation(
            should_close=False,
            reason="rule_based_placeholder",
            confidence=0.5,
        )

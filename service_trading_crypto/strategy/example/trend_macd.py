"""
Trend + MACD strategy: 4H trend (AI) + 15m MACD cross for entry, 4H MACD cross / AI for exit.

Entry:
- 4H uptrend + 15m MACD golden cross -> BUY (long)
- 4H downtrend + 15m MACD death cross -> SELL (short)

Exit:
- Long: 4H death cross or AI says trend unclear -> close
- Short: 4H golden cross or AI says trend unclear -> close
"""

import logging
from typing import Any, Dict, List, Optional

from service_trading_crypto.indicators.example.macd_cross import (
    MacdCrossType,
    detect_macd_cross,
)
from service_trading_crypto.indicators import MarketSnapshot
from service_trading_crypto.strategy.example.interface.base import (
    BaseStrategy,
    Signal,
    SignalAction,
    StrategyContext,
)
from service_trading_crypto.strategy.example.ai_trend import (
    ExitEvaluator,
    ExitEvaluation,
    RuleBasedExitEvaluator,
    RuleBasedTrendAnalyzer,
    TrendAnalyzer,
    TrendDirection,
    TrendResult,
)

logger = logging.getLogger(__name__)


class TrendMACDStrategy(BaseStrategy):
    """
    多周期趋势+MACD策略:
    - 4H K线由AI分析波峰波谷判断趋势
    - 15m MACD金叉/死叉作为入场信号
    - 4H MACD交叉或AI评估趋势变化作为出场
    """

    KEY_ENTRY_PRICE = "entry_price"
    KEY_POSITION_SIDE = "position_side"  # "long" | "short"
    KEY_4H_HISTORY = "history_4h"
    KEY_15M_HISTORY = "history_15m"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        trend_analyzer: Optional[TrendAnalyzer] = None,
        exit_evaluator: Optional[ExitEvaluator] = None,
    ) -> None:
        super().__init__(config)
        self.macd_name_4h = str(self.config.get("macd_name_4h", "macd"))
        self.macd_name_15m = str(self.config.get("macd_name_15m", "macd"))
        self.trend_analyzer = trend_analyzer or RuleBasedTrendAnalyzer(lookback=5)
        self.exit_evaluator = exit_evaluator or RuleBasedExitEvaluator()

    CH_4H = "candle4H"
    CH_15M = "candle15m"

    def evaluate(self, context: StrategyContext) -> Signal:
        """从 context.snapshot_processed_v2 与 snapshot_processed_v1_history 取 candle4H / candle15m。"""
        sp1 = context.snapshot_processed_v2.snapshot_processed_v1
        snap_4h = sp1.get(self.CH_4H)
        snap_15m = sp1.get(self.CH_15M)
        if snap_4h is None or snap_15m is None:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="missing_candle4h_or_candle15m",
                metadata={},
            )
        history_4h: List[MarketSnapshot] = [s for sp in context.snapshot_processed_v1_history for s in (sp.get(self.CH_4H),) if s is not None]
        history_15m: List[MarketSnapshot] = [s for sp in context.snapshot_processed_v1_history for s in (sp.get(self.CH_15M),) if s is not None]
        state = context.state
        entry_price = state.get(self.KEY_ENTRY_PRICE)
        position_side = state.get(self.KEY_POSITION_SIDE, "")
        in_position = entry_price is not None and position_side in ("long", "short")

        # ---- In position: check exit ----
        if in_position:
            prev_4h = history_4h[-2] if len(history_4h) >= 2 else None
            prev_15m = history_15m[-2] if len(history_15m) >= 2 else None

            cross_4h = detect_macd_cross(snap_4h, prev_4h, self.macd_name_4h)

            # Exit by 4H MACD cross
            if position_side == "long" and cross_4h.cross_type == MacdCrossType.DEATH:
                state.pop(self.KEY_ENTRY_PRICE, None)
                state.pop(self.KEY_POSITION_SIDE, None)
                return Signal(
                    action=SignalAction.SELL,
                    confidence=0.9,
                    reason="4h_death_cross_close_long",
                    metadata={"entry_price": entry_price, "close": snap_4h.close},
                )
            if position_side == "short" and cross_4h.cross_type == MacdCrossType.GOLDEN:
                state.pop(self.KEY_ENTRY_PRICE, None)
                state.pop(self.KEY_POSITION_SIDE, None)
                return Signal(
                    action=SignalAction.BUY,  # cover short
                    confidence=0.9,
                    reason="4h_golden_cross_close_short",
                    metadata={"entry_price": entry_price, "close": snap_4h.close},
                )

            # Exit by AI evaluation (trend unclear)
            exit_eval = self.exit_evaluator.evaluate(
                snapshot_4h=snap_4h,
                snapshot_15m=snap_15m,
                position_side=position_side,
                history_4h=history_4h,
                history_15m=history_15m,
            )
            if exit_eval.should_close and exit_eval.confidence >= 0.7:
                state.pop(self.KEY_ENTRY_PRICE, None)
                state.pop(self.KEY_POSITION_SIDE, None)
                action = SignalAction.SELL if position_side == "long" else SignalAction.BUY
                return Signal(
                    action=action,
                    confidence=exit_eval.confidence,
                    reason=f"ai_exit_{exit_eval.reason}",
                    metadata={"entry_price": entry_price},
                )

            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="in_position_holding",
                metadata={"entry_price": entry_price, "side": position_side},
            )

        # ---- Not in position: check entry ----
        trend_result = self.trend_analyzer.analyze_trend(history_4h + [snap_4h])
        prev_15m = history_15m[-1] if history_15m else None
        cross_15m = detect_macd_cross(snap_15m, prev_15m, self.macd_name_15m)

        if trend_result.direction == TrendDirection.UPTREND and cross_15m.cross_type == MacdCrossType.GOLDEN:
            if trend_result.confidence >= 0.6:
                state[self.KEY_ENTRY_PRICE] = snap_15m.close
                state[self.KEY_POSITION_SIDE] = "long"
                return Signal(
                    action=SignalAction.BUY,
                    confidence=trend_result.confidence * 0.9,
                    reason="uptrend_15m_golden_cross",
                    metadata={
                        "trend": trend_result.reason,
                        "close": snap_15m.close,
                    },
                )

        if trend_result.direction == TrendDirection.DOWNTREND and cross_15m.cross_type == MacdCrossType.DEATH:
            if trend_result.confidence >= 0.6:
                state[self.KEY_ENTRY_PRICE] = snap_15m.close
                state[self.KEY_POSITION_SIDE] = "short"
                return Signal(
                    action=SignalAction.SELL,
                    confidence=trend_result.confidence * 0.9,
                    reason="downtrend_15m_death_cross",
                    metadata={
                        "trend": trend_result.reason,
                        "close": snap_15m.close,
                    },
                )

        return Signal(
            action=SignalAction.HOLD,
            confidence=0.0,
            reason="waiting_for_entry",
            metadata={
                "trend": trend_result.direction.value,
                "macd_cross": cross_15m.cross_type.value,
            },
        )

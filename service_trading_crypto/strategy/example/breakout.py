"""
Breakout strategy: 横盘 -> 突破 + 放量 -> 开仓 -> 止损/加仓.

Entry: consolidation -> breakout with volume spike -> BUY
Stop: breakout fails -> STOP_LOSS
Add: breakout succeeds, pullback to MA support -> ADD_POSITION
"""

import logging
from typing import Any, Dict, List

from service_trading_crypto.indicators import MarketSnapshot
from service_trading_crypto.strategy.example.interface.base import (
    BaseStrategy,
    Signal,
    SignalAction,
    StrategyContext,
)

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    """
    突破策略: 横盘一段时间后放量突破开仓，失败止损，成功则回调均线附近加仓.
    """

    # State keys (stored in context.state)
    KEY_ENTRY_PRICE = "entry_price"
    KEY_CONSOLIDATION_HIGH = "consolidation_high"
    KEY_CONSOLIDATION_LOW = "consolidation_low"
    KEY_PHASE = "phase"  # "idle" | "in_position" | "waiting_pullback"

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.consolidation_bars = int(self.config.get("consolidation_bars", 20))
        self.volume_spike_ratio = float(self.config.get("volume_spike_ratio", 2.0))
        self.ma_name = str(self.config.get("ma_name", "ma_20"))
        self.atr_name = str(self.config.get("atr_name", "atr_14"))
        self.volume_ma_name = str(self.config.get("volume_ma_name", "volume_sma_20"))
        self.stop_loss_pct = float(self.config.get("stop_loss_pct", 0.02))
        self.add_position_ma_tolerance_pct = float(
            self.config.get("add_position_ma_tolerance_pct", 0.005)
        )
        self.min_consolidation_range_pct = float(
            self.config.get("min_consolidation_range_pct", 0.01)
        )
        self.consolidation_max_range_pct = float(
            self.config.get("consolidation_max_range_pct", 0.03)
        )  # range/close < 3% = 横盘

    def evaluate(self, context: StrategyContext) -> Signal:
        snapshot = context.market_snapshot
        if snapshot is None:
            return Signal(action=SignalAction.HOLD, confidence=0.0, reason="no_snapshot", metadata={})
        history = context.market_snapshot_history
        state = context.state

        # Need enough history
        all_snapshots = list(history) + [snapshot]
        if len(all_snapshots) < self.consolidation_bars:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="insufficient_history",
                metadata={"count": len(all_snapshots), "required": self.consolidation_bars},
            )

        close = snapshot.close
        volume = snapshot.volume
        high = snapshot.high
        low = snapshot.low
        open_ = snapshot.open
        indicators = snapshot.indicators

        ma_val = indicators.get(self.ma_name)
        atr_val = indicators.get(self.atr_name)
        volume_ma_val = indicators.get(self.volume_ma_name)

        # 1. Compute consolidation range (横盘区间)
        lookback = all_snapshots[-self.consolidation_bars - 1 : -1]  # exclude current
        if not lookback:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="no_lookback",
                metadata={},
            )
        cons_high = max(s.high for s in lookback)
        cons_low = min(s.low for s in lookback)
        cons_range = cons_high - cons_low
        cons_range_pct = cons_range / close if close > 0 else 0

        # 2. Check if we're in position (from state, persisted across calls)
        entry_price = state.get(self.KEY_ENTRY_PRICE)
        in_position = entry_price is not None

        # ---- In position: check stop loss / add position ----
        if in_position and entry_price is not None:
            # Stop loss: 突破失败
            stop_price = entry_price * (1 - self.stop_loss_pct)
            if low <= stop_price or close < cons_low:
                state.pop(self.KEY_ENTRY_PRICE, None)
                state[self.KEY_PHASE] = "idle"
                return Signal(
                    action=SignalAction.STOP_LOSS,
                    confidence=1.0,
                    reason="breakout_failed_or_stop_loss",
                    metadata={
                        "entry_price": entry_price,
                        "stop_price": stop_price,
                        "close": close,
                    },
                )

            # Add position: 回调到均线附近有支撑
            if ma_val is not None and ma_val > 0:
                ma_tolerance = ma_val * self.add_position_ma_tolerance_pct
                near_ma = abs(close - ma_val) <= ma_tolerance
                bounced = close > open_  # 阳线
                if near_ma and bounced:
                    return Signal(
                        action=SignalAction.ADD_POSITION,
                        confidence=0.8,
                        reason="pullback_to_ma_support",
                        metadata={
                            "entry_price": entry_price,
                            "ma": ma_val,
                            "close": close,
                        },
                    )

            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="in_position_holding",
                metadata={"entry_price": entry_price},
            )

        # ---- Not in position: check entry ----
        # 横盘: 区间幅度小
        is_consolidation = (
            self.min_consolidation_range_pct
            <= cons_range_pct
            <= self.consolidation_max_range_pct
        )
        # 突破: 当前收盘突破区间上沿
        is_breakout = close > cons_high
        # 放量: 成交量显著放大
        volume_ok = volume_ma_val is not None and volume_ma_val > 0
        if volume_ok:
            volume_spike = volume >= volume_ma_val * self.volume_spike_ratio
        else:
            volume_spike = False

        if is_consolidation and is_breakout and volume_spike:
            state[self.KEY_ENTRY_PRICE] = close
            state[self.KEY_PHASE] = "in_position"
            return Signal(
                action=SignalAction.BUY,
                confidence=0.85,
                reason="breakout_with_volume_spike",
                metadata={
                    "consolidation_high": cons_high,
                    "consolidation_low": cons_low,
                    "close": close,
                    "volume": volume,
                    "volume_ma": volume_ma_val,
                },
            )

        return Signal(
            action=SignalAction.HOLD,
            confidence=0.0,
            reason="waiting_for_breakout",
            metadata={
                "is_consolidation": is_consolidation,
                "is_breakout": is_breakout,
                "volume_spike": volume_spike,
            },
        )

    def on_signal_executed(
        self, signal: Signal, context: StrategyContext, result: Dict[str, Any]
    ) -> None:
        """Update state after BUY/ADD_POSITION/STOP_LOSS executed."""
        if signal.action == SignalAction.BUY:
            context.state[self.KEY_ENTRY_PRICE] = context.market_snapshot.close
            context.state[self.KEY_PHASE] = "in_position"
        elif signal.action == SignalAction.ADD_POSITION:
            pass  # keep entry_price
        elif signal.action == SignalAction.STOP_LOSS:
            context.state.pop(self.KEY_ENTRY_PRICE, None)
            context.state[self.KEY_PHASE] = "idle"

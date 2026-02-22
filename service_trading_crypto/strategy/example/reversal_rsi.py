"""
反转 RSI 策略（3 分钟）：连续 4 根阴线后 RSI 金叉 + 当前阳线 -> 买入；
持仓后某 K 线收盘价触及 20 均线 -> 下一根开盘价卖出。
"""

from typing import Any, Dict, List

from service_trading_crypto.indicators import MarketSnapshot
from service_trading_crypto.strategy.data import Signal, SignalAction
from service_trading_crypto.strategy.example.interface.base import BaseStrategy, StrategyContext


def _is_bearish(s: MarketSnapshot) -> bool:
    return s.close < s.open


def _is_bullish(s: MarketSnapshot) -> bool:
    return s.close > s.open


class ReversalRSIStrategy(BaseStrategy):
    """
    监测 3 分钟 K 线（或 trigger channel）。
    入场：连续 4 根阴线 + RSI 金叉（由下穿上 30）+ 当前 K 线阳线 -> 买入。
    出场：持仓中某 K 线收盘价触及 20 均线 -> 下一根开盘价卖出（本根发出 SELL）。
    """

    RSI_OVERBOUGHT = 30  # RSI 金叉：由 < 30 上穿 30

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.rsi_name = str(self.config.get("rsi_name", "rsi_14"))
        self.ma_name = str(self.config.get("ma_name", "ma_20"))
        self.consecutive_bearish = int(self.config.get("consecutive_bearish", 4))
        self._in_position = False
        self._entry_price: float | None = None

    def evaluate(self, context: StrategyContext) -> Signal:
        snap = context.market_snapshot
        if snap is None:
            return Signal(action=SignalAction.HOLD, confidence=0.0, reason="no_snapshot", metadata={})
        history: List[MarketSnapshot] = list(context.market_snapshot_history)
        ind = snap.indicators
        rsi = ind.get(self.rsi_name)
        ma20 = ind.get(self.ma_name)

        # 持仓：检查是否触及 20 均线 -> 卖出
        if self._in_position and self._entry_price is not None:
            if ma20 is not None and snap.close <= ma20:
                self._in_position = False
                self._entry_price = None
                return Signal(
                    action=SignalAction.SELL,
                    confidence=0.8,
                    reason="close_touch_ma20_exit_next_open",
                    metadata={},
                )
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="in_position_holding",
                metadata={},
            )

        # 入场条件：至少 4 根历史 + 当前
        need = self.consecutive_bearish
        if len(history) < need:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="insufficient_history",
                metadata={"need": need, "have": len(history)},
            )
        last_n = history[-need:]
        if not all(_is_bearish(s) for s in last_n):
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="not_4_consecutive_bearish",
                metadata={},
            )
        if rsi is None or ma20 is None:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="missing_rsi_or_ma20",
                metadata={},
            )
        prev_rsi = last_n[-1].indicators.get(self.rsi_name)
        if prev_rsi is None:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="no_prev_rsi",
                metadata={},
            )
        # RSI 金叉：前一根 RSI < 30，当前 RSI >= 30
        if prev_rsi >= self.RSI_OVERBOUGHT or rsi < self.RSI_OVERBOUGHT:
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="no_rsi_golden_cross",
                metadata={"prev_rsi": prev_rsi, "rsi": rsi},
            )
        if not _is_bullish(snap):
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="current_not_bullish",
                metadata={},
            )
        self._in_position = True
        self._entry_price = snap.close
        return Signal(
            action=SignalAction.BUY,
            confidence=0.75,
            reason="reversal_rsi_4_bearish_then_golden_cross",
            metadata={"entry_price": self._entry_price},
        )

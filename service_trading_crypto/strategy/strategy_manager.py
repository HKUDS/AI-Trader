"""
StrategyManager: 根据 strategy_type 创建不同策略，从队列取 SnapshotProcessedV2，
由各策略在内部根据规则生成 Signal，并写入 output_queue。
策略注册表内置在 StrategyManager 中。
"""

import logging
import threading
from collections import deque
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Type

from service_trading_crypto.indicators import SnapshotProcessedV1, SnapshotProcessedV2
from service_trading_crypto.strategy.data import Signal, StrategyContext
from service_trading_crypto.strategy.example.breakout import BreakoutStrategy
from service_trading_crypto.strategy.example.hold_strategy import HoldStrategy
from service_trading_crypto.strategy.example.trend_macd import TrendMACDStrategy
from service_trading_crypto.strategy.example.reversal_rsi import ReversalRSIStrategy

logger = logging.getLogger(__name__)


class StrategyManager:
    """
    根据 strategy_type 创建策略；从 input_queue 取 SnapshotProcessedV2，
    构建 StrategyContext 后交给策略 evaluate(context)，策略内部按规则生成 Signal，
    将 signal.to_dict() 写入 output_queue。
    """

    _REGISTRY: Dict[str, Type[Any]] = {}

    @classmethod
    def _register_strategies(cls) -> None:
        if cls._REGISTRY:
            return
        cls._REGISTRY.update({
            "hold": HoldStrategy,
            "breakout": BreakoutStrategy,
            "trend_macd": TrendMACDStrategy,
            "reversal_rsi": ReversalRSIStrategy,
        })

    def _create_strategy(self, strategy_type: str, params: Dict[str, Any]) -> Any:
        """按 strategy_type 创建策略实例。"""
        StrategyManager._register_strategies()
        kind = (strategy_type or "hold").strip().lower()
        if kind not in self._REGISTRY:
            raise ValueError(f"Unknown strategy_type: {strategy_type}. Available: {list(self._REGISTRY.keys())}")
        return self._REGISTRY[kind](params)

    def __init__(
        self,
        input_queue: Queue,
        output_queue: Queue,
        strategy_type: str,
        strategy_params: Optional[Dict[str, Any]] = None,
        history_size: int = 100,
        trigger_timeframe: str = None,
    ) -> None:
        self._input_queue = input_queue
        self._output_queue = output_queue
        self._strategy_type = strategy_type or "hold"
        self._strategy = self._create_strategy(self._strategy_type, strategy_params or {})
        self._history_size = max(1, history_size)
        self._trigger_timeframe = trigger_timeframe  # 若为 None，从首条 v2 取

        # 有界 V1 历史（由旧到新），满时自动丢弃最旧
        self._snapshot_processed_v1_history: deque = deque(maxlen=self._history_size)
        self._state: Dict[str, Any] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _v2_to_context(self, v2: SnapshotProcessedV2, trigger_channel: str) -> StrategyContext:
        """从 SnapshotProcessedV2 及 V1 历史构建 StrategyContext。"""
        history_list: List[SnapshotProcessedV1] = list(self._snapshot_processed_v1_history)
        self._snapshot_processed_v1_history.append(v2.snapshot_processed_v1)
        return StrategyContext(
            trigger_channel=trigger_channel,
            snapshot_processed_v2=v2,
            snapshot_processed_v1_history=history_list,
            state=self._state,
        )

    def _run_loop(self) -> None:
        trigger_tf = self._trigger_timeframe
        while not self._stop.is_set():
            try:
                v2 = self._input_queue.get(timeout=0.5)
            except Empty:
                continue
            if not isinstance(v2, SnapshotProcessedV2):
                continue
            if trigger_tf is None and v2.snapshot_processed_v1.compose_snapshot:
                trigger_tf = next(reversed(v2.snapshot_processed_v1.compose_snapshot))
                self._trigger_timeframe = trigger_tf
            try:
                context = self._v2_to_context(v2, trigger_tf)
                signal: Signal = self._strategy.evaluate(context)
                out = signal.to_dict()
                snap = context.market_snapshot
                out["snapshot_ts"] = snap.ts if snap else v2.snapshot_processed_v1.ts
                self._output_queue.put_nowait(out)
            except Exception as e:
                logger.exception("StrategyManager strategy.evaluate error: %s", e)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("StrategyManager started strategy_type=%s", self._strategy_type)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("StrategyManager stopped")

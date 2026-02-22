"""Pipeline: main 入口调用的编排层。仅负责按 config 创建各模块 Manager 并串联队列。"""

import logging
from queue import Queue

from service_trading_crypto.agent import AgentManager
from service_trading_crypto.config import ServiceConfig
from service_trading_crypto.indicators import IndicatorManager
from service_trading_crypto.strategy import StrategyManager
from service_trading_crypto.websocket.ws_client_okx import OkxWsClient

logger = logging.getLogger(__name__)


class Pipeline:
    """
    编排层：除 websocket 外，各模块以 Manager 为入口。
    - IndicatorManager：生成指标，产出 SnapshotProcessedV1
    - AgentManager：产出 SnapshotProcessedV2 写入 v2 队列（当前为 default）
    - StrategyManager：按 strategy_type 创建策略，从 v2 队列取 SnapshotProcessedV2，
      各策略内部按规则生成 Signal，写入 signal_queue
    """

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.snapshot_queue: Queue = Queue(maxsize=10000)
        self.snapshot_processed_v1_queue: Queue = Queue(maxsize=1000)
        self.snapshot_processed_v2_queue: Queue = Queue(maxsize=1000)
        self.signal_queue: Queue = Queue(maxsize=1000)
        self._ws: OkxWsClient = None
        self._indicator_manager: IndicatorManager = None
        self._agent_manager: AgentManager = None
        self._strategy_manager: StrategyManager = None

    def start(self) -> None:
        okx = self.config.okx
        channels = okx.channels if okx.channels else [okx.channel]
        trigger_ch = channels[0] if len(channels) == 1 else channels[-1]

        self._ws = OkxWsClient(
            url=okx.url,
            symbol=okx.symbol,
            channels=channels,
            output_queue=self.snapshot_queue,
            ping_interval=okx.ping_interval,
            reconnect_delay=okx.reconnect_delay,
        )
        self._indicator_manager = IndicatorManager(
            channels=channels,
            input_queue=self.snapshot_queue,
            output_queue=self.snapshot_processed_v1_queue,
            trigger_channel=trigger_ch,
            max_candle_buffer=self.config.max_candle_buffer,
        )

        sc = self.config.strategy
        self._strategy_manager = StrategyManager(
            input_queue=self.snapshot_processed_v2_queue,
            output_queue=self.signal_queue,
            strategy_type=sc.strategy_type or "hold",
            strategy_params=sc.strategy_params,
            history_size=sc.history_size,
            trigger_timeframe=trigger_ch,
        )

        agent_cfg = self.config.agent
        self._agent_manager = AgentManager(
            input_queue=self.snapshot_processed_v1_queue,
            output_queue=self.snapshot_processed_v2_queue,
            agent_type="default",
            symbol=okx.symbol,
            trigger_interval_seconds=agent_cfg.trigger_interval_seconds,
            trigger_on_candle=agent_cfg.trigger_on_candle,
        )
        self._agent_manager.start()
        
        self._ws.start()
        self._indicator_manager.start()
        self._strategy_manager.start()
        logger.info("Pipeline started: %s %s", okx.symbol, channels)

    def stop(self) -> None:
        if self._strategy_manager is not None:
            self._strategy_manager.stop()
            self._strategy_manager = None
        if self._agent_manager is not None:
            self._agent_manager.stop()
            self._agent_manager = None
        if self._indicator_manager is not None:
            self._indicator_manager.stop()
            self._indicator_manager = None
        if self._ws is not None:
            self._ws.stop()
            self._ws = None
        logger.info("Pipeline stopped")

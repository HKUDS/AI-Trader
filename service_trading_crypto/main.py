#!/usr/bin/env python3
"""
入口：main 启动后由 Pipeline 按 config 串联各模块 Manager。
- 除 websocket 外，每模块以 Manager 为入口：IndicatorManager / AgentManager / StrategyManager
- Manager 负责选择不同 agent、策略及生成指标
"""

import logging
import signal
import sys
import time
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from service_trading_crypto.config import ServiceConfig
from service_trading_crypto import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = SERVICE_DIR / "config" / "json" / "trend_macd.json"


def main() -> None:
    if not CONFIG_PATH.exists():
        logger.error("Config file not found: %s", CONFIG_PATH)
        return
    config = ServiceConfig.from_json_file(CONFIG_PATH)
    pipeline = Pipeline(config)
    logger.info("strategy=%s", config.strategy.strategy_type or "hold")

    def on_stop(*_args: object) -> None:
        pipeline.stop()

    signal.signal(signal.SIGINT, on_stop)
    signal.signal(signal.SIGTERM, on_stop)
    pipeline.start()
    logger.info("Running. Ctrl+C to stop.")
    try:
        while True:
            signal.pause()
    except AttributeError:
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
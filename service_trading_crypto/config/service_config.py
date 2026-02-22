"""Config: okx、consumer 触发间隔、max_candle_buffer、strategy。指标在 IndicatorManager 内固定为 example 下全部。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import json


@dataclass
class OkxWsConfig:
    """OKX WebSocket connection and subscription."""

    url: str = "wss://wspri.coinall.ltd:8443/ws/v5/public"
    symbol: str = "BTC-USDT"
    channel: str = "candle1m"
    channels: List[str] | None = None  # Multi-timeframe: ["candle4H", "candle15m"]
    ping_interval: float = 25.0
    reconnect_delay: float = 5.0


@dataclass
class AgentRunnerConfig:
    """Consumer 触发节奏（何时调用 handler）。"""

    trigger_interval_seconds: float = 60.0
    trigger_on_candle: bool = False


@dataclass
class StrategyConfig:
    """策略配置：Pipeline 用于直接创建 StrategyManager。"""

    strategy_type: str | None = None  # "breakout" | "trend_macd" | None 表示 hold
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    history_size: int = 100


@dataclass
class ServiceConfig:
    """Full service config (pipeline: okx, trigger, strategy).指标在 IndicatorManager 内固定为 example 下全部。"""

    okx: OkxWsConfig = field(default_factory=OkxWsConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    agent: AgentRunnerConfig = field(default_factory=AgentRunnerConfig)
    max_candle_buffer: int = 500

    @classmethod
    def from_json_file(cls, path: str | Path) -> "ServiceConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceConfig":
        okx_data = data.get("okx", {})
        okx = OkxWsConfig(
            url=okx_data.get("url", OkxWsConfig.url),
            symbol=okx_data.get("symbol", OkxWsConfig.symbol),
            channel=okx_data.get("channel", OkxWsConfig.channel),
            channels=okx_data.get("channels"),
            ping_interval=okx_data.get("ping_interval", OkxWsConfig.ping_interval),
            reconnect_delay=okx_data.get("reconnect_delay", OkxWsConfig.reconnect_delay),
        )
        agent_data = data.get("agent", {})
        agent = AgentRunnerConfig(
            trigger_interval_seconds=agent_data.get("trigger_interval_seconds", 60.0),
            trigger_on_candle=agent_data.get("trigger_on_candle", False),
        )
        strategy_data = data.get("strategy", {})
        strategy = StrategyConfig(
            strategy_type=strategy_data.get("strategy_type"),
            strategy_params=strategy_data.get("strategy_params") or {},
            history_size=strategy_data.get("history_size", 100),
        )
        return cls(
            okx=okx,
            strategy=strategy,
            agent=agent,
            max_candle_buffer=data.get("max_candle_buffer", 500),
        )

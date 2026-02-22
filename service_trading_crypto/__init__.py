"""
Crypto Trading Service (service_trading_crypto).

Standalone service: WebSocket OKX data stream -> indicator computation -> agent decision.
Uses shared components: agent (LLM + MCP tools).

各模块以 Manager 为入口（除 websocket）:
  config/     - ServiceConfig
  websocket/  - OkxWsClient（无 Manager）
  indicators/ - IndicatorManager 生成指标
  strategy/   - StrategyManager 选择策略
  agent/      - AgentManager (选择 agent)
  pipeline.py - Pipeline 串联各 Manager
"""

from service_trading_crypto.config import ServiceConfig
from service_trading_crypto.pipeline import Pipeline

__all__ = ["Pipeline", "ServiceConfig"]

"""Pluggable technical indicators + IndicatorManager（初始化时注册所有指标）, MarketSnapshot, SnapshotProcessedV1。"""

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike
from service_trading_crypto.indicators.example.ma import EMAIndicator, SMAIndicator
from service_trading_crypto.indicators.example.macd import MACDIndicator
from service_trading_crypto.indicators.example.atr import ATRIndicator
from service_trading_crypto.indicators.example.volume import VolumeSMAIndicator
from service_trading_crypto.indicators.indicator_manager import IndicatorManager
from service_trading_crypto.indicators.data import (
    MarketSnapshot,
    SnapshotProcessedV1,
    SnapshotProcessedV2,
)

__all__ = [
    "BaseIndicator",
    "CandleLike",
    "SMAIndicator",
    "EMAIndicator",
    "MACDIndicator",
    "ATRIndicator",
    "VolumeSMAIndicator",
    "IndicatorManager",
    "MarketSnapshot",
    "SnapshotProcessedV1",
    "SnapshotProcessedV2",
]

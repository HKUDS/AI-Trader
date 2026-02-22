"""Example indicator set: base, MA, MACD, ATR, volume. MACD cross in macd_cross module (avoids circular import with strategy/processor)."""

from service_trading_crypto.indicators.example.base import BaseIndicator, CandleLike
from service_trading_crypto.indicators.example.ma import EMAIndicator, SMAIndicator
from service_trading_crypto.indicators.example.macd import MACDIndicator
from service_trading_crypto.indicators.example.atr import ATRIndicator
from service_trading_crypto.indicators.example.volume import VolumeSMAIndicator
from service_trading_crypto.indicators.example.rsi import RSIIndicator

__all__ = [
    "BaseIndicator",
    "CandleLike",
    "SMAIndicator",
    "EMAIndicator",
    "MACDIndicator",
    "ATRIndicator",
    "VolumeSMAIndicator",
    "RSIIndicator",
]

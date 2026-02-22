"""MACD cross detection: golden cross (金叉) and death cross (死叉)."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from service_trading_crypto.indicators import MarketSnapshot


class MacdCrossType(Enum):
    """MACD cross type."""

    GOLDEN = "golden"   # MACD 上穿 signal → 金叉，偏多
    DEATH = "death"     # MACD 下穿 signal → 死叉，偏空
    NONE = "none"


@dataclass
class MacdCrossResult:
    """Result of MACD cross detection."""

    cross_type: MacdCrossType
    macd: Optional[float]
    signal: Optional[float]
    histogram: Optional[float]


def detect_macd_cross(
    snapshot: MarketSnapshot,
    prev_snapshot: Optional[MarketSnapshot],
    macd_name: str = "macd",
) -> MacdCrossResult:
    """
    Detect MACD golden cross or death cross.
    Golden: MACD was below signal, now above.
    Death: MACD was above signal, now below.

    Requires macd_<name>_macd and macd_<name>_signal in indicators.
    """
    indicators = snapshot.indicators
    macd_key = f"{macd_name}_macd"
    signal_key = f"{macd_name}_signal"
    hist_key = f"{macd_name}_histogram"

    macd = indicators.get(macd_key)
    signal_val = indicators.get(signal_key)
    hist = indicators.get(hist_key)

    if macd is None or signal_val is None:
        return MacdCrossResult(
            cross_type=MacdCrossType.NONE,
            macd=macd,
            signal=signal_val,
            histogram=hist,
        )

    if prev_snapshot is None:
        return MacdCrossResult(
            cross_type=MacdCrossType.NONE,
            macd=macd,
            signal=signal_val,
            histogram=hist,
        )

    prev_ind = prev_snapshot.indicators
    prev_macd = prev_ind.get(macd_key)
    prev_signal = prev_ind.get(signal_key)

    if prev_macd is None or prev_signal is None:
        return MacdCrossResult(
            cross_type=MacdCrossType.NONE,
            macd=macd,
            signal=signal_val,
            histogram=hist,
        )

    prev_above = prev_macd > prev_signal
    curr_above = macd > signal_val

    if not prev_above and curr_above:
        return MacdCrossResult(
            cross_type=MacdCrossType.GOLDEN,
            macd=macd,
            signal=signal_val,
            histogram=hist,
        )
    if prev_above and not curr_above:
        return MacdCrossResult(
            cross_type=MacdCrossType.DEATH,
            macd=macd,
            signal=signal_val,
            histogram=hist,
        )

    return MacdCrossResult(
        cross_type=MacdCrossType.NONE,
        macd=macd,
        signal=signal_val,
        histogram=hist,
    )

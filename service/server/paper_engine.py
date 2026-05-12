"""Paper-trading fill engine with Taiwan market microstructure rules.

Pure functions only — no DB, no network. The trading routes call into this
module to check whether a hypothetical fill is legal *before* writing the
position to the database. Keeping the rules pure makes them cheap to unit-
test and means a future Phase 3 broker integration can reuse the same
validators against pre-trade quotes from a real venue.

Rules implemented:
  - TW common stock round-lot is 1,000 shares; partial lots are rejected
    as INVALID_LOT_SIZE (the system does not yet model 盤中零股).
  - TW daily price limit is ±10% of the previous close. A submitted price
    outside the band is rejected as PRICE_OUTSIDE_DAILY_LIMIT.
  - TWSE regular session is 09:00–13:30 Asia/Taipei, Monday through Friday,
    excluding TWSE-published holidays.

The session check intentionally allows for the *queued-to-open* mode: when
the market is closed, `evaluate_fill` returns a `Decision` with status
`queue_for_open` and an `effective_at` timestamp the scheduler can fire on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import config

TPE = ZoneInfo("Asia/Taipei")


# TWSE-published holidays. The list is intentionally hand-curated because the
# TWSE calendar JSON requires per-year fetch and ops would rather flip a date
# constant than ship a network dependency in the fill engine. Update when
# 證交所 公布隔年行事曆 (typically Q4).
TW_HOLIDAYS_2025: frozenset[date] = frozenset(
    {
        date(2025, 1, 1),
        # Lunar New Year cluster
        date(2025, 1, 27),
        date(2025, 1, 28),
        date(2025, 1, 29),
        date(2025, 1, 30),
        date(2025, 1, 31),
        date(2025, 2, 28),  # 228 紀念日
        date(2025, 4, 3),
        date(2025, 4, 4),  # 兒童節 / 清明
        date(2025, 5, 1),  # 勞動節
        date(2025, 5, 30),
        date(2025, 6, 30),
        date(2025, 9, 29),  # 中秋 連假
        date(2025, 10, 10),  # 國慶
    }
)
TW_HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 2, 16),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 2, 20),
        date(2026, 2, 27),
        date(2026, 4, 3),
        date(2026, 4, 6),
        date(2026, 5, 1),
        date(2026, 6, 19),
        date(2026, 9, 25),
        date(2026, 10, 9),
    }
)

TW_HOLIDAYS: frozenset[date] = TW_HOLIDAYS_2025 | TW_HOLIDAYS_2026


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def is_tw_trading_day(d: date) -> bool:
    """True iff `d` is a Mon-Fri weekday and not on the TWSE holiday list."""
    if d.weekday() >= 5:
        return False
    return d not in TW_HOLIDAYS


def next_tw_trading_day(d: date) -> date:
    """The next trading day strictly after `d`."""
    candidate = d + timedelta(days=1)
    # Cap the loop — in normal calendars we'd never need more than 5 forward
    # steps (long-weekend + holiday cluster), but 14 is a safe upper bound
    # if a future year config goes wrong.
    for _ in range(14):
        if is_tw_trading_day(candidate):
            return candidate
        candidate = candidate + timedelta(days=1)
    return candidate  # pragma: no cover — only reached if holiday list malformed


def is_tw_session_open(now: Optional[datetime] = None) -> bool:
    """True iff `now` is inside the TWSE 09:00–13:30 regular session.

    Accepts a naïve datetime (assumed Taipei) or a tz-aware datetime in any
    zone. Defaults to current Taipei time.
    """
    now_tpe = (now or datetime.now(TPE)).astimezone(TPE)
    if not is_tw_trading_day(now_tpe.date()):
        return False
    open_t = _parse_hhmm(config.TW_SESSION_OPEN_HHMM)
    close_t = _parse_hhmm(config.TW_SESSION_CLOSE_HHMM)
    return open_t <= now_tpe.time() < close_t


def next_tw_open(now: Optional[datetime] = None) -> datetime:
    """Return the next 09:00 Asia/Taipei trading-session open at-or-after now.

    Used by the queue-for-open fill path: when a trader pushes an order
    pre-market or after-hours, the engine reports when the order would
    activate.
    """
    now_tpe = (now or datetime.now(TPE)).astimezone(TPE)
    open_t = _parse_hhmm(config.TW_SESSION_OPEN_HHMM)
    close_t = _parse_hhmm(config.TW_SESSION_CLOSE_HHMM)
    candidate = now_tpe.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
    # If today is a trading day AND we are still before close, use today's open
    # (which may be in the past — caller treats "open == now or earlier" as
    # immediate-fill eligibility).
    if is_tw_trading_day(now_tpe.date()) and now_tpe.time() < close_t:
        return candidate
    # Otherwise advance to the next trading day's open.
    next_day = next_tw_trading_day(now_tpe.date())
    return datetime.combine(next_day, open_t, tzinfo=TPE)


@dataclass(frozen=True)
class Decision:
    """The result of a pre-fill check.

    `status`:
      - "fill"            → submit immediately
      - "queue_for_open"  → store in the open queue, fire when `effective_at`
                            is reached
      - "reject"          → return 400 to the caller with `reason`
    """

    status: str
    reason: Optional[str] = None
    effective_at: Optional[datetime] = None
    notes: tuple[str, ...] = field(default_factory=tuple)


REJECT_INVALID_LOT_SIZE = "INVALID_LOT_SIZE"
REJECT_PRICE_OUTSIDE_DAILY_LIMIT = "PRICE_OUTSIDE_DAILY_LIMIT"
REJECT_NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"


def validate_lot_size(quantity: float, market: str) -> Optional[str]:
    """Return a rejection reason or None.

    TW common stock orders must be whole multiples of the round-lot
    (default 1,000 shares). Non-TW markets bypass the check.
    """
    if market != "tw-stock":
        return None
    if quantity <= 0:
        return REJECT_NON_POSITIVE_QUANTITY
    lot = config.TW_ROUND_LOT_SHARES
    if lot <= 0:
        return None  # pragma: no cover — defensive
    # Use modulo on integer quantities; reject fractional shares outright.
    if quantity != int(quantity):
        return REJECT_INVALID_LOT_SIZE
    if int(quantity) % lot != 0:
        return REJECT_INVALID_LOT_SIZE
    return None


def validate_price_band(
    price: float,
    previous_close: Optional[float],
    market: str,
) -> Optional[str]:
    """Return a rejection reason or None for the TW ±10% daily band.

    A None `previous_close` (e.g. brand new listing, or the price-fetcher
    couldn't resolve yesterday's close) is treated as "skip the check" —
    the alternative would be to reject every IPO day, which is worse for
    paper-trading UX. The TW news + research path can surface the missing
    reference price separately.
    """
    if market != "tw-stock":
        return None
    if previous_close is None or previous_close <= 0:
        return None
    limit_pct = config.TW_DAILY_PRICE_LIMIT_PCT
    upper = previous_close * (1 + limit_pct)
    lower = previous_close * (1 - limit_pct)
    if price > upper or price < lower:
        return REJECT_PRICE_OUTSIDE_DAILY_LIMIT
    return None


def evaluate_fill(
    *,
    market: str,
    quantity: float,
    price: float,
    previous_close: Optional[float],
    now: Optional[datetime] = None,
) -> Decision:
    """Decide whether a paper order can fill, queue, or must reject.

    The function is intentionally single-purpose and does no I/O. Routes
    that need the verdict should call this and dispatch on `Decision.status`.
    """
    lot_err = validate_lot_size(quantity, market)
    if lot_err:
        return Decision(status="reject", reason=lot_err)

    price_err = validate_price_band(price, previous_close, market)
    if price_err:
        return Decision(status="reject", reason=price_err)

    if market != "tw-stock":
        return Decision(status="fill")

    if is_tw_session_open(now):
        return Decision(status="fill")

    return Decision(
        status="queue_for_open",
        effective_at=next_tw_open(now),
        notes=("tw_market_closed",),
    )


# ==================== Portfolio analytics ====================
#
# The leaderboard already shows raw profit. These helpers compute the
# slightly richer metrics Brian asked for: cumulative return, monthly
# win rate, maximum drawdown, and a coarse Sharpe ratio. They run on
# in-memory series so a future caller can read profit_history rows
# straight out of the DB and pass them in.


def cumulative_return(profit_series: list[float], starting_capital: float) -> float:
    """Last-value cumulative return as a percentage of starting capital."""
    if starting_capital <= 0 or not profit_series:
        return 0.0
    return profit_series[-1] / starting_capital * 100.0


def monthly_win_rate(monthly_profits: list[float]) -> float:
    """Fraction of months with non-negative P&L, in [0, 1].

    A month with exactly zero P&L is counted as a win (typical conservative
    framing for retail dashboards — zero days outnumber loss days only when
    the trader actually traded).
    """
    if not monthly_profits:
        return 0.0
    wins = sum(1 for p in monthly_profits if p >= 0)
    return wins / len(monthly_profits)


def max_drawdown(equity_curve: list[float]) -> float:
    """Worst peak-to-trough drop on the equity curve, as a positive fraction.

    Returns 0.0 for an empty / single-point series or a strictly increasing
    one. Drawdown is computed against the running maximum.
    """
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak <= 0:
            continue
        drop = (peak - value) / peak
        if drop > worst:
            worst = drop
    return worst


def coarse_sharpe(daily_returns: list[float], risk_free_daily: float = 0.0) -> float:
    """Annualised Sharpe ratio from a daily-return series.

    Coarse: assumes 252 trading days, no rolling-window correction. Good
    enough for a paper-trading dashboard, not for actual portfolio
    management. Returns 0.0 when stdev is zero or the series is too short.
    """
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - risk_free_daily for r in daily_returns]
    mean = sum(excess) / len(excess)
    variance = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
    if variance <= 0:
        return 0.0
    stdev = variance ** 0.5
    return (mean / stdev) * (252 ** 0.5)

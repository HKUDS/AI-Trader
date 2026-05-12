"""TW-market-aware scheduler loops.

The existing `tasks.py` registers fixed-interval async loops (5-min news
refresh, 10-min macro snapshots, etc.). Those work fine for always-on
markets like crypto. The TW path needs three additional cadences that are
keyed to the Asia/Taipei session and the TWSE holiday calendar:

  1. Pre-open research pull (08:30 TPE) — kick the last30days research
     skill across a watchlist of popular TW symbols so the morning UI is
     warm and the cache is populated when traders log in at 09:00.
  2. Intraday price tick (every 5 minutes, 09:00–13:30 TPE on trading
     days) — refresh prices for symbols that have open paper positions.
  3. Daily settlement (13:35 TPE) — write today's P&L snapshot to
     `profit_history` and recompute the leaderboard caches.

These loops are intentionally cooperative with the existing background
runtime: they live in their own module so `worker.py` can opt them in or
out without forking `tasks.py`. The default behaviour is "wait until the
next scheduled instant, run, sleep again" — no in-process cron, so
restarting the worker doesn't lose a window.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Iterable, Optional

from paper_engine import TPE, is_tw_trading_day, next_tw_trading_day

logger = logging.getLogger(__name__)


# Default TW watchlist for the pre-open research sweep. Curated to the
# usual retail-heavy weights — TSMC, 0050 ETF, Hon Hai, etc. Operators
# can override via TW_RESEARCH_WATCHLIST=2330,2317,...
DEFAULT_TW_WATCHLIST = (
    "2330",  # TSMC
    "2317",  # Hon Hai
    "0050",  # 元大台灣50
    "0056",  # 元大高股息
    "2454",  # MediaTek
    "2308",  # Delta Electronics
    "2412",  # 中華電
    "2881",  # 富邦金
)


def get_tw_watchlist() -> tuple[str, ...]:
    raw = os.environ.get("TW_RESEARCH_WATCHLIST", "")
    if not raw.strip():
        return DEFAULT_TW_WATCHLIST
    return tuple(item.strip() for item in raw.split(",") if item.strip())


# ---- Time helpers (deterministic, no I/O) ----------------------------------


def _today_at(hh: int, mm: int, now: Optional[datetime] = None) -> datetime:
    """Today's HH:MM in Asia/Taipei."""
    now_tpe = (now or datetime.now(TPE)).astimezone(TPE)
    return now_tpe.replace(hour=hh, minute=mm, second=0, microsecond=0)


def next_pre_open_pull(now: Optional[datetime] = None) -> datetime:
    """Next 08:30 Asia/Taipei on a trading day."""
    now_tpe = (now or datetime.now(TPE)).astimezone(TPE)
    candidate = _today_at(8, 30, now_tpe)
    if is_tw_trading_day(now_tpe.date()) and now_tpe < candidate:
        return candidate
    return datetime.combine(next_tw_trading_day(now_tpe.date()), candidate.timetz())


def next_daily_settlement(now: Optional[datetime] = None) -> datetime:
    """Next 13:35 Asia/Taipei on a trading day (5 minutes after close)."""
    now_tpe = (now or datetime.now(TPE)).astimezone(TPE)
    candidate = _today_at(13, 35, now_tpe)
    if is_tw_trading_day(now_tpe.date()) and now_tpe < candidate:
        return candidate
    return datetime.combine(next_tw_trading_day(now_tpe.date()), candidate.timetz())


def next_intraday_tick(now: Optional[datetime] = None, *, interval_minutes: int = 5) -> datetime:
    """Next aligned-to-clock 5-minute mark inside the TW session window.

    If we're outside the session, returns the next 09:00 open (caller will
    sleep until then and start the intraday cadence fresh).
    """
    now_tpe = (now or datetime.now(TPE)).astimezone(TPE)
    open_t = _today_at(9, 0, now_tpe)
    close_t = _today_at(13, 30, now_tpe)
    if not is_tw_trading_day(now_tpe.date()) or now_tpe < open_t:
        # Either weekend, holiday, or pre-open. Sleep until today's (or the
        # next trading day's) open.
        if is_tw_trading_day(now_tpe.date()):
            return open_t
        return datetime.combine(next_tw_trading_day(now_tpe.date()), open_t.timetz())
    if now_tpe >= close_t:
        return datetime.combine(next_tw_trading_day(now_tpe.date()), open_t.timetz())
    # Round up to the next interval boundary.
    minute_floor = (now_tpe.minute // interval_minutes) * interval_minutes
    target = now_tpe.replace(minute=minute_floor, second=0, microsecond=0) + timedelta(
        minutes=interval_minutes
    )
    if target > close_t:
        return datetime.combine(next_tw_trading_day(now_tpe.date()), open_t.timetz())
    return target


async def _sleep_until(target: datetime) -> None:
    delta = (target - datetime.now(TPE)).total_seconds()
    if delta > 0:
        await asyncio.sleep(delta)


# ---- The loops themselves --------------------------------------------------
#
# Each loop is shaped so a test can replace `_sleep_until` (via the
# `sleeper` argument) and `now_provider` to exercise the schedule
# without waiting wall-clock minutes. Production wiring calls the public
# `loop()` form, which uses the defaults.


async def tw_pre_open_research_loop(
    *,
    sleeper: Callable[[datetime], Awaitable[None]] = _sleep_until,
    now_provider: Callable[[], datetime] = lambda: datetime.now(TPE),
    iterations: Optional[int] = None,
) -> None:
    """Run a research pull for the watchlist 30 minutes before TW open."""
    from research import is_backend_available, research

    count = 0
    while True:
        target = next_pre_open_pull(now_provider())
        logger.info("tw_pre_open_research_loop: sleeping until %s", target.isoformat())
        await sleeper(target)
        if is_backend_available():
            for symbol in get_tw_watchlist():
                topic = f"台股 {symbol} 投資人討論 最近 30 天"
                try:
                    result = research(topic=topic)
                    logger.info(
                        "tw_pre_open_research[%s]: status=%s sources=%d",
                        symbol,
                        result.status,
                        len(result.sources),
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning("tw_pre_open_research[%s] failed: %s", symbol, exc)
        else:
            logger.info("tw_pre_open_research_loop: last30days unavailable, skipping")
        count += 1
        if iterations is not None and count >= iterations:
            return


async def tw_intraday_price_loop(
    *,
    refresh_fn: Optional[Callable[[], Awaitable[None]]] = None,
    sleeper: Callable[[datetime], Awaitable[None]] = _sleep_until,
    now_provider: Callable[[], datetime] = lambda: datetime.now(TPE),
    iterations: Optional[int] = None,
) -> None:
    """Refresh prices for open positions every 5 minutes during the session."""
    if refresh_fn is None:
        from tasks import update_position_prices

        refresh_fn = update_position_prices

    count = 0
    while True:
        target = next_intraday_tick(now_provider())
        await sleeper(target)
        try:
            await refresh_fn()
        except Exception as exc:
            logger.warning("tw_intraday_price_loop refresh failed: %s", exc)
        count += 1
        if iterations is not None and count >= iterations:
            return


async def tw_daily_settlement_loop(
    *,
    settle_fn: Optional[Callable[[], Awaitable[None]]] = None,
    sleeper: Callable[[datetime], Awaitable[None]] = _sleep_until,
    now_provider: Callable[[], datetime] = lambda: datetime.now(TPE),
    iterations: Optional[int] = None,
) -> None:
    """Run the paper-portfolio settlement at 13:35 Asia/Taipei."""
    if settle_fn is None:
        from tasks import record_profit_history

        settle_fn = record_profit_history

    count = 0
    while True:
        target = next_daily_settlement(now_provider())
        await sleeper(target)
        try:
            await settle_fn()
        except Exception as exc:
            logger.warning("tw_daily_settlement_loop failed: %s", exc)
        count += 1
        if iterations is not None and count >= iterations:
            return


# Registry used by worker.py to opt in. Operators flip these via
# AI_TRADER_BACKGROUND_TASKS=tw_pre_open_research,tw_intraday_prices,tw_daily_settlement
TW_SCHEDULER_REGISTRY: dict[str, Callable[..., Awaitable[None]]] = {
    "tw_pre_open_research": tw_pre_open_research_loop,
    "tw_intraday_prices": tw_intraday_price_loop,
    "tw_daily_settlement": tw_daily_settlement_loop,
}

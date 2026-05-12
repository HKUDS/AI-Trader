"""Tests for the TW-market-aware scheduler.

The scheduler is split into pure time-helpers (deterministic) and async
loops that take a `sleeper` and `now_provider` for injection. Tests
exercise the schedule arithmetic directly and run the loops with a fake
sleeper that records target times instead of waiting.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import scheduler
from paper_engine import TPE


class TimeArithmeticTests(unittest.TestCase):
    def test_pre_open_pull_before_target_returns_today(self) -> None:
        # 2025-05-12 (Mon) at 07:00 — pre-open target is today 08:30.
        now = datetime(2025, 5, 12, 7, 0, tzinfo=TPE)
        result = scheduler.next_pre_open_pull(now)
        self.assertEqual(result, datetime(2025, 5, 12, 8, 30, tzinfo=TPE))

    def test_pre_open_pull_after_target_advances_to_next_day(self) -> None:
        # 2025-05-12 (Mon) at 10:00 — past today's 08:30, next Tue.
        now = datetime(2025, 5, 12, 10, 0, tzinfo=TPE)
        result = scheduler.next_pre_open_pull(now)
        self.assertEqual(result.date(), date(2025, 5, 13))
        self.assertEqual(result.hour, 8)
        self.assertEqual(result.minute, 30)

    def test_pre_open_pull_skips_weekend(self) -> None:
        # 2025-05-10 (Sat) → next is Mon 2025-05-12.
        now = datetime(2025, 5, 10, 7, 0, tzinfo=TPE)
        result = scheduler.next_pre_open_pull(now)
        self.assertEqual(result.date(), date(2025, 5, 12))

    def test_pre_open_pull_skips_holiday(self) -> None:
        # 2025-10-09 (Thu) at 22:00 → next is Mon 2025-10-13 (10/10 is 國慶).
        now = datetime(2025, 10, 9, 22, 0, tzinfo=TPE)
        result = scheduler.next_pre_open_pull(now)
        self.assertEqual(result.date(), date(2025, 10, 13))

    def test_daily_settlement_at_1335(self) -> None:
        now = datetime(2025, 5, 12, 12, 0, tzinfo=TPE)
        result = scheduler.next_daily_settlement(now)
        self.assertEqual(result, datetime(2025, 5, 12, 13, 35, tzinfo=TPE))

    def test_daily_settlement_post_market_advances(self) -> None:
        now = datetime(2025, 5, 12, 15, 0, tzinfo=TPE)
        result = scheduler.next_daily_settlement(now)
        self.assertEqual(result.date(), date(2025, 5, 13))

    def test_intraday_tick_aligns_to_next_5_minute(self) -> None:
        # 2025-05-12 (Mon) at 10:07 → next is 10:10.
        now = datetime(2025, 5, 12, 10, 7, tzinfo=TPE)
        result = scheduler.next_intraday_tick(now, interval_minutes=5)
        self.assertEqual(result.minute, 10)
        self.assertEqual(result.hour, 10)

    def test_intraday_tick_pre_market_returns_open(self) -> None:
        now = datetime(2025, 5, 12, 8, 0, tzinfo=TPE)
        result = scheduler.next_intraday_tick(now)
        self.assertEqual(result, datetime(2025, 5, 12, 9, 0, tzinfo=TPE))

    def test_intraday_tick_after_close_advances_to_next_day_open(self) -> None:
        now = datetime(2025, 5, 12, 14, 0, tzinfo=TPE)
        result = scheduler.next_intraday_tick(now)
        self.assertEqual(result.date(), date(2025, 5, 13))
        self.assertEqual(result.hour, 9)

    def test_intraday_tick_skips_weekend(self) -> None:
        now = datetime(2025, 5, 10, 10, 0, tzinfo=TPE)  # Sat
        result = scheduler.next_intraday_tick(now)
        self.assertEqual(result.date(), date(2025, 5, 12))


class WatchlistTests(unittest.TestCase):
    def test_default_watchlist_includes_tsmc(self) -> None:
        self.assertIn("2330", scheduler.get_tw_watchlist())

    def test_env_override_replaces_watchlist(self) -> None:
        with patch.dict("os.environ", {"TW_RESEARCH_WATCHLIST": "2330, 2317,  2454 "}):
            result = scheduler.get_tw_watchlist()
            self.assertEqual(result, ("2330", "2317", "2454"))

    def test_empty_env_falls_back_to_default(self) -> None:
        with patch.dict("os.environ", {"TW_RESEARCH_WATCHLIST": "   "}):
            result = scheduler.get_tw_watchlist()
            self.assertEqual(result, scheduler.DEFAULT_TW_WATCHLIST)


class LoopExecutionTests(unittest.TestCase):
    """End-to-end loop run with injected sleeper + now_provider.

    The fake sleeper records the target instants the loop wanted to fire on,
    and we cap iterations so the loop terminates after a deterministic
    number of cycles.
    """

    def test_intraday_loop_calls_refresh_each_iteration(self) -> None:
        call_count = {"n": 0}

        async def fake_refresh() -> None:
            call_count["n"] += 1

        async def fake_sleeper(target: datetime) -> None:
            return None

        now = datetime(2025, 5, 12, 10, 0, tzinfo=TPE)
        asyncio.run(
            scheduler.tw_intraday_price_loop(
                refresh_fn=fake_refresh,
                sleeper=fake_sleeper,
                now_provider=lambda: now,
                iterations=3,
            )
        )
        self.assertEqual(call_count["n"], 3)

    def test_daily_settlement_loop_calls_settle(self) -> None:
        call_count = {"n": 0}

        async def fake_settle() -> None:
            call_count["n"] += 1

        async def fake_sleeper(target: datetime) -> None:
            return None

        now = datetime(2025, 5, 12, 12, 0, tzinfo=TPE)
        asyncio.run(
            scheduler.tw_daily_settlement_loop(
                settle_fn=fake_settle,
                sleeper=fake_sleeper,
                now_provider=lambda: now,
                iterations=2,
            )
        )
        self.assertEqual(call_count["n"], 2)

    def test_intraday_loop_swallows_refresh_errors(self) -> None:
        # A refresh that raises must not kill the loop — the next tick
        # should still fire.
        attempts = {"n": 0}

        async def flaky_refresh() -> None:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("boom")

        async def fake_sleeper(target: datetime) -> None:
            return None

        now = datetime(2025, 5, 12, 10, 0, tzinfo=TPE)
        asyncio.run(
            scheduler.tw_intraday_price_loop(
                refresh_fn=flaky_refresh,
                sleeper=fake_sleeper,
                now_provider=lambda: now,
                iterations=2,
            )
        )
        self.assertEqual(attempts["n"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

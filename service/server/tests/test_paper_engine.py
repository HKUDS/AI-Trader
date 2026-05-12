"""Tests for the TW-aware paper-trading fill engine.

Three groups:
  - microstructure: round-lot, ±10% price band, session hours, holiday cal.
  - decision: end-to-end evaluate_fill across fill/queue/reject branches.
  - analytics: cumulative return, win rate, drawdown, Sharpe.

All tests pass deterministic datetimes/series — the engine has no I/O so
nothing needs to be mocked. The holiday list is the only date-sensitive
piece; tests pin to 2025/2026 dates that the hand-curated constant covers.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import config
from paper_engine import (
    REJECT_INVALID_LOT_SIZE,
    REJECT_NON_POSITIVE_QUANTITY,
    REJECT_PRICE_OUTSIDE_DAILY_LIMIT,
    TPE,
    coarse_sharpe,
    cumulative_return,
    evaluate_fill,
    is_tw_session_open,
    is_tw_trading_day,
    max_drawdown,
    monthly_win_rate,
    next_tw_open,
    next_tw_trading_day,
    validate_lot_size,
    validate_price_band,
)


class LotSizeTests(unittest.TestCase):
    def test_1000_share_lot_passes(self) -> None:
        self.assertIsNone(validate_lot_size(1000, "tw-stock"))
        self.assertIsNone(validate_lot_size(5000, "tw-stock"))

    def test_partial_lot_rejected(self) -> None:
        self.assertEqual(validate_lot_size(100, "tw-stock"), REJECT_INVALID_LOT_SIZE)
        self.assertEqual(validate_lot_size(1500, "tw-stock"), REJECT_INVALID_LOT_SIZE)

    def test_fractional_quantity_rejected(self) -> None:
        self.assertEqual(validate_lot_size(1000.5, "tw-stock"), REJECT_INVALID_LOT_SIZE)

    def test_zero_quantity_rejected(self) -> None:
        self.assertEqual(validate_lot_size(0, "tw-stock"), REJECT_NON_POSITIVE_QUANTITY)

    def test_us_stock_bypasses_lot_check(self) -> None:
        # The lot-size rule is TW-specific; other markets must not be
        # constrained to 1,000-share multiples.
        self.assertIsNone(validate_lot_size(7, "us-stock"))
        self.assertIsNone(validate_lot_size(0.5, "crypto"))


class PriceBandTests(unittest.TestCase):
    def test_within_band_passes(self) -> None:
        # 1,000 ±10% = [900, 1100]
        self.assertIsNone(validate_price_band(1000, 1000, "tw-stock"))
        self.assertIsNone(validate_price_band(1099, 1000, "tw-stock"))
        self.assertIsNone(validate_price_band(901, 1000, "tw-stock"))

    def test_above_upper_limit_rejected(self) -> None:
        self.assertEqual(
            validate_price_band(1101, 1000, "tw-stock"),
            REJECT_PRICE_OUTSIDE_DAILY_LIMIT,
        )

    def test_below_lower_limit_rejected(self) -> None:
        self.assertEqual(
            validate_price_band(899, 1000, "tw-stock"),
            REJECT_PRICE_OUTSIDE_DAILY_LIMIT,
        )

    def test_missing_previous_close_skips_check(self) -> None:
        # IPO / data-fetch failure should not block paper trades.
        self.assertIsNone(validate_price_band(10000, None, "tw-stock"))
        self.assertIsNone(validate_price_band(10000, 0, "tw-stock"))

    def test_non_tw_market_bypasses_band(self) -> None:
        self.assertIsNone(validate_price_band(1_000_000, 100, "us-stock"))


class SessionHoursTests(unittest.TestCase):
    def test_weekday_session_open_at_10am(self) -> None:
        # 2025-05-12 is Mon (not a holiday)
        ts = datetime(2025, 5, 12, 10, 0, tzinfo=TPE)
        self.assertTrue(is_tw_session_open(ts))

    def test_session_closed_at_2pm(self) -> None:
        ts = datetime(2025, 5, 12, 14, 0, tzinfo=TPE)
        self.assertFalse(is_tw_session_open(ts))

    def test_session_closed_at_830am(self) -> None:
        ts = datetime(2025, 5, 12, 8, 30, tzinfo=TPE)
        self.assertFalse(is_tw_session_open(ts))

    def test_weekend_closed(self) -> None:
        # 2025-05-10 is Sat
        ts = datetime(2025, 5, 10, 10, 0, tzinfo=TPE)
        self.assertFalse(is_tw_session_open(ts))

    def test_holiday_closed(self) -> None:
        # 2025-10-10 is 國慶 (in TW_HOLIDAYS_2025)
        ts = datetime(2025, 10, 10, 10, 0, tzinfo=TPE)
        self.assertFalse(is_tw_session_open(ts))

    def test_holiday_calendar_excludes_228(self) -> None:
        self.assertFalse(is_tw_trading_day(date(2025, 2, 28)))
        self.assertTrue(is_tw_trading_day(date(2025, 5, 12)))


class NextTradingDayTests(unittest.TestCase):
    def test_friday_advances_to_monday(self) -> None:
        # 2025-05-09 is Fri. Next trading day is Mon 2025-05-12.
        self.assertEqual(next_tw_trading_day(date(2025, 5, 9)), date(2025, 5, 12))

    def test_skips_holiday(self) -> None:
        # 2025-10-09 is Thu; Fri 2025-10-10 is 國慶 holiday.
        # Next trading day is Mon 2025-10-13.
        self.assertEqual(next_tw_trading_day(date(2025, 10, 9)), date(2025, 10, 13))

    def test_next_open_after_close_returns_next_day(self) -> None:
        ts = datetime(2025, 5, 12, 14, 0, tzinfo=TPE)
        result = next_tw_open(ts)
        # Tue 2025-05-13 at 09:00 Taipei.
        self.assertEqual(result.date(), date(2025, 5, 13))
        self.assertEqual(result.hour, 9)

    def test_next_open_pre_market_returns_today(self) -> None:
        ts = datetime(2025, 5, 12, 8, 0, tzinfo=TPE)
        result = next_tw_open(ts)
        self.assertEqual(result.date(), date(2025, 5, 12))


class EvaluateFillTests(unittest.TestCase):
    def test_during_session_returns_fill(self) -> None:
        d = evaluate_fill(
            market="tw-stock",
            quantity=1000,
            price=1000,
            previous_close=1000,
            now=datetime(2025, 5, 12, 10, 0, tzinfo=TPE),
        )
        self.assertEqual(d.status, "fill")
        self.assertIsNone(d.reason)

    def test_after_session_queues_for_next_open(self) -> None:
        d = evaluate_fill(
            market="tw-stock",
            quantity=1000,
            price=1000,
            previous_close=1000,
            now=datetime(2025, 5, 12, 14, 0, tzinfo=TPE),
        )
        self.assertEqual(d.status, "queue_for_open")
        self.assertIsNotNone(d.effective_at)
        self.assertIn("tw_market_closed", d.notes)

    def test_partial_lot_rejected_before_session_check(self) -> None:
        # Session is closed but the lot-size error should win regardless —
        # we want the user to fix the obvious bug, not be told "queue then
        # reject at fill time".
        d = evaluate_fill(
            market="tw-stock",
            quantity=500,
            price=1000,
            previous_close=1000,
            now=datetime(2025, 5, 12, 22, 0, tzinfo=TPE),
        )
        self.assertEqual(d.status, "reject")
        self.assertEqual(d.reason, REJECT_INVALID_LOT_SIZE)

    def test_price_outside_band_rejected(self) -> None:
        d = evaluate_fill(
            market="tw-stock",
            quantity=1000,
            price=1200,
            previous_close=1000,
            now=datetime(2025, 5, 12, 10, 0, tzinfo=TPE),
        )
        self.assertEqual(d.status, "reject")
        self.assertEqual(d.reason, REJECT_PRICE_OUTSIDE_DAILY_LIMIT)

    def test_us_stock_always_fills(self) -> None:
        # The engine only gates tw-stock — other markets keep prior behaviour.
        d = evaluate_fill(
            market="us-stock",
            quantity=7,
            price=200,
            previous_close=None,
            now=datetime(2025, 5, 12, 3, 0, tzinfo=TPE),  # pre-US-market
        )
        self.assertEqual(d.status, "fill")


class AnalyticsTests(unittest.TestCase):
    def test_cumulative_return_pct(self) -> None:
        # 100,000 capital, 25,000 profit → 25%.
        self.assertAlmostEqual(cumulative_return([5000, 25000], 100000), 25.0)

    def test_cumulative_return_zero_capital(self) -> None:
        self.assertEqual(cumulative_return([100], 0), 0.0)

    def test_monthly_win_rate(self) -> None:
        # 3 wins (>=0) of 5 → 0.6.
        self.assertAlmostEqual(monthly_win_rate([1, -1, 2, -3, 0]), 0.6)

    def test_max_drawdown_simple(self) -> None:
        # Peak 120, trough 80 → drop 40/120 ≈ 0.333.
        equity = [100, 110, 120, 90, 80, 95]
        self.assertAlmostEqual(max_drawdown(equity), (120 - 80) / 120, places=4)

    def test_max_drawdown_strictly_increasing(self) -> None:
        self.assertEqual(max_drawdown([1, 2, 3, 4]), 0.0)

    def test_coarse_sharpe_positive_for_steady_gain(self) -> None:
        # Constant positive return → infinite Sharpe in theory, but the
        # zero-variance branch returns 0 to keep the result finite. Use
        # mixed positive returns to exercise the real path.
        returns = [0.01, 0.015, 0.005, 0.012, 0.008]
        sharpe = coarse_sharpe(returns)
        self.assertGreater(sharpe, 0)

    def test_coarse_sharpe_zero_variance_returns_zero(self) -> None:
        self.assertEqual(coarse_sharpe([0.01, 0.01, 0.01]), 0.0)

    def test_coarse_sharpe_short_series_returns_zero(self) -> None:
        self.assertEqual(coarse_sharpe([0.01]), 0.0)


class ConfigDefaultsTests(unittest.TestCase):
    def test_round_lot_default(self) -> None:
        self.assertEqual(config.TW_ROUND_LOT_SHARES, 1000)

    def test_daily_price_limit_pct_default(self) -> None:
        self.assertAlmostEqual(config.TW_DAILY_PRICE_LIMIT_PCT, 0.10)

    def test_session_hhmm_defaults(self) -> None:
        self.assertEqual(config.TW_SESSION_OPEN_HHMM, "09:00")
        self.assertEqual(config.TW_SESSION_CLOSE_HHMM, "13:30")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

# ruff: noqa: E402
"""End-to-end coverage for issue #69: intraday timestamps crashing date parsing.

The shipped data stores position dates like "2025-10-01 10:00:00", which the
date-only strptime in get_trading_dates could not parse. These tests exercise
the real scheduling path (parse_date + compute_trading_dates + is_trading_day)
against that exact format, over real temp files.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.price_tools as price_tools
from tools.price_tools import compute_trading_dates
from utils.date_utils import parse_date


class ParseDateTests(unittest.TestCase):
    def test_accepts_plain_date(self):
        self.assertEqual(parse_date("2025-10-01"), datetime(2025, 10, 1))

    def test_accepts_intraday_timestamp(self):
        # The exact shipped format from data/agent_data/*/position/position.jsonl.
        self.assertEqual(parse_date("2025-10-01 10:00:00"), datetime(2025, 10, 1, 10, 0, 0))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_date("01/10/2025")

    def test_regression_old_date_only_parse_would_crash(self):
        # Documents the root cause the fix removes.
        with self.assertRaises(ValueError):
            datetime.strptime("2025-10-01 10:00:00", "%Y-%m-%d")


class ComputeTradingDatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Market calendar marking Oct 2 and 3 as trading days.
        merged = self.tmp_path / "merged.jsonl"
        merged.write_text(
            json.dumps({"Time Series (Daily)": {"2025-10-02": {}, "2025-10-03": {}}}) + "\n",
            encoding="utf-8",
        )
        self._patch = patch.object(price_tools, "get_merged_file_path", return_value=merged)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def _write_positions(self, dates):
        position_file = self.tmp_path / "position.jsonl"
        with open(position_file, "w", encoding="utf-8") as f:
            for value in dates:
                f.write(json.dumps({"date": value, "positions": {}}) + "\n")
        return str(position_file)

    def test_intraday_timestamps_do_not_crash(self):
        position_file = self._write_positions(["2025-10-01 10:00:00"])
        dates = compute_trading_dates(position_file, "2025-10-01", "2025-10-03", market="us")
        self.assertEqual(dates, ["2025-10-02", "2025-10-03"])

    def test_latest_processed_date_is_respected(self):
        position_file = self._write_positions(["2025-10-01 10:00:00", "2025-10-02 11:00:00"])
        dates = compute_trading_dates(position_file, "2025-10-01", "2025-10-03", market="us")
        self.assertEqual(dates, ["2025-10-03"])

    def test_missing_position_file_starts_from_init_date(self):
        dates = compute_trading_dates(None, "2025-10-01", "2025-10-03", market="us")
        self.assertEqual(dates, ["2025-10-02", "2025-10-03"])

    def test_no_new_dates_returns_empty(self):
        position_file = self._write_positions(["2025-10-03 10:00:00"])
        self.assertEqual(compute_trading_dates(position_file, "2025-10-01", "2025-10-03", market="us"), [])

    def test_non_trading_days_are_filtered_out(self):
        # Oct 4 is absent from the calendar, so it must not appear.
        position_file = self._write_positions(["2025-10-01 10:00:00"])
        dates = compute_trading_dates(position_file, "2025-10-01", "2025-10-04", market="us")
        self.assertNotIn("2025-10-04", dates)


if __name__ == "__main__":
    unittest.main()

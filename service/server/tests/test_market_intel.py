import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import market_intel


def _snapshot_payload(symbol: str = "HD") -> dict:
    return {
        "available": True,
        "symbol": symbol,
        "market": "us-stock",
        "analysis_id": f"{symbol}:snapshot",
        "current_price": 338.91,
        "currency": "USD",
        "signal": "hold",
        "signal_score": 1.5,
        "trend_status": "constructive",
        "support_levels": [330.0],
        "resistance_levels": [350.0],
        "bullish_factors": ["Momentum improved."],
        "risk_factors": ["Resistance is nearby."],
        "summary": "Base daily snapshot summary.",
        "analysis": {
            "symbol": symbol,
            "market": "us-stock",
            "current_price": 338.91,
            "signal": "hold",
            "as_of": "2026-04-17",
        },
        "created_at": "2026-04-20T02:00:00Z",
    }


class MarketIntelLatestPayloadTests(unittest.TestCase):
    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel._get_stock_quote_payload")
    @patch("market_intel._get_stock_analysis_snapshot_payload")
    def test_latest_payload_prefers_intraday_quote(
        self,
        mock_snapshot_payload,
        mock_quote_payload,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_snapshot_payload.return_value = _snapshot_payload("HD")
        mock_quote_payload.return_value = {
            "available": True,
            "current_price": 352.11,
            "price_as_of": "2026-04-20T14:35:00Z",
            "price_source": "alpha_vantage_time_series_intraday",
        }

        with patch("market_intel._utc_now", return_value=datetime(2026, 4, 20, 14, 40, tzinfo=timezone.utc)):
            payload = market_intel.get_stock_analysis_latest_payload("HD")

        self.assertEqual(payload["current_price"], 352.11)
        self.assertEqual(payload["price_source"], "alpha_vantage_time_series_intraday")
        self.assertEqual(payload["price_as_of"], "2026-04-20T14:35:00Z")
        self.assertFalse(payload["price_stale"])
        self.assertEqual(payload["price_status"], "realtime")
        self.assertEqual(payload["analysis"]["as_of"], "2026-04-17")

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel._get_stock_quote_payload", return_value=None)
    @patch("market_intel._get_stock_analysis_snapshot_payload")
    def test_latest_payload_falls_back_to_daily_snapshot_when_quote_missing(
        self,
        mock_snapshot_payload,
        _mock_quote_payload,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_snapshot_payload.return_value = _snapshot_payload("AAPL")

        with patch("market_intel._utc_now", return_value=datetime(2026, 4, 20, 14, 40, tzinfo=timezone.utc)):
            payload = market_intel.get_stock_analysis_latest_payload("AAPL")

        self.assertEqual(payload["current_price"], 338.91)
        self.assertEqual(payload["price_source"], "alpha_vantage_time_series_daily_adjusted")
        self.assertEqual(payload["price_as_of"], "2026-04-17T20:00:00Z")
        self.assertTrue(payload["price_stale"])
        self.assertEqual(payload["price_status"], "stale")

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel.get_stock_analysis_latest_payload", side_effect=AssertionError("featured should not call latest"))
    @patch("market_intel._get_stock_analysis_snapshot_payload")
    @patch("market_intel._get_hot_us_stock_symbols", return_value=["AAPL", "MSFT"])
    def test_featured_payload_uses_snapshot_payloads_only(
        self,
        _mock_symbols,
        mock_snapshot_payload,
        _mock_latest_payload,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_snapshot_payload.side_effect = [
            _snapshot_payload("AAPL"),
            _snapshot_payload("MSFT"),
        ]

        payload = market_intel.get_featured_stock_analysis_payload(limit=2)

        self.assertTrue(payload["available"])
        self.assertEqual([item["symbol"] for item in payload["items"]], ["AAPL", "MSFT"])


class StockPriceMetadataTests(unittest.TestCase):
    """Coverage for _build_stock_price_metadata staleness classification.

    The intent of `price_status="session_close"` is "the latest US session has
    closed; this intraday quote is the most-recent available data until the
    next open". The staleness check must therefore accept Friday's close as
    `session_close` on Saturday/Sunday, and accept the previous trading day's
    close as `session_close` during the next day's pre-market hours.
    """

    def _intraday(self, price_as_of: str) -> dict:
        return {
            "price_as_of": price_as_of,
            "price_source": "alpha_vantage_time_series_intraday",
        }

    def test_metadata_during_market_open_realtime(self) -> None:
        # Tuesday 14:35 ET, quote from 14:34 ET (1 min ago) → realtime.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 21, 18, 35, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-21T18:34:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "realtime")

    def test_metadata_post_close_same_day_session_close(self) -> None:
        # Tuesday 18:00 ET (after 16:00 close), quote from Tuesday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 21, 22, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-21T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_friday_close_on_saturday_is_session_close(self) -> None:
        # Saturday 10:00 ET, quote from Friday 16:00 ET.
        # Friday's close IS the latest available real-time data until Monday's
        # open — current behavior incorrectly classifies it as `stale`.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-24T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_friday_close_on_sunday_is_session_close(self) -> None:
        # Sunday 12:00 ET, quote from Friday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 26, 16, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-24T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_premarket_next_day_is_session_close(self) -> None:
        # Tuesday 08:00 ET (pre-market), quote from Monday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-20T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_premarket_monday_uses_friday_close(self) -> None:
        # Monday 08:00 ET pre-market, quote from previous Friday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-24T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_quote_older_than_last_session_is_stale(self) -> None:
        # Saturday 10:00 ET, quote from Wednesday 16:00 ET (2 sessions stale).
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-22T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertTrue(meta["price_stale"])
        self.assertEqual(meta["price_status"], "stale")

    def test_metadata_daily_fallback_remains_stale(self) -> None:
        meta = market_intel._build_stock_price_metadata(
            "2026-04-17T20:00:00Z",
            "alpha_vantage_time_series_daily_adjusted",
        )
        self.assertTrue(meta["price_stale"])
        self.assertEqual(meta["price_status"], "stale")

    def test_metadata_unparseable_timestamp_is_stale(self) -> None:
        meta = market_intel._build_stock_price_metadata(None, None)
        self.assertTrue(meta["price_stale"])
        self.assertEqual(meta["price_status"], "stale")
        self.assertIsNone(meta["price_age_seconds"])


if __name__ == "__main__":
    unittest.main()

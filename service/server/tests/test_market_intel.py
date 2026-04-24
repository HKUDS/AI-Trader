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


if __name__ == "__main__":
    unittest.main()

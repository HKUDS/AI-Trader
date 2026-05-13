import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import price_fetcher


def _time_series_payload(rows: dict) -> dict:
    return {"Time Series (1min)": rows}


class UsStockPriceTimezoneTests(unittest.TestCase):
    def test_us_stock_lookup_uses_est_timestamp_in_winter(self) -> None:
        payload = _time_series_payload({
            "2025-01-15 09:30:00": {"4. close": "100.0"},
            "2025-01-15 10:30:00": {"4. close": "200.0"},
        })

        with patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"):
            with patch.object(price_fetcher, "_request_json_with_retry", return_value=payload) as mock_request:
                price = price_fetcher._get_us_stock_price("AAPL", "2025-01-15T14:30:00Z")

        self.assertEqual(price, 100.0)
        request_params = mock_request.call_args.kwargs["params"]
        self.assertEqual(request_params["month"], "2025-01")

    def test_us_stock_lookup_uses_edt_timestamp_in_summer(self) -> None:
        payload = _time_series_payload({
            "2025-07-15 09:30:00": {"4. close": "100.0"},
            "2025-07-15 10:30:00": {"4. close": "300.0"},
        })

        with patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"):
            with patch.object(price_fetcher, "_request_json_with_retry", return_value=payload):
                price = price_fetcher._get_us_stock_price("AAPL", "2025-07-15T14:30:00Z")

        self.assertEqual(price, 300.0)

    def test_us_stock_lookup_uses_eastern_month_at_utc_boundary(self) -> None:
        payload = _time_series_payload({
            "2025-07-31 20:30:00": {"4. close": "150.0"},
            "2025-08-01 00:30:00": {"4. close": "250.0"},
        })

        with patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"):
            with patch.object(price_fetcher, "_request_json_with_retry", return_value=payload) as mock_request:
                price = price_fetcher._get_us_stock_price("AAPL", "2025-08-01T00:30:00Z")

        self.assertEqual(price, 150.0)
        request_params = mock_request.call_args.kwargs["params"]
        self.assertEqual(request_params["month"], "2025-07")


if __name__ == "__main__":
    unittest.main()

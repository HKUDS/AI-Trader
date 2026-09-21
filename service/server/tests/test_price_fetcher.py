import subprocess
import sys
import textwrap
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
    def test_market_alias_uses_crypto_price_source(self) -> None:
        with patch.object(price_fetcher, "_get_hyperliquid_candle_close", return_value=None), \
             patch.object(price_fetcher, "_get_hyperliquid_mid_price", return_value=4.2) as mock_mid, \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=125.79) as mock_stock:
            price = price_fetcher.get_price_from_market("SUI", "2026-05-15T08:00:00Z", "binance")

        self.assertEqual(price, 4.2)
        mock_mid.assert_called_once_with("SUI")
        mock_stock.assert_not_called()

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

    def test_us_stock_market_prefers_alpha_vantage_before_yfinance(self) -> None:
        with patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=125.79) as mock_alpha, \
             patch.object(price_fetcher, "_get_yfinance_us_stock_price", return_value=124.0) as mock_yfinance:
            price = price_fetcher.get_price_from_market("AAPL", "2025-08-01T14:30:00Z", "us-stock")

        self.assertEqual(price, 125.79)
        mock_alpha.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")
        mock_yfinance.assert_not_called()

    def test_us_stock_market_falls_back_to_yfinance_when_alpha_returns_none(self) -> None:
        with patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=None) as mock_alpha, \
             patch.object(price_fetcher, "_get_yfinance_us_stock_price", return_value=124.0) as mock_yfinance:
            price = price_fetcher.get_price_from_market("AAPL", "2025-08-01T14:30:00Z", "us-stock")

        self.assertEqual(price, 124.0)
        mock_alpha.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")
        mock_yfinance.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")

    def test_us_stock_market_uses_yfinance_when_alpha_key_missing(self) -> None:
        with patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "demo"), \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=125.79) as mock_alpha, \
             patch.object(price_fetcher, "_get_yfinance_us_stock_price", return_value=124.0) as mock_yfinance:
            price = price_fetcher.get_price_from_market("AAPL", "2025-08-01T14:30:00Z", "us-stock")

        self.assertEqual(price, 124.0)
        mock_alpha.assert_not_called()
        mock_yfinance.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")

    def test_polymarket_mid_price_uses_best_bid_and_ask_from_unsorted_book(self) -> None:
        book = {
            "bids": [
                {"price": "0.001", "size": "1000"},
                {"price": "0.41", "size": "1000"},
                {"price": "0.421", "size": "1000"},
            ],
            "asks": [
                {"price": "0.999", "size": "1000"},
                {"price": "0.45", "size": "1000"},
                {"price": "0.422", "size": "1000"},
            ],
        }

        with patch.object(
            price_fetcher,
            "_polymarket_resolve_reference",
            return_value={"token_id": "123", "outcome": "Yes", "market": {}},
        ), patch.object(price_fetcher, "_polymarket_get_json", return_value=book):
            price = price_fetcher._get_polymarket_mid_price("market-slug", token_id="123", outcome="Yes")

        self.assertEqual(price, 0.4215)


class ZoneinfoFallbackTests(unittest.TestCase):
    """price_fetcher must import on a host without a tz database."""

    SCRIPT = textwrap.dedent(
        """
        import sys
        import zoneinfo


        class _BlockTzdata:
            def find_spec(self, name, path=None, target=None):
                if name == "tzdata" or name.startswith("tzdata."):
                    raise ImportError("tzdata is blocked for this test")
                return None


        sys.meta_path.insert(0, _BlockTzdata())
        zoneinfo.reset_tzpath([])

        try:
            zoneinfo.ZoneInfo("America/New_York")
        except zoneinfo.ZoneInfoNotFoundError:
            pass
        else:
            print("tz database still reachable")
            raise SystemExit(2)

        sys.path.insert(0, sys.argv[1])
        import price_fetcher

        print(price_fetcher.ET_TZ.utcoffset(None).total_seconds())
        """
    )

    def test_import_succeeds_without_a_tz_database(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", self.SCRIPT, str(SERVER_DIR)],
            capture_output=True,
            text=True,
        )

        if result.returncode == 2:
            self.fail("precondition not met: " + result.stdout.strip())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(float(result.stdout.strip()), -5 * 3600)


if __name__ == "__main__":
    unittest.main()

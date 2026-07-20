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


class LsePriceSourceTests(unittest.TestCase):
    @staticmethod
    def _http_error(status_code: int):
        import requests

        response = requests.Response()
        response.status_code = status_code
        return requests.HTTPError(response=response)

    def test_us_stock_prefers_lse_when_key_set(self) -> None:
        with patch.object(price_fetcher, "LSE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_lse_us_stock_price", return_value=101.5) as mock_lse, \
             patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=125.79) as mock_alpha, \
             patch.object(price_fetcher, "_get_yfinance_us_stock_price", return_value=124.0) as mock_yfinance:
            price = price_fetcher.get_price_from_market("AAPL", "2025-08-01T14:30:00Z", "us-stock")

        self.assertEqual(price, 101.5)
        mock_lse.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")
        mock_alpha.assert_not_called()
        mock_yfinance.assert_not_called()

    def test_us_stock_falls_back_to_alpha_when_lse_returns_none(self) -> None:
        with patch.object(price_fetcher, "LSE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_lse_us_stock_price", return_value=None) as mock_lse, \
             patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=125.79) as mock_alpha:
            price = price_fetcher.get_price_from_market("AAPL", "2025-08-01T14:30:00Z", "us-stock")

        self.assertEqual(price, 125.79)
        mock_lse.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")
        mock_alpha.assert_called_once_with("AAPL", "2025-08-01T14:30:00Z")

    def test_us_stock_skips_lse_when_key_missing(self) -> None:
        with patch.object(price_fetcher, "LSE_API_KEY", ""), \
             patch.object(price_fetcher, "_get_lse_us_stock_price", return_value=101.5) as mock_lse, \
             patch.object(price_fetcher, "ALPHA_VANTAGE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_us_stock_price", return_value=125.79):
            price = price_fetcher.get_price_from_market("AAPL", "2025-08-01T14:30:00Z", "us-stock")

        self.assertEqual(price, 125.79)
        mock_lse.assert_not_called()

    def test_crypto_prefers_lse_and_falls_back_to_hyperliquid(self) -> None:
        with patch.object(price_fetcher, "LSE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_lse_crypto_price", return_value=64000.5) as mock_lse, \
             patch.object(price_fetcher, "_get_hyperliquid_candle_close", return_value=63999.0) as mock_hl:
            price = price_fetcher.get_price_from_market("BTC", "2025-08-01T14:30:00Z", "crypto")

        self.assertEqual(price, 64000.5)
        mock_lse.assert_called_once_with("BTC", "2025-08-01T14:30:00Z")
        mock_hl.assert_not_called()

        with patch.object(price_fetcher, "LSE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_get_lse_crypto_price", return_value=None), \
             patch.object(price_fetcher, "_get_hyperliquid_candle_close", return_value=63999.0):
            price = price_fetcher.get_price_from_market("BTC", "2025-08-01T14:30:00Z", "crypto")

        self.assertEqual(price, 63999.0)

    def test_lse_candle_close_queries_bounded_window(self) -> None:
        rows = [{"timestamp": "2025-08-01T14:30:00+00:00", "close": 101.5, "symbol": "AAPL"}]
        with patch.object(price_fetcher, "_lse_get_json", return_value=rows) as mock_get:
            from datetime import datetime, timezone

            target = datetime(2025, 8, 1, 14, 30, tzinfo=timezone.utc)
            price = price_fetcher._lse_candle_close("d_candles_aapl", target)

        self.assertEqual(price, 101.5)
        table, params = mock_get.call_args.args
        self.assertEqual(table, "d_candles_aapl")
        self.assertIn(("timestamp", "lte.2025-08-01T14:30:00Z"), params)
        self.assertIn(("timestamp", "gte.2025-07-25T14:30:00Z"), params)
        self.assertIn(("order", "timestamp.desc"), params)
        self.assertIn(("limit", "1"), params)

    def test_lse_us_stock_tries_fallback_tables_on_404(self) -> None:
        rows = [{"timestamp": "2025-08-01T14:30:00+00:00", "close": 99.25, "symbol": "AAPL"}]
        with patch.object(price_fetcher, "LSE_API_KEY", "test-key"), \
             patch.object(
                 price_fetcher,
                 "_request_json_with_retry",
                 side_effect=[self._http_error(404), self._http_error(404), rows],
             ) as mock_request:
            price = price_fetcher._get_lse_us_stock_price("AAPL", "2025-08-01T14:30:00Z")

        self.assertEqual(price, 99.25)
        requested_urls = [call.args[2] for call in mock_request.call_args_list]
        self.assertTrue(requested_urls[0].endswith("/d_candles_aapl"))
        self.assertTrue(requested_urls[1].endswith("/candles_aapl"))
        self.assertTrue(requested_urls[2].endswith("/x_candles_5m"))

    def test_lse_crypto_maps_coin_to_usd_pair_table(self) -> None:
        rows = [{"timestamp": "2025-08-01T14:30:00+00:00", "close": 1880.5, "symbol": "ETH/USD"}]
        with patch.object(price_fetcher, "LSE_API_KEY", "test-key"), \
             patch.object(price_fetcher, "_lse_get_json", return_value=rows) as mock_get:
            price = price_fetcher._get_lse_crypto_price("ETH-PERP", "2025-08-01T14:30:00Z")

        self.assertEqual(price, 1880.5)
        self.assertEqual(mock_get.call_args.args[0], "candles_eth_usd")


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import requests

import tw_market
import finmind_client


_TWSE_SAMPLE = [
    {
        "Code": "2330",
        "Name": "台積電",
        "TradeVolume": "30,000,000",
        "TradeValue": "30,000,000,000",
        "OpeningPrice": "1000",
        "HighestPrice": "1015",
        "LowestPrice": "998",
        "ClosingPrice": "1010",
        "Change": "+10",
        "Transaction": "55,000",
        "MonthlyAveragePrice": "1005",
    },
    {
        "Code": "0050",
        "Name": "元大台灣50",
        "ClosingPrice": "180.25",
    },
    {
        "Code": "9999",
        "Name": "Bad row",
        "ClosingPrice": "",
        "OpeningPrice": "",
    },
]


def _twse_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TwMarketTests(unittest.TestCase):
    @patch("tw_market.requests.get")
    def test_resolves_closing_price(self, mock_get):
        mock_get.return_value = _twse_response(_TWSE_SAMPLE)
        price = tw_market.get_tw_stock_price("2330", "2026-05-12T05:00:00Z")
        self.assertEqual(price, 1010.0)

    @patch("tw_market.requests.get")
    def test_etf_resolves_with_decimal(self, mock_get):
        mock_get.return_value = _twse_response(_TWSE_SAMPLE)
        price = tw_market.get_tw_stock_price("0050", "2026-05-12T05:00:00Z")
        self.assertEqual(price, 180.25)

    @patch("tw_market.requests.get")
    def test_missing_symbol_returns_none(self, mock_get):
        mock_get.return_value = _twse_response(_TWSE_SAMPLE)
        self.assertIsNone(tw_market.get_tw_stock_price("0000", "2026-05-12T05:00:00Z"))

    @patch("tw_market.requests.get")
    def test_blank_close_falls_back_then_returns_none(self, mock_get):
        mock_get.return_value = _twse_response(_TWSE_SAMPLE)
        # Code 9999 has both ClosingPrice and OpeningPrice blank → None.
        self.assertIsNone(tw_market.get_tw_stock_price("9999", "2026-05-12T05:00:00Z"))

    @patch("tw_market.requests.get")
    def test_request_failure_returns_none(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("reset by peer")
        self.assertIsNone(tw_market.get_tw_stock_price("2330", "2026-05-12T05:00:00Z"))


_FINMIND_OK = {
    "status": 200,
    "data": [
        {"date": "2026-05-08", "stock_id": "2330", "close": 1005.0},
        {"date": "2026-05-09", "stock_id": "2330", "close": 1010.0},
        {"date": "2026-05-12", "stock_id": "2330", "close": 1020.0},
    ],
}


class FinmindClientTests(unittest.TestCase):
    @patch("finmind_client.requests.get")
    def test_returns_last_close(self, mock_get):
        mock_get.return_value = _twse_response(_FINMIND_OK)
        price = finmind_client.get_tw_stock_price_finmind("2330", "2026-05-12T05:00:00Z")
        self.assertEqual(price, 1020.0)

    @patch("finmind_client.requests.get")
    def test_empty_data_returns_none(self, mock_get):
        mock_get.return_value = _twse_response({"status": 200, "data": []})
        self.assertIsNone(finmind_client.get_tw_stock_price_finmind("2330", "2026-05-12T05:00:00Z"))

    @patch("finmind_client.requests.get")
    def test_non_200_status_returns_none(self, mock_get):
        mock_get.return_value = _twse_response({"status": 402, "msg": "rate limited"})
        self.assertIsNone(finmind_client.get_tw_stock_price_finmind("2330", "2026-05-12T05:00:00Z"))

    @patch("finmind_client.requests.get")
    def test_bad_executed_at_returns_none_without_request(self, mock_get):
        self.assertIsNone(finmind_client.get_tw_stock_price_finmind("2330", "not-a-date"))
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()

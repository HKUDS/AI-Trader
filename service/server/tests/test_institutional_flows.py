"""Tests for service.server.data_sources.institutional_flows.

Real FinMind API is never hit — all requests are mocked.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import requests  # noqa: E402

from data_sources import institutional_flows  # noqa: E402


SAMPLE_PAYLOAD = {
    "msg": "success",
    "status": 200,
    "data": [
        {"date": "2026-05-08", "stock_id": "2330", "buy": 0,        "name": "Foreign_Dealer_Self",  "sell": 0},
        {"date": "2026-05-08", "stock_id": "2330", "buy": 362000,   "name": "Dealer_self",          "sell": 455200},
        {"date": "2026-05-08", "stock_id": "2330", "buy": 497603,   "name": "Dealer_Hedging",       "sell": 296757},
        {"date": "2026-05-08", "stock_id": "2330", "buy": 18585696, "name": "Foreign_Investor",     "sell": 19443369},
        {"date": "2026-05-08", "stock_id": "2330", "buy": 1451008,  "name": "Investment_Trust",     "sell": 182016},
    ],
}


def _mock_response(payload, status_code=200):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = payload
    m.status_code = status_code
    return m


class TestAggregation(unittest.TestCase):
    def test_collapses_per_investor_rows_into_one_row(self):
        rows = institutional_flows._aggregate_finmind_rows(SAMPLE_PAYLOAD["data"])
        self.assertEqual(len(rows), 1)
        agg = rows[0]
        self.assertEqual(agg["date"], "2026-05-08")
        self.assertEqual(agg["stock_id"], "2330")
        # Foreign = Foreign_Investor + Foreign_Dealer_Self
        self.assertEqual(agg["foreign_buy"], 18585696)
        self.assertEqual(agg["foreign_sell"], 19443369)
        self.assertEqual(agg["investment_trust_buy"], 1451008)
        self.assertEqual(agg["investment_trust_sell"], 182016)
        # Dealer = Dealer_self + Dealer_Hedging
        self.assertEqual(agg["dealer_buy"], 362000 + 497603)
        self.assertEqual(agg["dealer_sell"], 455200 + 296757)
        # net_total = sum of (buy - sell)
        expected_net = (
            (18585696 - 19443369)
            + (1451008 - 182016)
            + (362000 + 497603 - 455200 - 296757)
        )
        self.assertEqual(agg["net_total"], expected_net)

    def test_unknown_investor_name_ignored(self):
        rows = institutional_flows._aggregate_finmind_rows([
            {"date": "2026-05-08", "stock_id": "2330", "name": "Mystery_Bucket", "buy": 999, "sell": 111},
        ])
        # The row exists (date+stock_id valid) but all canonical buckets are 0
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["foreign_buy"], 0)
        self.assertEqual(rows[0]["dealer_buy"], 0)
        self.assertEqual(rows[0]["investment_trust_buy"], 0)

    def test_skips_rows_without_date_or_stock_id(self):
        rows = institutional_flows._aggregate_finmind_rows([
            {"date": "", "stock_id": "2330", "name": "Foreign_Investor", "buy": 1, "sell": 0},
            {"date": "2026-05-08", "stock_id": "", "name": "Foreign_Investor", "buy": 1, "sell": 0},
            {"name": "Foreign_Investor", "buy": 1, "sell": 0},
        ])
        self.assertEqual(rows, [])


class TestFetchInstitutionalFlows(unittest.TestCase):
    @patch("data_sources.institutional_flows.requests.get")
    def test_happy_path(self, mock_get):
        mock_get.return_value = _mock_response(SAMPLE_PAYLOAD)
        result = institutional_flows.fetch_institutional_flows(
            "2330", "2026-05-08", "2026-05-08"
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["stock_id"], "2330")
        # Verify request URL params
        call = mock_get.call_args
        self.assertIn("params", call.kwargs)
        params = call.kwargs["params"]
        self.assertEqual(params["dataset"], "TaiwanStockInstitutionalInvestorsBuySell")
        self.assertEqual(params["data_id"], "2330")
        self.assertEqual(params["start_date"], "2026-05-08")
        self.assertEqual(params["end_date"], "2026-05-08")

    @patch("data_sources.institutional_flows.requests.get")
    def test_empty_symbol_returns_none(self, mock_get):
        result = institutional_flows.fetch_institutional_flows("", "2026-05-08")
        self.assertIsNone(result)
        mock_get.assert_not_called()

    @patch("data_sources.institutional_flows.requests.get")
    def test_network_error_returns_none(self, mock_get):
        mock_get.side_effect = requests.RequestException("boom")
        result = institutional_flows.fetch_institutional_flows("2330", "2026-05-08")
        self.assertIsNone(result)

    @patch("data_sources.institutional_flows.requests.get")
    def test_non_success_status_returns_none(self, mock_get):
        mock_get.return_value = _mock_response({"status": 400, "msg": "bad", "data": []})
        result = institutional_flows.fetch_institutional_flows("2330", "2026-05-08")
        self.assertIsNone(result)

    @patch("data_sources.institutional_flows.requests.get")
    def test_token_injected_when_env_set(self, mock_get):
        mock_get.return_value = _mock_response(SAMPLE_PAYLOAD)
        with patch.dict("os.environ", {"FINMIND_API_TOKEN": "abc"}):
            institutional_flows.fetch_institutional_flows("2330", "2026-05-08")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["token"], "abc")


class TestLatestNet(unittest.TestCase):
    @patch("data_sources.institutional_flows.fetch_institutional_flows")
    def test_returns_last_row(self, mock_fetch):
        mock_fetch.return_value = [
            {"date": "2026-05-07", "stock_id": "2330", "net_total": 100},
            {"date": "2026-05-08", "stock_id": "2330", "net_total": 200},
        ]
        result = institutional_flows.get_latest_institutional_net("2330")
        self.assertEqual(result["date"], "2026-05-08")
        self.assertEqual(result["net_total"], 200)

    @patch("data_sources.institutional_flows.fetch_institutional_flows")
    def test_returns_none_when_no_data(self, mock_fetch):
        mock_fetch.return_value = []
        result = institutional_flows.get_latest_institutional_net("9999")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

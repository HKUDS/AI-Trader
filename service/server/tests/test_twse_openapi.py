"""Tests for service.server.data_sources.twse_openapi.

Real TWSE OpenAPI is never hit — all requests are mocked.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import requests  # noqa: E402

from data_sources import twse_openapi  # noqa: E402


class TestFetchJson(unittest.TestCase):
    def _mock_response(self, payload, status_code=200):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = payload
        m.status_code = status_code
        return m

    def test_pe_ratios_happy_path(self):
        sample = [{"Code": "2330", "PEratio": "20.5", "DividendYield": "1.6", "PBratio": "5.0"}]
        with patch.object(requests, "get", return_value=self._mock_response(sample)) as g:
            out = twse_openapi.fetch_pe_ratios()
        self.assertEqual(out, sample)
        # Built URL must hit the documented swagger path.
        called_url = g.call_args[0][0]
        self.assertTrue(called_url.endswith("/exchangeReport/BWIBBU_ALL"))

    def test_get_pe_for_symbol_picks_matching_row(self):
        sample = [
            {"Code": "2330", "PEratio": "20.5"},
            {"Code": "0050", "PEratio": "0.0"},
        ]
        with patch.object(requests, "get", return_value=self._mock_response(sample)):
            row = twse_openapi.get_pe_for_symbol("2330")
        self.assertEqual(row["PEratio"], "20.5")

    def test_get_pe_for_unknown_symbol_returns_none(self):
        sample = [{"Code": "2330", "PEratio": "20.5"}]
        with patch.object(requests, "get", return_value=self._mock_response(sample)):
            self.assertIsNone(twse_openapi.get_pe_for_symbol("9999"))

    def test_network_error_returns_none(self):
        with patch.object(requests, "get", side_effect=requests.RequestException("DNS")):
            self.assertIsNone(twse_openapi.fetch_pe_ratios())

    def test_non_list_payload_rejected(self):
        with patch.object(requests, "get", return_value=self._mock_response({"unexpected": "object"})):
            self.assertIsNone(twse_openapi.fetch_listed_companies())

    def test_listed_companies_endpoint_path(self):
        with patch.object(requests, "get", return_value=self._mock_response([])) as g:
            twse_openapi.fetch_listed_companies()
        self.assertTrue(g.call_args[0][0].endswith("/opendata/t187ap03_L"))

    def test_monthly_revenue_endpoint_path(self):
        with patch.object(requests, "get", return_value=self._mock_response([])) as g:
            twse_openapi.fetch_monthly_revenue()
        self.assertTrue(g.call_args[0][0].endswith("/opendata/t187ap05_P"))

    def test_foreign_top20_endpoint_path(self):
        with patch.object(requests, "get", return_value=self._mock_response([])) as g:
            twse_openapi.fetch_foreign_top20_holdings()
        self.assertTrue(g.call_args[0][0].endswith("/fund/MI_QFIIS_sort_20"))

    def test_get_pe_short_circuits_on_empty(self):
        with patch.object(requests, "get", return_value=self._mock_response([])):
            self.assertIsNone(twse_openapi.get_pe_for_symbol("2330"))


if __name__ == "__main__":
    unittest.main()

"""Tests for service.server.brokers.pionex_client.

No real Pionex API contact. Validates:
  - constructor rejects empty key / secret
  - signing payload is deterministic
  - klines endpoint returns parsed list
  - klines exception fallback returns []
  - authenticated fetch_balance attaches PIONEX-KEY / -SIGNATURE / -TIMESTAMP
  - place_order / cancel_order raise NotImplementedError (Phase-3 gate)
"""

import hashlib
import hmac
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import requests  # noqa: E402

from brokers.pionex_client import PionexClient  # noqa: E402


class TestPionexClientConstruction(unittest.TestCase):
    def test_rejects_empty_key(self):
        with self.assertRaises(ValueError):
            PionexClient("", "secret")

    def test_rejects_empty_secret(self):
        with self.assertRaises(ValueError):
            PionexClient("key", "")

    def test_rejects_whitespace_key(self):
        with self.assertRaises(ValueError):
            PionexClient("   ", "secret")

    def test_strips_keys(self):
        c = PionexClient("  key  ", "  secret  ")
        self.assertEqual(c.api_key, "key")


class TestSigning(unittest.TestCase):
    def setUp(self):
        self.client = PionexClient("key", "topsecret")

    def test_signature_matches_documented_format(self):
        ts = "1715500000000"
        path = "/api/v1/account/balances"
        sig = self.client._sign_payload("GET", path, {}, "", ts)
        expected = hmac.new(
            b"topsecret",
            f"GET{path}{ts}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(sig, expected)

    def test_query_params_sorted_in_signature(self):
        ts = "1715500000000"
        # Two different param orders must produce the same signature
        # because we sort keys lexicographically.
        sig1 = self.client._sign_payload("GET", "/x", {"b": "2", "a": "1"}, "", ts)
        sig2 = self.client._sign_payload("GET", "/x", {"a": "1", "b": "2"}, "", ts)
        self.assertEqual(sig1, sig2)
        # And it must include the query in canonical order.
        expected = hmac.new(
            b"topsecret",
            f"GET/x?a=1&b=2{ts}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(sig1, expected)

    def test_auth_headers_contains_required_keys(self):
        headers = self.client._auth_headers("GET", "/api/v1/account/balances", {})
        self.assertIn("PIONEX-KEY", headers)
        self.assertIn("PIONEX-SIGNATURE", headers)
        self.assertIn("PIONEX-TIMESTAMP", headers)
        self.assertEqual(headers["PIONEX-KEY"], "key")


class TestFetchKlines(unittest.TestCase):
    def setUp(self):
        self.client = PionexClient("key", "secret")

    def _mock_response(self, payload):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = payload
        return m

    def test_returns_data_list(self):
        # Pionex returns {"data": {"klines": [...]}} historically — handle both shapes.
        payload = {"data": {"klines": [{"t": 1, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100}]}}
        with patch.object(requests, "get", return_value=self._mock_response(payload)) as g:
            out = self.client.fetch_klines("BTC_USDT")
        self.assertEqual(len(out), 1)
        # Public endpoint should NOT be signed → no Pionex headers attached.
        call_kwargs = g.call_args[1]
        self.assertNotIn("headers", call_kwargs)

    def test_returns_empty_on_network_error(self):
        with patch.object(requests, "get", side_effect=requests.RequestException("boom")):
            self.assertEqual(self.client.fetch_klines("BTC_USDT"), [])


class TestFetchBalance(unittest.TestCase):
    def setUp(self):
        self.client = PionexClient("key", "secret")

    def test_attaches_auth_headers(self):
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {"balances": []}
        with patch.object(requests, "get", return_value=mock) as g:
            out = self.client.fetch_balance()
        self.assertEqual(out, {"balances": []})
        headers = g.call_args[1]["headers"]
        self.assertIn("PIONEX-KEY", headers)
        self.assertIn("PIONEX-SIGNATURE", headers)
        self.assertIn("PIONEX-TIMESTAMP", headers)


class TestNotImplementedGates(unittest.TestCase):
    def test_place_order_raises(self):
        c = PionexClient("k", "s")
        with self.assertRaises(NotImplementedError):
            c.place_order("BTC_USDT", "BUY", 100)

    def test_cancel_order_raises(self):
        c = PionexClient("k", "s")
        with self.assertRaises(NotImplementedError):
            c.cancel_order("order-123")


if __name__ == "__main__":
    unittest.main()

"""Tests for the research-enrichment helper in routes_market.

Verifies the helper degrades gracefully when data_sources is unavailable
and surfaces per-section status when network calls fail.
"""

import sys
import types
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _stub_fastapi() -> None:
    """Insert minimal fastapi stubs so routes_market imports without the dep."""
    if "fastapi" in sys.modules:
        return
    fastapi = types.ModuleType("fastapi")

    class _App:
        def get(self, *a, **k):
            def deco(fn):
                return fn
            return deco

    fastapi.FastAPI = _App
    fastapi.HTTPException = Exception
    fastapi.WebSocket = object
    fastapi.WebSocketDisconnect = Exception
    fastapi.APIRouter = _App
    fastapi.Body = lambda *a, **k: None
    fastapi.Query = lambda *a, **k: None
    fastapi.Depends = lambda *a, **k: None
    fastapi.status = types.SimpleNamespace(HTTP_400_BAD_REQUEST=400)
    sys.modules["fastapi"] = fastapi
    responses = types.ModuleType("fastapi.responses")
    responses.JSONResponse = object
    responses.StreamingResponse = object
    sys.modules["fastapi.responses"] = responses
    middleware = types.ModuleType("fastapi.middleware.cors")
    middleware.CORSMiddleware = object
    sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
    sys.modules["fastapi.middleware.cors"] = middleware


_stub_fastapi()

import routes_market as _rm  # noqa: E402


class TestEnrichmentDegradesGracefully(unittest.TestCase):
    def setUp(self):
        # Save originals so we can restore after each test.
        self._orig_tw = _rm._tw_twstock
        self._orig_inst = _rm._institutional_flows

    def tearDown(self):
        _rm._tw_twstock = self._orig_tw
        _rm._institutional_flows = self._orig_inst


    def test_unavailable_when_modules_missing(self):
        _rm._tw_twstock = None
        _rm._institutional_flows = None
        result = _rm._build_research_enrichment("2330")
        self.assertEqual(result["realtime"]["status"], "unavailable")
        self.assertEqual(result["institutional"]["status"], "unavailable")
        self.assertEqual(result["institutional"]["rows"], [])

    def test_institutional_ok_returns_at_most_5_rows(self):
        class FakeFlows:
            @staticmethod
            def fetch_institutional_flows(sym, start, end):
                return [{"date": f"2026-05-0{i}", "net_total": i} for i in range(1, 8)]

        _rm._institutional_flows = FakeFlows
        _rm._tw_twstock = None
        result = _rm._build_research_enrichment("2330")
        self.assertEqual(result["institutional"]["status"], "ok")
        self.assertEqual(len(result["institutional"]["rows"]), 5)
        self.assertEqual(result["institutional"]["rows"][0]["date"], "2026-05-03")
        self.assertEqual(result["institutional"]["rows"][-1]["date"], "2026-05-07")

    def test_institutional_error_when_fetch_returns_none(self):
        class FakeFlows:
            @staticmethod
            def fetch_institutional_flows(sym, start, end):
                return None

        _rm._institutional_flows = FakeFlows
        _rm._tw_twstock = None
        result = _rm._build_research_enrichment("9999")
        self.assertEqual(result["institutional"]["status"], "error")

    def test_realtime_ok_path(self):
        class FakeTwstock:
            @staticmethod
            def fetch_realtime(sym):
                return {"price": 1000, "symbol": sym}

        _rm._tw_twstock = FakeTwstock
        _rm._institutional_flows = None
        result = _rm._build_research_enrichment("2330")
        self.assertEqual(result["realtime"]["status"], "ok")
        self.assertEqual(result["realtime"]["data"]["symbol"], "2330")

    def test_realtime_error_caught(self):
        class BoomTwstock:
            @staticmethod
            def fetch_realtime(sym):
                raise RuntimeError("upstream down")

        _rm._tw_twstock = BoomTwstock
        _rm._institutional_flows = None
        result = _rm._build_research_enrichment("2330")
        self.assertEqual(result["realtime"]["status"], "error")
        self.assertEqual(result["realtime"]["error"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()

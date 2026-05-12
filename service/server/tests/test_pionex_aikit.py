"""Unit tests for the Pionex AI Kit MCP subprocess wrapper.

The Pionex AI Kit MCP server is a node subprocess. None of these tests
spawn it — they inject a `FakeTransport` that records the JSON-RPC
payloads the wrapper would have sent and returns canned responses. That
keeps the suite fast, hermetic, and independent of node being installed
on the test machine.

The cases that matter most are the red-line checks (4, 5, 6): the wrapper
must refuse to forward a write call when user consent or
`ALLOW_LIVE_TRADING` is missing, and that refusal must happen *before*
the transport is touched (so a forgotten lock does not leak even one
test order to a future real subprocess).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi import HTTPException

import config
from integrations import PionexMCPClient, PionexMCPError


class FakeTransport:
    """Records outgoing JSON-RPC payloads and replays scripted responses.

    The wrapper always issues `initialize` before any other call. To keep
    test setup small, the fake responds to `initialize` and `tools/list`
    automatically and lets the per-test script handle `tools/call`.
    """

    def __init__(self, tool_responses: Dict[str, Any]) -> None:
        self._tool_responses = tool_responses
        self.requests: List[Dict[str, Any]] = []
        self.closed = False

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.requests.append(payload)
        method = payload.get("method")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "pionex-trade-mcp", "version": "0.2.49"},
                    "capabilities": {"tools": {}},
                },
            }
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"tools": [{"name": k} for k in self._tool_responses]},
            }
        if method == "tools/call":
            params = payload.get("params") or {}
            name = params.get("name", "")
            response = self._tool_responses.get(name)
            if response is None:
                return {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {"code": -32601, "message": f"tool not scripted: {name}"},
                }
            return {"jsonrpc": "2.0", "id": payload["id"], "result": response}
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "error": {"code": -32601, "message": f"method not scripted: {method}"},
        }

    def close(self) -> None:
        self.closed = True

    def calls_to(self, tool_name: str) -> List[Dict[str, Any]]:
        return [
            r for r in self.requests
            if r.get("method") == "tools/call"
            and (r.get("params") or {}).get("name") == tool_name
        ]


def _ok(tool_name: str, data: Any) -> Dict[str, Any]:
    """Shape a fake `tools/call` result the way the real MCP server does."""
    structured = {
        "tool": tool_name,
        "ok": True,
        "data": data,
        "capabilities": {},
        "timestamp": "2026-05-12T00:00:00Z",
    }
    return {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": structured,
    }


def _error(tool_name: str, code: str, message: str) -> Dict[str, Any]:
    structured = {
        "tool": tool_name,
        "ok": False,
        "code": code,
        "message": message,
        "capabilities": {},
    }
    return {
        "isError": True,
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": structured,
    }


class InitializeHandshakeTests(unittest.TestCase):
    def test_initialize_runs_once_and_caches(self) -> None:
        # Case 1 — every other call depends on a clean handshake, so we
        # verify the initialize payload shape and that we don't re-send.
        transport = FakeTransport({})
        client = PionexMCPClient(transport=transport)
        first = client.initialize()
        second = client.initialize()
        self.assertEqual(first, second)
        init_calls = [r for r in transport.requests if r["method"] == "initialize"]
        self.assertEqual(len(init_calls), 1)
        # Client info identifies BW-Trader so Pionex-side telemetry can
        # distinguish this caller from a human running the CLI.
        self.assertEqual(
            init_calls[0]["params"]["clientInfo"]["name"],
            "bw-trader",
        )


class ReadOnlyToolTests(unittest.TestCase):
    def test_get_klines_unwraps_data_field(self) -> None:
        # Case 2 — the MCP server wraps payloads as {tool, ok, data, ...}.
        # Callers shouldn't have to know that; the wrapper unwraps `data`.
        rows = [[1700000000000, "30000", "31000", "29500", "30500", "100"]]
        transport = FakeTransport({"pionex_market_get_klines": _ok("pionex_market_get_klines", rows)})
        client = PionexMCPClient(transport=transport)

        result = client.get_klines("BTC_USDT", interval="1H", limit=10)

        self.assertEqual(result, rows)
        sent = transport.calls_to("pionex_market_get_klines")
        self.assertEqual(len(sent), 1)
        self.assertEqual(
            sent[0]["params"]["arguments"],
            {"symbol": "BTC_USDT", "interval": "1H", "limit": 10},
        )

    def test_get_depth_no_auth_required(self) -> None:
        # Case 3 — market depth is a public endpoint; it must work even
        # when the wrapper has never seen a Pionex API key.
        payload = {"bids": [["30000", "1.0"]], "asks": [["30050", "0.5"]]}
        transport = FakeTransport({"pionex_market_get_depth": _ok("pionex_market_get_depth", payload)})
        client = PionexMCPClient(transport=transport)

        self.assertEqual(client.get_depth("BTC_USDT", limit=5), payload)

    def test_get_balance_with_auth(self) -> None:
        # Case 4 — auth-required read tool. The wrapper makes the call;
        # whether the upstream returns data or an auth error is the
        # server's job (covered by the next test).
        balance = {"balances": [{"coin": "USDT", "free": "1000.00"}]}
        transport = FakeTransport({"pionex_account_get_balance": _ok("pionex_account_get_balance", balance)})
        client = PionexMCPClient(transport=transport)

        self.assertEqual(client.get_balance(), balance)

    def test_get_balance_propagates_auth_error(self) -> None:
        # Case 5 — when the MCP server returns isError=true (e.g. auth
        # missing), the wrapper raises `PionexMCPError` rather than
        # silently returning empty data. Callers must see the failure.
        transport = FakeTransport({
            "pionex_account_get_balance": _error(
                "pionex_account_get_balance", "AUTH_MISSING", "API key not configured",
            ),
        })
        client = PionexMCPClient(transport=transport)

        with self.assertRaises(PionexMCPError) as ctx:
            client.get_balance()
        self.assertIn("AUTH_MISSING", str(ctx.exception))


class RedLineWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_allow = config.ALLOW_LIVE_TRADING

    def tearDown(self) -> None:
        config.ALLOW_LIVE_TRADING = self._orig_allow

    def test_new_order_without_consent_returns_403_without_touching_transport(self) -> None:
        # Case 6 — the most important test. A caller that forgets the
        # `user_consent=True` keyword must fail closed, and the failure
        # must happen before any JSON-RPC payload is constructed (so a
        # future real subprocess never sees the request).
        config.ALLOW_LIVE_TRADING = False
        transport = FakeTransport({})  # nothing scripted on purpose
        client = PionexMCPClient(transport=transport)

        with self.assertRaises(HTTPException) as ctx:
            client.new_order({"symbol": "BTC_USDT", "side": "BUY", "type": "MARKET", "amount": "10"})

        self.assertEqual(ctx.exception.status_code, 403)
        # No tools/call ever issued — the lock fired before initialize.
        self.assertEqual([r for r in transport.requests if r["method"] == "tools/call"], [])

    def test_new_order_with_consent_but_no_allow_live_trading_still_403(self) -> None:
        # Case 7 — second lock. Even with explicit user consent, if the
        # process-level kill switch is off, the wrapper refuses. This
        # catches the failure mode where a user is tricked into ticking
        # a box; the deploy still has to opt in.
        config.ALLOW_LIVE_TRADING = False
        transport = FakeTransport({})
        client = PionexMCPClient(transport=transport)

        with self.assertRaises(HTTPException) as ctx:
            client.new_order(
                {"symbol": "BTC_USDT", "side": "BUY", "type": "MARKET", "amount": "10"},
                user_consent=True,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("ALLOW_LIVE_TRADING=false", ctx.exception.detail)
        self.assertEqual([r for r in transport.requests if r["method"] == "tools/call"], [])

    def test_new_order_both_locks_open_reaches_transport(self) -> None:
        # Case 8 — the only path that should reach the upstream. Both
        # locks are explicitly open; the fake transport returns a stub
        # fill so we can confirm the args we sent were the args we got.
        config.ALLOW_LIVE_TRADING = True
        fill = {"orderId": "abc-123", "status": "FILLED"}
        transport = FakeTransport({"pionex_orders_new_order": _ok("pionex_orders_new_order", fill)})
        client = PionexMCPClient(transport=transport)

        result = client.new_order(
            {"symbol": "BTC_USDT", "side": "BUY", "type": "MARKET", "amount": "10"},
            user_consent=True,
        )

        self.assertEqual(result, fill)
        sent = transport.calls_to("pionex_orders_new_order")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["params"]["arguments"]["symbol"], "BTC_USDT")


class LifecycleTests(unittest.TestCase):
    def test_close_propagates_to_owned_transport(self) -> None:
        # Case 9 — when the wrapper owns the transport (production path,
        # injected=False), close() must shut down the subprocess.
        transport = FakeTransport({})
        client = PionexMCPClient(transport=transport)
        # Force owned-by-client to mirror production semantics even though
        # tests inject; this exercises the close path the FastAPI shutdown
        # hook will use.
        client._owns_transport = True
        client.close()
        self.assertTrue(transport.closed)

    def test_close_no_op_when_transport_injected(self) -> None:
        # Case 10 — injected transports belong to the caller (e.g. the
        # test harness); the wrapper must not close someone else's pipe.
        transport = FakeTransport({})
        client = PionexMCPClient(transport=transport)
        # default _owns_transport=False when transport is injected
        client.close()
        self.assertFalse(transport.closed)


if __name__ == "__main__":
    unittest.main()

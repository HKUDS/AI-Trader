"""Unit tests for the no-auto-trade red-line guard.

Covers four shapes the policy must hold:
  1. Paper-only payloads pass `assert_paper_only` without raising.
  2. Explicit `paper=false` payloads raise HTTP 403 (the user-facing surface
     of `LiveTradingDeniedError`).
  3. `reject_broker_webhook` always raises — the policy refuses to interpret
     any inbound webhook as a trade trigger.
  4. `queue_copy_trade_notification` returns a manual-execution payload
     instead of performing a trade.

These tests deliberately avoid spinning up the FastAPI app — they target
the policy primitives so a regression that bypasses the guard at the route
layer still gets caught at the unit layer.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi import HTTPException

import config
from security import (
    assert_paper_only,
    queue_copy_trade_notification,
    reject_broker_webhook,
)


class AssertPaperOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_allow = config.ALLOW_LIVE_TRADING
        config.ALLOW_LIVE_TRADING = False

    def tearDown(self) -> None:
        config.ALLOW_LIVE_TRADING = self._orig_allow

    def test_paper_true_dict_passes(self) -> None:
        # Default-allow path — paper=true must never raise.
        assert_paper_only({"paper": True, "symbol": "2330"})

    def test_missing_paper_flag_passes(self) -> None:
        # Absence of the flag is "unknown intent" — the guard only fires on
        # explicit `paper=false`. Routes that want strict default-deny should
        # set `paper: bool = True` on the request model.
        assert_paper_only({"symbol": "2330"})

    def test_paper_false_dict_raises_403(self) -> None:
        with self.assertRaises(HTTPException) as exc_ctx:
            assert_paper_only({"paper": False, "symbol": "2330"})
        self.assertEqual(exc_ctx.exception.status_code, 403)
        self.assertIn("paper-trading sandbox", exc_ctx.exception.detail)

    def test_paper_false_object_attribute_raises(self) -> None:
        class Payload:
            paper = False
            symbol = "2330"

        with self.assertRaises(HTTPException) as exc_ctx:
            assert_paper_only(Payload())
        self.assertEqual(exc_ctx.exception.status_code, 403)

    def test_allow_live_trading_override_bypasses_guard(self) -> None:
        config.ALLOW_LIVE_TRADING = True
        # No raise — the override is the documented escape hatch for the
        # eventual real-money path, which still needs additional review
        # before being wired up.
        assert_paper_only({"paper": False, "symbol": "2330"})


class RejectBrokerWebhookTests(unittest.TestCase):
    def test_always_raises(self) -> None:
        with self.assertRaises(HTTPException) as exc_ctx:
            reject_broker_webhook("fubon")
        self.assertEqual(exc_ctx.exception.status_code, 403)
        self.assertIn("fubon", exc_ctx.exception.detail)

    def test_raises_even_when_live_trading_enabled(self) -> None:
        orig = config.ALLOW_LIVE_TRADING
        config.ALLOW_LIVE_TRADING = True
        try:
            with self.assertRaises(HTTPException):
                reject_broker_webhook("ctbc")
        finally:
            config.ALLOW_LIVE_TRADING = orig


class CopyTradeNotificationTests(unittest.TestCase):
    def test_returns_manual_execution_payload(self) -> None:
        payload = queue_copy_trade_notification(
            follower_id=42,
            leader_id=7,
            signal_id=999,
            summary="Long 2330 @ 1010",
        )
        self.assertEqual(payload["type"], "copy_trade_notification")
        self.assertEqual(payload["follower_id"], 42)
        self.assertEqual(payload["leader_id"], 7)
        self.assertEqual(payload["execution_required"], "manual")
        self.assertEqual(payload["policy"], "no_auto_trade")

    def test_does_not_call_any_trade_function(self) -> None:
        # Sanity: the helper is a pure shaping function. If a future refactor
        # accidentally injects a side effect, this test stops being trivial —
        # which is the point.
        payload = queue_copy_trade_notification(1, 2, 3, "test")
        self.assertIsInstance(payload, dict)
        self.assertNotIn("filled", payload)
        self.assertNotIn("broker_order_id", payload)


class RegisterDefaultBalanceTests(unittest.TestCase):
    def test_default_balance_is_ntd_one_million(self) -> None:
        # Documents the cross-cutting choice: HKUDS upstream used USD $100K,
        # BW-Trader uses NT$1,000,000 so P&L percentages feel meaningful to
        # a Taiwan retail audience. Override is via DEFAULT_PAPER_BALANCE_NTD.
        self.assertEqual(config.DEFAULT_PAPER_BALANCE_NTD, 1_000_000.0)

    def test_agent_register_pydantic_default_matches_config(self) -> None:
        from routes_models import AgentRegister

        registration = AgentRegister(name="alice", password="hunter2")
        self.assertEqual(registration.initial_balance, config.DEFAULT_PAPER_BALANCE_NTD)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

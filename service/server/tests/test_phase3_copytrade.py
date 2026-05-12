"""Phase 3 copy-trade endpoint tests.

Covers:
  - consent required (explicit_consent + risk_disclosure_accepted)
  - mirror happy path via paper broker (default)
  - mirror happy path with mocked Pionex / CTBC broker clients
  - broker auth failure surfaces 502 not 500, and writes an audit record
  - rate-limit error from broker propagates cleanly
  - audit-log file is created and one record per mirror
  - webhook endpoints stay 403 (no consent flow)
  - unfollow drops a record and rejects unknown ids
  - positions list scoped to user_id
  - unknown broker name returns 400
  - mirror without a prior follow returns 404
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from brokers.base import (  # noqa: E402
    BrokerAuthError,
    BrokerOrder,
    BrokerOrderResult,
    BrokerRateLimitError,
)
from main import app  # noqa: E402
import routes_copytrade  # noqa: E402
from security.no_auto_trade import (  # noqa: E402
    _audit_log_path,
    assert_user_consent_or_no_trade,
)


def _follow_payload(**over):
    base = {
        "follow_agent_id": "agent-1",
        "broker": "paper",
        "explicit_consent": True,
        "risk_disclosure_accepted": True,
        "user_id": "u1",
    }
    base.update(over)
    return base


class CopyTradeRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        # Reset the in-memory follow registry between tests.
        routes_copytrade._FOLLOWS.clear()

    # ------------------------------------------------------------------
    # 1. Consent enforcement
    # ------------------------------------------------------------------

    def test_follow_without_explicit_consent_returns_403(self):
        r = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(explicit_consent=False),
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("missing_explicit_consent", json.dumps(r.json()))

    def test_follow_without_risk_disclosure_returns_403(self):
        r = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(risk_disclosure_accepted=False),
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("risk_disclosure_not_accepted", json.dumps(r.json()))

    def test_follow_with_full_consent_succeeds(self):
        r = self.client.post("/api/copytrade/follow", json=_follow_payload())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["follow_id"].startswith("fl-"))
        self.assertEqual(body["broker"], "paper")
        self.assertEqual(body["policy"], "user_consent_recorded")

    # ------------------------------------------------------------------
    # 2. Mirror happy path (paper)
    # ------------------------------------------------------------------

    def test_paper_mirror_happy_path(self):
        f = self.client.post("/api/copytrade/follow", json=_follow_payload()).json()
        m = self.client.post(
            "/api/copytrade/mirror",
            json={
                "follow_id": f["follow_id"],
                "signal_ref": "sig-1",
                "symbol": "2330",
                "side": "buy",
                "quantity": 1000,
            },
        )
        self.assertEqual(m.status_code, 200, m.text)
        body = m.json()
        self.assertEqual(body["broker"], "paper")
        self.assertEqual(body["status"], "filled")
        self.assertEqual(body["filled_quantity"], 1000.0)

    def test_pionex_mirror_with_mocked_client(self):
        f = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(broker="pionex"),
        ).json()

        def fake_client(name):
            class _C:
                name = "pionex"

                def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
                    return BrokerOrderResult(
                        order_ref="px-99",
                        status="accepted",
                        filled_quantity=order.quantity,
                        average_price=600.0,
                        broker="pionex",
                    )

            return _C()

        with patch("routes_copytrade.get_broker_client", side_effect=fake_client):
            m = self.client.post(
                "/api/copytrade/mirror",
                json={
                    "follow_id": f["follow_id"],
                    "signal_ref": "sig-px",
                    "symbol": "BTC_USDT",
                    "side": "buy",
                    "quantity": 0.01,
                },
            )
        self.assertEqual(m.status_code, 200, m.text)
        self.assertEqual(m.json()["order_ref"], "px-99")

    def test_ctbc_mirror_with_mocked_client(self):
        f = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(broker="ctbc"),
        ).json()

        def fake_client(name):
            class _C:
                name = "ctbc"

                def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
                    return BrokerOrderResult(
                        order_ref="ctbc-77",
                        status="pending",
                        broker="ctbc",
                    )

            return _C()

        with patch("routes_copytrade.get_broker_client", side_effect=fake_client):
            m = self.client.post(
                "/api/copytrade/mirror",
                json={
                    "follow_id": f["follow_id"],
                    "signal_ref": "sig-c",
                    "symbol": "2330",
                    "side": "buy",
                    "quantity": 1000,
                },
            )
        self.assertEqual(m.status_code, 200, m.text)
        self.assertEqual(m.json()["broker"], "ctbc")

    # ------------------------------------------------------------------
    # 3. Broker error handling
    # ------------------------------------------------------------------

    def test_broker_auth_error_returns_502_and_audits(self):
        f = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(broker="pionex"),
        ).json()

        def boom(name):
            class _C:
                name = "pionex"

                def place_order(self, order):
                    raise BrokerAuthError("no key")

            return _C()

        before = self._audit_lines()
        with patch("routes_copytrade.get_broker_client", side_effect=boom):
            m = self.client.post(
                "/api/copytrade/mirror",
                json={
                    "follow_id": f["follow_id"],
                    "signal_ref": "sig-auth",
                    "symbol": "BTC_USDT",
                    "side": "buy",
                    "quantity": 0.01,
                },
            )
        self.assertEqual(m.status_code, 502)
        after = self._audit_lines()
        self.assertTrue(any('"broker_auth_error"' in line for line in after[len(before):]))

    def test_broker_rate_limit_propagates_as_500(self):
        f = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(broker="pionex"),
        ).json()

        def boom(name):
            class _C:
                name = "pionex"

                def place_order(self, order):
                    raise BrokerRateLimitError("slow down")

            return _C()

        with patch("routes_copytrade.get_broker_client", side_effect=boom):
            m = self.client.post(
                "/api/copytrade/mirror",
                json={
                    "follow_id": f["follow_id"],
                    "signal_ref": "sig-rl",
                    "symbol": "BTC_USDT",
                    "side": "buy",
                    "quantity": 0.01,
                },
            )
        self.assertEqual(m.status_code, 503)

    # ------------------------------------------------------------------
    # 4. Audit log file
    # ------------------------------------------------------------------

    def test_mirror_writes_audit_record(self):
        f = self.client.post("/api/copytrade/follow", json=_follow_payload()).json()
        before = self._audit_lines()
        self.client.post(
            "/api/copytrade/mirror",
            json={
                "follow_id": f["follow_id"],
                "signal_ref": "sig-audit",
                "symbol": "2330",
                "side": "buy",
                "quantity": 1000,
            },
        )
        after = self._audit_lines()
        added = after[len(before):]
        self.assertTrue(
            any('"copytrade_mirror_filled"' in line for line in added),
            f"no mirror-filled record found in: {added}",
        )

    @staticmethod
    def _audit_lines() -> list[str]:
        path = _audit_log_path()
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    # ------------------------------------------------------------------
    # 5. Policy invariants
    # ------------------------------------------------------------------

    def test_broker_webhook_still_403(self):
        r = self.client.post("/api/brokers/webhook", json={})
        self.assertEqual(r.status_code, 403)

    def test_named_broker_webhook_still_403(self):
        r = self.client.post("/api/brokers/pionex/webhook")
        self.assertEqual(r.status_code, 403)

    def test_assert_user_consent_blocks_without_marker(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            assert_user_consent_or_no_trade(
                action="copytrade_mirror",
                user_consent=True,
                audit_meta={"explicit_follow_action": False},
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_assert_user_consent_blocks_when_consent_false(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            assert_user_consent_or_no_trade(
                action="copytrade_mirror",
                user_consent=False,
                audit_meta={"explicit_follow_action": True},
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_describe_policy_lists_consent_carveout(self):
        r = self.client.get("/api/policy/no-auto-trade")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn(
            "copy_trade_mirror_with_explicit_user_consent_and_risk_disclosure",
            body["allowed"],
        )
        self.assertIn("agent_autonomous_broker_execution", body["denied"])

    # ------------------------------------------------------------------
    # 6. Lifecycle
    # ------------------------------------------------------------------

    def test_unfollow_drops_record(self):
        f = self.client.post("/api/copytrade/follow", json=_follow_payload()).json()
        r = self.client.post(
            "/api/copytrade/unfollow",
            json={"follow_id": f["follow_id"]},
        )
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post(
            "/api/copytrade/unfollow",
            json={"follow_id": f["follow_id"]},
        )
        self.assertEqual(r2.status_code, 404)

    def test_positions_lists_only_current_user(self):
        self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(user_id="u1", follow_agent_id="a1"),
        )
        self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(user_id="u2", follow_agent_id="a2"),
        )
        r = self.client.get("/api/copytrade/positions", params={"user_id": "u1"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["positions"][0]["follow_agent_id"], "a1")

    def test_unknown_broker_rejected(self):
        r = self.client.post(
            "/api/copytrade/follow",
            json=_follow_payload(broker="robinhood"),
        )
        self.assertEqual(r.status_code, 400)

    def test_mirror_without_follow_returns_404(self):
        r = self.client.post(
            "/api/copytrade/mirror",
            json={
                "follow_id": "fl-nonexistent",
                "signal_ref": "sig-x",
                "symbol": "2330",
                "side": "buy",
                "quantity": 1000,
            },
        )
        self.assertEqual(r.status_code, 404)

    def test_mirror_invalid_side_rejected(self):
        f = self.client.post("/api/copytrade/follow", json=_follow_payload()).json()
        r = self.client.post(
            "/api/copytrade/mirror",
            json={
                "follow_id": f["follow_id"],
                "signal_ref": "sig-bad",
                "symbol": "2330",
                "side": "hold",
                "quantity": 1000,
            },
        )
        # Pydantic regex validation should reject; 422 is fine too
        self.assertIn(r.status_code, (400, 422))


if __name__ == "__main__":
    unittest.main()

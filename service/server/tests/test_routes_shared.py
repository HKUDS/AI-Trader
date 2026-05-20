import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from fastapi import HTTPException
from routes_shared import (
    attach_experiment_unread_notice,
    normalize_market,
    should_fetch_server_trade_price,
    utc_now_iso_z,
    validate_market,
)


class TradePriceSourceTests(unittest.TestCase):
    def test_supported_trade_markets_always_use_server_prices(self) -> None:
        with patch.dict(os.environ, {'ALLOW_SYNC_PRICE_FETCH_IN_API': 'false'}, clear=False):
            self.assertTrue(should_fetch_server_trade_price('crypto'))
            self.assertTrue(should_fetch_server_trade_price('binance'))
            self.assertTrue(should_fetch_server_trade_price('polymarket'))
            self.assertTrue(should_fetch_server_trade_price('us-stock'))

    def test_env_flag_keeps_server_fetch_for_unknown_markets(self) -> None:
        with patch.dict(os.environ, {'ALLOW_SYNC_PRICE_FETCH_IN_API': 'true'}, clear=False):
            self.assertTrue(should_fetch_server_trade_price('custom-market'))

    def test_market_aliases_normalize_to_supported_markets(self) -> None:
        self.assertEqual(normalize_market('binance'), 'crypto')
        self.assertEqual(normalize_market('kraken'), 'crypto')
        self.assertEqual(normalize_market('OKX'), 'crypto')
        self.assertEqual(normalize_market('US Stock'), 'us-stock')
        self.assertEqual(normalize_market('NASDAQ'), 'us-stock')
        self.assertEqual(validate_market('stock'), 'us-stock')

    def test_unknown_market_is_rejected(self) -> None:
        with self.assertRaises(HTTPException):
            validate_market('forex')


class ExperimentUnreadNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = self._create_agent("notice-agent")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str) -> int:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES (?, ?, 0, 100000.0, ?, ?)
            """,
            (name, f"token-{name}", utc_now_iso_z(), utc_now_iso_z()),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _insert_message(self, message_type: str, read: int = 0) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_messages (agent_id, type, content, data, read, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.agent_id,
                message_type,
                f"{message_type} content",
                '{"campaign_id":"unit"}',
                read,
                utc_now_iso_z(),
            ),
        )
        conn.commit()
        conn.close()

    def test_attach_experiment_unread_notice_is_non_destructive(self) -> None:
        self._insert_message("experiment_reminder")
        self._insert_message("discussion_reply")
        payload = attach_experiment_unread_notice({"success": True}, self.agent_id)

        notice = payload["experiment_unread"]
        self.assertEqual(notice["unread_count"], 1)
        self.assertFalse(notice["requires_read"])
        self.assertEqual(notice["read_receipts_role"], "diagnostic_only")
        self.assertFalse(notice["message_read_state_required"])
        self.assertEqual(notice["recommended_action"]["endpoint"], "/api/claw/messages/read-experiment")
        self.assertEqual(notice["recommended_action"]["method"], "POST")
        self.assertIn("read_experiment_messages", [action["name"] for action in notice["actions"]])
        self.assertIn("read_and_mark_via_heartbeat", [action["name"] for action in notice["actions"]])
        self.assertEqual(notice["mark_read_endpoint"]["body"], {"categories": ["experiment"]})
        self.assertEqual(notice["messages"][0]["type"], "experiment_reminder")
        self.assertIn("read_experiment", notice["read_via"])
        self.assertIn("heartbeat", notice["read_via"])
        self.assertTrue(payload["agent_notice"]["experiment_unread"])
        self.assertFalse(payload["agent_notice"]["must_call_now"])
        self.assertEqual(payload["agent_notice"]["must_call"], "/api/claw/messages/read-experiment")
        self.assertEqual(payload["agent_notice"]["must_call_method"], "POST")
        self.assertEqual(payload["agent_notice"]["primary_metric_family"], "active_agent_behavior")
        self.assertEqual(payload["agent_notice"]["read_receipts_role"], "diagnostic_only")
        self.assertFalse(payload["agent_notice"]["message_read_state_required"])
        self.assertEqual(
            payload["agent_notice"]["required_action"]["endpoint"],
            "/api/claw/messages/read-experiment",
        )
        self.assertEqual(payload["agent_notice"]["unread_count"], 1)
        self.assertEqual(
            payload["agent_notice"]["recommended_action"]["endpoint"],
            "/api/claw/messages/read-experiment",
        )

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT read FROM agent_messages WHERE agent_id = ? AND type = 'experiment_reminder'",
            (self.agent_id,),
        )
        self.assertEqual(cursor.fetchone()["read"], 0)
        conn.close()

    def test_attach_experiment_unread_notice_records_exposure(self) -> None:
        self._insert_message("experiment_reminder")
        payload = attach_experiment_unread_notice(
            {"success": True},
            self.agent_id,
            surface="unit_test_surface",
        )

        self.assertIn("experiment_unread", payload)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT actor_agent_id, object_type, object_id, metadata_json
            FROM experiment_events
            WHERE event_type = 'experiment_notice_exposed'
            """
        )
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["actor_agent_id"], self.agent_id)
        self.assertEqual(row["object_type"], "agent")
        self.assertEqual(row["object_id"], str(self.agent_id))
        self.assertIn("unit_test_surface", row["metadata_json"])
        self.assertIn("experiment_reminder", row["metadata_json"])

    def test_attach_experiment_unread_notice_omits_empty_notice(self) -> None:
        self._insert_message("experiment_reminder", read=1)
        payload = attach_experiment_unread_notice({"success": True}, self.agent_id)

        self.assertNotIn("experiment_unread", payload)


if __name__ == '__main__':
    unittest.main()

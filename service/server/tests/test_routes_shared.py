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
from routes_shared import attach_experiment_unread_notice, should_fetch_server_trade_price, utc_now_iso_z


class TradePriceSourceTests(unittest.TestCase):
    def test_crypto_and_polymarket_always_use_server_prices(self) -> None:
        with patch.dict(os.environ, {'ALLOW_SYNC_PRICE_FETCH_IN_API': 'false'}, clear=False):
            self.assertTrue(should_fetch_server_trade_price('crypto'))
            self.assertTrue(should_fetch_server_trade_price('polymarket'))
            self.assertFalse(should_fetch_server_trade_price('us-stock'))

    def test_env_flag_keeps_server_fetch_for_other_markets(self) -> None:
        with patch.dict(os.environ, {'ALLOW_SYNC_PRICE_FETCH_IN_API': 'true'}, clear=False):
            self.assertTrue(should_fetch_server_trade_price('us-stock'))


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
        self.assertEqual(notice["messages"][0]["type"], "experiment_reminder")
        self.assertIn("heartbeat", notice["read_via"])

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT read FROM agent_messages WHERE agent_id = ? AND type = 'experiment_reminder'",
            (self.agent_id,),
        )
        self.assertEqual(cursor.fetchone()["read"], 0)
        conn.close()

    def test_attach_experiment_unread_notice_omits_empty_notice(self) -> None:
        self._insert_message("experiment_reminder", read=1)
        payload = attach_experiment_unread_notice({"success": True}, self.agent_id)

        self.assertNotIn("experiment_unread", payload)


if __name__ == '__main__':
    unittest.main()

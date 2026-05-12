import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from experiments import create_experiment
from routes import create_app
from routes_shared import utc_now_iso_z


class ExperimentEventRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.author_id = self._create_agent("author-agent", "token-author")
        self.reply_agent_id = self._create_agent("reply-agent", "token-reply")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, token: str) -> int:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES (?, ?, 0, 100000.0, ?, ?)
            """,
            (name, token, utc_now_iso_z(), utc_now_iso_z()),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_strategy_discussion_reply_and_accept_write_events_with_json_metadata(self):
        create_experiment({
            "experiment_key": "event-context",
            "title": "Event context",
            "variants_json": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
        })

        strategy_res = self.client.post(
            "/api/signals/strategy",
            headers={"Authorization": "Bearer token-author"},
            json={
                "market": "crypto",
                "title": "BTC breakout target 120000",
                "content": "BTC long because momentum confirms, target price 120000, confidence 70 percent.",
                "symbols": "BTC",
                "tags": "breakout,evidence",
            },
        )
        self.assertEqual(strategy_res.status_code, 200, strategy_res.text)
        strategy_signal_id = strategy_res.json()["signal_id"]

        discussion_res = self.client.post(
            "/api/signals/discussion",
            headers={"Authorization": "Bearer token-author"},
            json={
                "market": "crypto",
                "symbol": "ETH",
                "title": "ETH risk check",
                "content": "ETH downside risk if funding turns negative.",
                "tags": "risk",
            },
        )
        self.assertEqual(discussion_res.status_code, 200, discussion_res.text)

        reply_res = self.client.post(
            "/api/signals/reply",
            headers={"Authorization": "Bearer token-reply"},
            json={"signal_id": strategy_signal_id, "content": "I agree and add volume confirmation."},
        )
        self.assertEqual(reply_res.status_code, 200, reply_res.text)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM signal_replies WHERE signal_id = ?", (strategy_signal_id,))
        reply_id = cursor.fetchone()["id"]
        conn.close()

        accept_res = self.client.post(
            f"/api/signals/{strategy_signal_id}/replies/{reply_id}/accept",
            headers={"Authorization": "Bearer token-author"},
        )
        self.assertEqual(accept_res.status_code, 200, accept_res.text)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT event_type, metadata_json FROM experiment_events ORDER BY id")
        rows = [dict(row) for row in cursor.fetchall()]
        event_types = [row["event_type"] for row in rows]
        self.assertGreaterEqual(event_types.count("signal_published"), 2)
        self.assertIn("reply_created", event_types)
        self.assertIn("reply_accepted", event_types)
        self.assertIn("reward_granted", event_types)
        for row in rows:
            if row["metadata_json"]:
                self.assertIsInstance(json.loads(row["metadata_json"]), dict)
        cursor.execute("SELECT COUNT(*) AS count FROM signal_predictions")
        self.assertGreaterEqual(cursor.fetchone()["count"], 2)
        cursor.execute("SELECT COUNT(*) AS count FROM signal_quality_scores")
        self.assertGreaterEqual(cursor.fetchone()["count"], 2)
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM experiment_events
            WHERE event_type IN ('signal_published', 'reply_created', 'reply_accepted')
              AND experiment_key = 'event-context'
              AND variant_key IS NOT NULL
            """
        )
        self.assertGreaterEqual(cursor.fetchone()["count"], 4)
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM agent_reward_ledger
            WHERE reason IN ('publish_strategy', 'publish_discussion', 'publish_reply', 'reply_accepted')
              AND experiment_key = 'event-context'
              AND variant_key IS NOT NULL
            """
        )
        self.assertGreaterEqual(cursor.fetchone()["count"], 4)
        conn.close()


if __name__ == "__main__":
    unittest.main()

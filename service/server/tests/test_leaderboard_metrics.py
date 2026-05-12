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
from routes import create_app
from routes_shared import utc_now_iso_z


class LeaderboardMetricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, cash: float) -> int:
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?, ?)
            """,
            (name, f"token-{name}", cash, now, now),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _insert_metric_snapshot(self, agent_id: int, *, quality_score_avg: float = 0) -> None:
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_metric_snapshots
            (agent_id, window_key, window_start_at, window_end_at, return_pct,
             max_drawdown, trade_count, strategy_count, discussion_count,
             reply_count, accepted_reply_count, citation_count, adoption_count,
             quality_score_avg, risk_violation_count, metadata_json, created_at)
            VALUES (?, '7d', ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, 0, '{}', ?)
            """,
            (agent_id, now, now, quality_score_avg, now),
        )
        conn.commit()
        conn.close()

    def test_quality_metric_sorts_before_pagination(self):
        high_return_agent = self._create_agent("high-return-low-quality", 200000.0)
        high_quality_agent = self._create_agent("high-quality-low-return", 100000.0)
        self._insert_metric_snapshot(high_return_agent, quality_score_avg=0)
        self._insert_metric_snapshot(high_quality_agent, quality_score_avg=5)

        response = self.client.get("/api/profit/history?limit=1&offset=0&metric=quality&include_history=false")

        self.assertEqual(response.status_code, 200, response.text)
        top_agents = response.json()["top_agents"]
        self.assertEqual(len(top_agents), 1)
        self.assertEqual(top_agents[0]["name"], "high-quality-low-return")
        self.assertEqual(top_agents[0]["quality_score_avg"], 5)


if __name__ == "__main__":
    unittest.main()

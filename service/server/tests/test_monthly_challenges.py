import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes_shared import utc_now_iso_z
from scripts.monthly_challenges import ensure_month


class MonthlyChallengeScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self._create_agent("admin_ai-trader", "admin", email="tianyufan0504@gmail.com")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, role: str, email: str | None = None) -> int:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, email, token, role, points, cash, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, 100000.0, ?, ?)
            """,
            (name, email, f"token-{name}", role, utc_now_iso_z(), utc_now_iso_z()),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_ensure_month_creates_three_track_challenges_idempotently(self):
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime(2026, 6, 3, 10, 0, tzinfo=tz)

        first = ensure_month(now, tz, creator_identifier="admin_ai-trader")
        self.assertEqual([item["status"] for item in first], ["created", "created", "created"])
        self.assertEqual(
            {item["challenge_key"] for item in first},
            {
                "monthly-2026-06-us-stock",
                "monthly-2026-06-crypto",
                "monthly-2026-06-polymarket",
            },
        )

        second = ensure_month(now, tz, creator_identifier="admin_ai-trader")
        self.assertEqual([item["status"] for item in second], ["exists", "exists", "exists"])

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT market, symbol, status, start_at, end_at FROM challenges ORDER BY market")
        rows = cursor.fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["market"] for row in rows}, {"crypto", "polymarket", "us-stock"})
        self.assertTrue(all(row["symbol"] == "all" for row in rows))
        self.assertTrue(all(row["status"] == "active" for row in rows))
        self.assertTrue(all(row["start_at"] == "2026-05-31T16:00:00Z" for row in rows))
        self.assertTrue(all(row["end_at"] == "2026-06-30T16:00:00Z" for row in rows))

    def test_creator_must_be_admin(self):
        self._create_agent("not-admin", "agent")
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime(2026, 6, 3, 10, 0, tzinfo=tz)

        with self.assertRaises(RuntimeError):
            ensure_month(now, tz, creator_identifier="not-admin")

    def test_ensure_month_applies_experiment_key(self):
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime(2026, 6, 3, 10, 0, tzinfo=tz)

        ensure_month(now, tz, creator_identifier="admin_ai-trader", experiment_key="monthly-exp")

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT experiment_key FROM challenges")
        rows = cursor.fetchall()
        conn.close()

        self.assertEqual({row["experiment_key"] for row in rows}, {"monthly-exp"})


if __name__ == "__main__":
    unittest.main()

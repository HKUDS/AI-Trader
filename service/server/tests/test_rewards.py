import os
import sys
import tempfile
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from rewards import grant_agent_reward, reverse_agent_reward
from routes_shared import utc_now_iso_z


class RewardLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = self._create_agent("reward-agent")

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

    def test_grant_reward_writes_ledger_updates_points_and_reverse_reverts(self):
        granted = grant_agent_reward(
            self.agent_id,
            25,
            "unit_test_reward",
            source_type="test",
            source_id="reward-1",
            metadata={"case": "grant"},
        )
        self.assertTrue(granted["success"])

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT points FROM agents WHERE id = ?", (self.agent_id,))
        self.assertEqual(cursor.fetchone()["points"], 25)
        cursor.execute("SELECT * FROM agent_reward_ledger WHERE id = ?", (granted["ledger_id"],))
        ledger = cursor.fetchone()
        self.assertEqual(ledger["amount"], 25)
        self.assertEqual(ledger["status"], "posted")
        cursor.execute("SELECT COUNT(*) AS count FROM experiment_events WHERE event_type = 'reward_granted'")
        self.assertEqual(cursor.fetchone()["count"], 1)
        conn.close()

        reversed_result = reverse_agent_reward(granted["ledger_id"], reason="unit_test_reverse")
        self.assertTrue(reversed_result["reversed"])

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT points FROM agents WHERE id = ?", (self.agent_id,))
        self.assertEqual(cursor.fetchone()["points"], 0)
        cursor.execute("SELECT status, reversed_at FROM agent_reward_ledger WHERE id = ?", (granted["ledger_id"],))
        ledger = cursor.fetchone()
        self.assertEqual(ledger["status"], "unit_test_reverse")
        self.assertTrue(ledger["reversed_at"])
        cursor.execute("SELECT COUNT(*) AS count FROM experiment_events WHERE event_type = 'reward_reversed'")
        self.assertEqual(cursor.fetchone()["count"], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()

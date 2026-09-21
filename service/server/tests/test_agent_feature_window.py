import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from team_matching import _agent_feature


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AgentFeatureReturnWindowTests(unittest.TestCase):
    """return_pct_30d must cover 30 days, like the counts next to it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.now = datetime.now(timezone.utc)
        self.conn = database.get_db_connection()
        self.cursor = self.conn.cursor()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _agent(self, agent_id: int, history: list) -> None:
        self.cursor.execute(
            "INSERT INTO agents (id, name, token, cash) VALUES (?, ?, ?, 100000.0)",
            (agent_id, f"agent-{agent_id}", f"token-{agent_id}"),
        )
        for days_ago, profit in history:
            self.cursor.execute(
                """
                INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
                VALUES (?, ?, ?, 0.0, ?, ?)
                """,
                (
                    agent_id,
                    100000.0 + profit,
                    100000.0 + profit,
                    profit,
                    _iso(self.now - timedelta(days=days_ago)),
                ),
            )
        self.conn.commit()

    def test_a_gain_older_than_the_window_is_not_counted(self) -> None:
        self._agent(1, [(90, 40000.0), (20, 40000.0), (1, 40000.0)])

        self.assertAlmostEqual(_agent_feature(self.cursor, 1)["return_pct_30d"], 0.0, places=4)

    def test_a_loss_inside_the_window_is_counted(self) -> None:
        self._agent(2, [(90, 40000.0), (20, 40000.0), (1, 30000.0)])

        self.assertAlmostEqual(_agent_feature(self.cursor, 2)["return_pct_30d"], -7.1429, places=4)

    def test_a_gain_inside_the_window_is_counted(self) -> None:
        self._agent(3, [(20, 0.0), (1, 10000.0)])

        self.assertAlmostEqual(_agent_feature(self.cursor, 3)["return_pct_30d"], 10.0, places=4)

    def test_an_agent_without_history_reports_zero(self) -> None:
        self._agent(4, [])

        self.assertAlmostEqual(_agent_feature(self.cursor, 4)["return_pct_30d"], 0.0, places=4)


if __name__ == "__main__":
    unittest.main()

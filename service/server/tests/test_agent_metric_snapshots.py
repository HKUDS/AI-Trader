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
from experiment_metrics import refresh_agent_metric_snapshots


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AgentMetricSnapshotWindowTests(unittest.TestCase):
    """return_pct must describe the snapshot window, like max_drawdown does."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _agent(self, agent_id: int, name: str, history: list) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO agents (id, name, token, cash) VALUES (?, ?, ?, 100000.0)",
            (agent_id, name, f"token-{agent_id}"),
        )
        for days_ago, profit in history:
            cursor.execute(
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
        conn.commit()
        conn.close()

    def _snapshots(self) -> dict:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT agent_id, return_pct, max_drawdown FROM agent_metric_snapshots")
        rows = {int(row["agent_id"]): dict(row) for row in cursor.fetchall()}
        conn.close()
        return rows

    def test_return_pct_covers_the_window_only(self) -> None:
        # flat inside the window, all of the gain predates it
        self._agent(1, "flat-after-old-gain", [(30, 40000.0), (6, 40000.0), (1, 40000.0)])
        # same old gain, but down 10000 inside the window
        self._agent(2, "losing-inside-window", [(30, 40000.0), (6, 40000.0), (1, 30000.0)])
        # control: the whole gain happens inside the window
        self._agent(3, "gaining-inside-window", [(6, 0.0), (1, 10000.0)])

        refresh_agent_metric_snapshots(window_days=7)
        snapshots = self._snapshots()

        self.assertAlmostEqual(snapshots[1]["return_pct"], 0.0, places=4)
        self.assertAlmostEqual(snapshots[2]["return_pct"], -7.1429, places=4)
        self.assertAlmostEqual(snapshots[3]["return_pct"], 10.0, places=4)

    def test_max_drawdown_is_unchanged(self) -> None:
        self._agent(1, "flat-after-old-gain", [(30, 40000.0), (6, 40000.0), (1, 40000.0)])
        self._agent(2, "losing-inside-window", [(30, 40000.0), (6, 40000.0), (1, 30000.0)])

        refresh_agent_metric_snapshots(window_days=7)
        snapshots = self._snapshots()

        self.assertAlmostEqual(snapshots[1]["max_drawdown"], 0.0, places=4)
        self.assertAlmostEqual(snapshots[2]["max_drawdown"], 7.1429, places=4)

    def test_an_agent_without_history_in_the_window_reports_zero(self) -> None:
        self._agent(1, "no-rows-in-window", [(30, 40000.0)])

        refresh_agent_metric_snapshots(window_days=7)

        self.assertAlmostEqual(self._snapshots()[1]["return_pct"], 0.0, places=4)


if __name__ == "__main__":
    unittest.main()

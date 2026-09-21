import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient

import database
from routes import create_app
from team_matching import _agent_feature


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ThirtyDayWindowBoundaryTests(unittest.TestCase):
    """A row older than the window must not be counted, whatever time of day it carries."""

    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        if self.now.hour == 0 and self.now.minute < 2:
            self.skipTest("run starts within two minutes of midnight UTC, the boundary case is ambiguous")
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.conn = database.get_db_connection()
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            "INSERT INTO agents (id, name, token, cash) VALUES (1, 'boundary-agent', 'token-boundary', 100000.0)"
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _signal(self, signal_id: int, created_at: datetime) -> None:
        self.cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, content, timestamp, created_at)
            VALUES (?, 1, 'operation', 'crypto', 'realtime', 'BTC', 'trade', 0, ?)
            """,
            (signal_id, _iso(created_at)),
        )
        self.conn.commit()

    def test_a_row_from_the_boundary_day_but_before_the_cutoff_is_excluded(self) -> None:
        boundary_day = (self.now - timedelta(days=30)).replace(hour=0, minute=0, second=1, microsecond=0)
        self._signal(1, boundary_day)

        self.assertEqual(_agent_feature(self.cursor, 1)["trade_count_30d"], 0)

    def test_a_row_inside_the_window_is_counted(self) -> None:
        self._signal(2, self.now - timedelta(days=29))

        self.assertEqual(_agent_feature(self.cursor, 1)["trade_count_30d"], 1)

    def test_a_row_well_outside_the_window_is_excluded(self) -> None:
        self._signal(3, self.now - timedelta(days=31))

        self.assertEqual(_agent_feature(self.cursor, 1)["trade_count_30d"], 0)


class SubscriptionActivityWindowTests(unittest.TestCase):
    """The 7 day counters on the subscription routes must use the same cutoff."""

    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        if self.now.hour == 0 and self.now.minute < 2:
            self.skipTest("run starts within two minutes of midnight UTC, the boundary case is ambiguous")
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        for agent_id, name in ((1, "leader"), (2, "follower")):
            cursor.execute(
                "INSERT INTO agents (id, name, token, cash) VALUES (?, ?, ?, 100000.0)",
                (agent_id, name, f"token-{name}"),
            )
        cursor.execute(
            "INSERT INTO subscriptions (follower_id, leader_id, status) VALUES (2, 1, 'active')"
        )
        boundary_day = (self.now - timedelta(days=7)).replace(hour=0, minute=0, second=1, microsecond=0)
        for signal_id, agent_id, created_at in (
            (1, 1, boundary_day),
            (2, 1, self.now - timedelta(days=6)),
            (3, 2, boundary_day),
            (4, 2, self.now - timedelta(days=6)),
        ):
            cursor.execute(
                """
                INSERT INTO signals
                (signal_id, agent_id, message_type, market, signal_type, symbol, content, timestamp, created_at)
                VALUES (?, ?, 'operation', 'crypto', 'realtime', 'BTC', 'trade', 0, ?)
                """,
                (signal_id, agent_id, _iso(created_at)),
            )
        conn.commit()
        conn.close()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_following_counts_only_the_last_seven_days(self) -> None:
        response = self.client.get(
            "/api/signals/following", headers={"Authorization": "Bearer token-follower"}
        )

        self.assertEqual(response.status_code, 200, response.text)
        following = response.json()["following"]
        self.assertEqual(len(following), 1)
        self.assertEqual(following[0]["recent_trade_count_7d"], 1)

    def test_subscribers_counts_only_the_last_seven_days(self) -> None:
        response = self.client.get(
            "/api/signals/subscribers", headers={"Authorization": "Bearer token-leader"}
        )

        self.assertEqual(response.status_code, 200, response.text)
        subscribers = response.json()["subscribers"]
        self.assertEqual(len(subscribers), 1)
        self.assertEqual(subscribers[0]["recent_trade_count_7d"], 1)


if __name__ == "__main__":
    unittest.main()

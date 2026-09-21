import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app
from routes_shared import utc_now_iso_z


class RealtimeOppositeSideGuardTests(unittest.TestCase):
    """A trade must never open a second positions row for the same symbol."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = self._create_agent()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self) -> int:
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES ('opposite-side-agent', 'token-opposite-side', 0, 100000.0, ?, ?)
            """,
            (now, now),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _create_follower(self) -> int:
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES ('opposite-side-follower', 'token-follower', 0, 100000.0, ?, ?)
            """,
            (now, now),
        )
        follower_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return follower_id

    def _subscribe(self, follower_id: int) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO subscriptions (follower_id, leader_id, status) VALUES (?, ?, 'active')",
            (follower_id, self.agent_id),
        )
        conn.commit()
        conn.close()

    def _trade(self, action: str, quantity: float, price: float, token: str = "token-opposite-side") -> object:
        with patch("routes_signals.is_market_open", return_value=True), \
             patch("price_fetcher.get_price_from_market", return_value=price):
            return self.client.post(
                "/api/signals/realtime",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "market": "us-stock",
                    "symbol": "TSLA",
                    "action": action,
                    "quantity": quantity,
                    "price": price,
                    "content": f"{action} TSLA",
                    "executed_at": "2026-05-19T14:00:00Z",
                },
            )

    def _positions(self, agent_id: int = None) -> list:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT side, quantity FROM positions WHERE agent_id = ? ORDER BY id",
            (agent_id if agent_id is not None else self.agent_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def _cash(self) -> float:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
        cash = float(cursor.fetchone()["cash"])
        conn.close()
        return cash

    def test_buy_while_short_is_rejected_and_leaves_one_row(self) -> None:
        self.assertEqual(self._trade("short", 10, 100.0).status_code, 200)
        cash_after_short = self._cash()

        response = self._trade("buy", 10, 120.0)

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("short position is open", response.json()["detail"])
        self.assertEqual(self._positions(), [{"side": "short", "quantity": -10.0}])
        self.assertEqual(self._cash(), cash_after_short)

    def test_short_while_long_is_rejected_and_leaves_one_row(self) -> None:
        self.assertEqual(self._trade("buy", 10, 100.0).status_code, 200)
        cash_after_buy = self._cash()

        response = self._trade("short", 10, 120.0)

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("long position is open", response.json()["detail"])
        self.assertEqual(self._positions(), [{"side": "long", "quantity": 10.0}])
        self.assertEqual(self._cash(), cash_after_buy)

    def test_buy_without_an_opposite_position_still_succeeds(self) -> None:
        self.assertEqual(self._trade("buy", 10, 100.0).status_code, 200)

        response = self._trade("buy", 5, 120.0)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._positions(), [{"side": "long", "quantity": 15.0}])

    def test_a_follower_holding_the_opposite_side_is_skipped_not_fatal(self) -> None:
        follower_id = self._create_follower()
        self._subscribe(follower_id)
        self.assertEqual(self._trade("buy", 10, 100.0, token="token-follower").status_code, 200)

        response = self._trade("short", 10, 120.0)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["follower_count"], 0)
        self.assertEqual(self._positions(), [{"side": "short", "quantity": -10.0}])
        self.assertEqual(self._positions(follower_id), [{"side": "long", "quantity": 10.0}])


if __name__ == "__main__":
    unittest.main()

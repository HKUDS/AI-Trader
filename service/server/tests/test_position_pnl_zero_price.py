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


class ZeroPricePnlTests(unittest.TestCase):
    """Regression: a valid current_price of 0.0 must not be treated as 'no price'.

    Polymarket outcome tokens resolve to exactly 0.0 when the outcome loses.
    The PnL endpoints previously guarded with `if current_price and ...`, so a
    0.0 price was falsy and the position's (fully realized) loss was silently
    dropped, overstating position PnL and leaderboard rank. The authoritative
    leaderboard SQL distinguishes NULL from 0.0, so the Python endpoints must too.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, cash: float = 100000.0) -> int:
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

    def _insert_position(self, agent_id, *, entry_price, current_price, quantity, side="long"):
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO positions
            (agent_id, symbol, market, token_id, outcome, side, quantity, entry_price, current_price, opened_at)
            VALUES (?, 'WINYES', 'polymarket', 'tok-1', 'Yes', ?, ?, ?, ?, ?)
            """,
            (agent_id, side, quantity, entry_price, current_price, now),
        )
        conn.commit()
        conn.close()

    def test_zero_current_price_loss_is_counted(self):
        # Long 100 tokens bought at 0.60; outcome lost so the token now trades at 0.0.
        # Expected PnL = (0.0 - 0.60) * 100 = -60.0 (a full loss), not 0.
        agent_id = self._create_agent("loser")
        self._insert_position(agent_id, entry_price=0.60, current_price=0.0, quantity=100)

        resp = self.client.get("/api/leaderboard/position-pnl")
        self.assertEqual(resp.status_code, 200)
        rows = {r["agent_id"]: r for r in resp.json()["top_agents"]}
        self.assertAlmostEqual(rows[agent_id]["position_pnl"], -60.0, places=6)

        resp = self.client.get(f"/api/agents/{agent_id}/positions")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertAlmostEqual(body["total_pnl"], -60.0, places=6)
        self.assertAlmostEqual(body["positions"][0]["pnl"], -60.0, places=6)


if __name__ == "__main__":
    unittest.main()

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


class RealtimeTradePriceGuardTests(unittest.TestCase):
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
            VALUES ('price-guard-agent', 'token-price-guard', 0, 100000.0, ?, ?)
            """,
            (now, now),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _trade_payload(self) -> dict:
        return {
            "market": "us-stock",
            "symbol": "TSLA",
            "action": "buy",
            "quantity": 10,
            "price": 10,
            "content": "Attempt to submit a stale client-side price.",
            "executed_at": "2026-05-19T14:00:00Z",
        }

    def _counts_and_cash(self) -> tuple[int, int, float]:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM signals")
        signal_count = int(cursor.fetchone()["count"])
        cursor.execute("SELECT COUNT(*) AS count FROM positions")
        position_count = int(cursor.fetchone()["count"])
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
        cash = float(cursor.fetchone()["cash"])
        conn.close()
        return signal_count, position_count, cash

    def test_us_stock_trade_rejects_client_price_when_server_quote_unavailable(self) -> None:
        with patch("routes_signals.is_market_open", return_value=True), \
             patch("price_fetcher.get_price_from_market", return_value=None):
            response = self.client.post(
                "/api/signals/realtime",
                headers={"Authorization": "Bearer token-price-guard"},
                json=self._trade_payload(),
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Unable to fetch historical price for TSLA", response.json()["detail"])
        self.assertEqual(self._counts_and_cash(), (0, 0, 100000.0))

    def test_us_stock_trade_uses_server_quote_instead_of_client_price(self) -> None:
        with patch("routes_signals.is_market_open", return_value=True), \
             patch("price_fetcher.get_price_from_market", return_value=403.08):
            response = self.client.post(
                "/api/signals/realtime",
                headers={"Authorization": "Bearer token-price-guard"},
                json=self._trade_payload(),
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["price"], 403.08)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT entry_price, quantity FROM signals WHERE agent_id = ? AND message_type = 'operation'",
            (self.agent_id,),
        )
        signal = cursor.fetchone()
        cursor.execute(
            "SELECT entry_price, quantity FROM positions WHERE agent_id = ? AND symbol = 'TSLA'",
            (self.agent_id,),
        )
        position = cursor.fetchone()
        cursor.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
        cash = float(cursor.fetchone()["cash"])
        conn.close()

        self.assertEqual(float(signal["entry_price"]), 403.08)
        self.assertEqual(float(position["entry_price"]), 403.08)
        self.assertEqual(float(position["quantity"]), 10.0)
        self.assertAlmostEqual(cash, 100000.0 - (403.08 * 10 * 1.001), places=6)


if __name__ == "__main__":
    unittest.main()

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


class AgentRegisterPositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["ALLOW_SQLITE"] = "true"
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rejects_invalid_position_quantity(self) -> None:
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={
                "name": "pos_validation_agent",
                "password": "secret123",
                "positions": [
                    {
                        "symbol": "BTC",
                        "market": "crypto",
                        "side": "short",
                        "quantity": 0,
                        "entry_price": 100.0,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_short_position_stored_with_negative_quantity(self) -> None:
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={
                "name": "short_pos_agent",
                "password": "secret123",
                "positions": [
                    {
                        "symbol": "BTC",
                        "market": "crypto",
                        "side": "short",
                        "quantity": 0.2,
                        "entry_price": 100.0,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        agent_id = response.json()["agent_id"]

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT quantity, entry_price, side FROM positions WHERE agent_id = ?",
            (agent_id,),
        )
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["quantity"], -0.2)
        self.assertAlmostEqual(row["entry_price"], 100.0)
        self.assertEqual(row["side"], "short")


if __name__ == "__main__":
    unittest.main()

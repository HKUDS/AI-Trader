import sqlite3
import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from services import _update_position_from_signal


class UpdatePositionFromSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            """
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                leader_id INTEGER,
                symbol TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'us-stock',
                token_id TEXT,
                outcome TEXT,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL,
                opened_at TEXT NOT NULL
            )
            """
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_short_add_updates_weighted_entry_price(self) -> None:
        self.cursor.execute(
            """
            INSERT INTO positions (
                agent_id, leader_id, symbol, market, token_id, outcome,
                side, quantity, entry_price, opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                None,
                "BTC",
                "crypto",
                None,
                None,
                "short",
                -0.2,
                100.0,
                "2026-04-13T14:16:45Z",
            ),
        )

        _update_position_from_signal(
            agent_id=1,
            symbol="BTC",
            market="crypto",
            action="short",
            quantity=0.3,
            price=120.0,
            executed_at="2026-04-13T15:16:45Z",
            cursor=self.cursor,
        )

        self.cursor.execute(
            """
            SELECT quantity, entry_price, opened_at
            FROM positions
            WHERE agent_id = ? AND symbol = ? AND market = ?
            """,
            (1, "BTC", "crypto"),
        )
        row = self.cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["quantity"], -0.5)
        self.assertAlmostEqual(row["entry_price"], 112.0)
        self.assertEqual(row["opened_at"], "2026-04-13T15:16:45Z")


if __name__ == "__main__":
    unittest.main()

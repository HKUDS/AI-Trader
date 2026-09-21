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

    def _insert_position(self, side: str, quantity: float, entry_price: float) -> None:
        self.cursor.execute(
            """
            INSERT INTO positions (
                agent_id, leader_id, symbol, market, token_id, outcome,
                side, quantity, entry_price, opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, None, "BTC", "crypto", None, None, side, quantity, entry_price, "2026-04-13T14:16:45Z"),
        )

    def _rows(self) -> list:
        self.cursor.execute(
            "SELECT side, quantity, entry_price FROM positions WHERE agent_id = 1 ORDER BY id"
        )
        return [dict(row) for row in self.cursor.fetchall()]

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

    def test_buy_is_rejected_while_a_short_position_is_open(self) -> None:
        self._insert_position("short", -0.2, 100.0)

        with self.assertRaises(ValueError) as caught:
            _update_position_from_signal(
                agent_id=1,
                symbol="BTC",
                market="crypto",
                action="buy",
                quantity=0.3,
                price=120.0,
                executed_at="2026-04-13T15:16:45Z",
                cursor=self.cursor,
            )

        self.assertIn("short position", str(caught.exception))
        self.assertEqual(self._rows(), [{"side": "short", "quantity": -0.2, "entry_price": 100.0}])

    def test_short_is_rejected_while_a_long_position_is_open(self) -> None:
        self._insert_position("long", 0.2, 100.0)

        with self.assertRaises(ValueError) as caught:
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

        self.assertIn("long position", str(caught.exception))
        self.assertEqual(self._rows(), [{"side": "long", "quantity": 0.2, "entry_price": 100.0}])

    def test_buy_still_averages_into_an_existing_long(self) -> None:
        self._insert_position("long", 0.2, 100.0)

        _update_position_from_signal(
            agent_id=1,
            symbol="BTC",
            market="crypto",
            action="buy",
            quantity=0.3,
            price=120.0,
            executed_at="2026-04-13T15:16:45Z",
            cursor=self.cursor,
        )

        self.assertEqual(self._rows(), [{"side": "long", "quantity": 0.5, "entry_price": 112.0}])

    def test_buy_still_opens_a_position_when_none_is_held(self) -> None:
        _update_position_from_signal(
            agent_id=1,
            symbol="BTC",
            market="crypto",
            action="buy",
            quantity=0.3,
            price=120.0,
            executed_at="2026-04-13T15:16:45Z",
            cursor=self.cursor,
        )

        self.assertEqual(self._rows(), [{"side": "long", "quantity": 0.3, "entry_price": 120.0}])


if __name__ == "__main__":
    unittest.main()

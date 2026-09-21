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
from services import _get_user_by_token


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


class SessionTokenExpiryTests(unittest.TestCase):
    """An expired session token must be rejected, whatever time of day it expired."""

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
        cursor.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (1, 'user@example.test', 'hash')"
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _token(self, name: str, expires_at: datetime) -> str:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_tokens (user_id, token, expires_at) VALUES (1, ?, ?)",
            (name, _iso(expires_at)),
        )
        conn.commit()
        conn.close()
        return name

    def test_a_token_that_expired_earlier_today_is_rejected(self) -> None:
        token = self._token(
            "expired-today",
            self.now.replace(hour=0, minute=0, second=1, microsecond=0),
        )

        self.assertIsNone(_get_user_by_token(token))

    def test_a_token_that_expired_yesterday_is_rejected(self) -> None:
        token = self._token("expired-yesterday", self.now - timedelta(days=1))

        self.assertIsNone(_get_user_by_token(token))

    def test_a_token_that_has_not_expired_is_accepted(self) -> None:
        token = self._token("still-valid", self.now + timedelta(days=1))

        user = _get_user_by_token(token)

        self.assertIsNotNone(user)
        self.assertEqual(user["email"], "user@example.test")


if __name__ == "__main__":
    unittest.main()

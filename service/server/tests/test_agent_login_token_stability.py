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
from utils import hash_password


class AgentLoginTokenStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agent_login_returns_existing_token_without_rotating(self) -> None:
        register = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "stable-agent", "password": "password123"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        original_token = register.json()["token"]

        first_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "stable-agent", "password": "password123"},
        )
        second_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "stable-agent", "password": "password123"},
        )

        self.assertEqual(first_login.status_code, 200, first_login.text)
        self.assertEqual(second_login.status_code, 200, second_login.text)
        self.assertEqual(first_login.json()["token"], original_token)
        self.assertEqual(second_login.json()["token"], original_token)

        me = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": f"Bearer {original_token}"},
        )
        self.assertEqual(me.status_code, 200, me.text)

    def test_agent_login_issues_token_only_for_legacy_empty_token(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, password_hash, token, cash)
            VALUES (?, ?, NULL, 100000.0)
            """,
            ("legacy-empty-token", hash_password("password123")),
        )
        conn.commit()
        conn.close()

        first_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "legacy-empty-token", "password": "password123"},
        )
        second_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "legacy-empty-token", "password": "password123"},
        )

        self.assertEqual(first_login.status_code, 200, first_login.text)
        self.assertEqual(second_login.status_code, 200, second_login.text)
        self.assertTrue(first_login.json()["token"])
        self.assertEqual(second_login.json()["token"], first_login.json()["token"])

    def test_new_registration_normalizes_agent_name(self) -> None:
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "  normalized-agent  ", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "normalized-agent")

        login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "normalized-agent", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)

    def test_registration_rejects_normalized_duplicate_of_legacy_spaced_name(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, password_hash, token, cash)
            VALUES (?, ?, ?, 100000.0)
            """,
            (" legacy-duplicate ", hash_password("password123"), "legacy-token"),
        )
        conn.commit()
        conn.close()

        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "legacy-duplicate", "password": "password123"},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"], "Agent name already exists")

    def test_legacy_agent_name_with_spaces_can_still_login_exactly(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, password_hash, token, cash)
            VALUES (?, ?, ?, 100000.0)
            """,
            (" legacy-spaced ", hash_password("password123"), "legacy-token"),
        )
        conn.commit()
        conn.close()

        exact_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": " legacy-spaced ", "password": "password123"},
        )
        trimmed_login = self.client.post(
            "/api/claw/agents/login",
            json={"name": "legacy-spaced", "password": "password123"},
        )

        self.assertEqual(exact_login.status_code, 200, exact_login.text)
        self.assertEqual(exact_login.json()["token"], "legacy-token")
        self.assertEqual(trimmed_login.status_code, 401, trimmed_login.text)


if __name__ == "__main__":
    unittest.main()

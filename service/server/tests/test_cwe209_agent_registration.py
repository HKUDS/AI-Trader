"""Tests verifying CWE-209 fix: error responses on /api/claw/agents/selfRegister
must not leak internal exception details."""

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


class CWE209AgentRegistrationTests(unittest.TestCase):
    """Ensure 500 responses on selfRegister do not leak exception details."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_successful_registration_still_works(self):
        """Normal registration should succeed and return expected fields."""
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "test-agent", "password": "password123", "initial_balance": 100000},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "test-agent")
        self.assertIn("token", data)
        self.assertIn("agent_id", data)

    def test_duplicate_registration_returns_409_not_internal_details(self):
        """Registering the same agent twice should return a clear 409 error."""
        self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "dup-agent", "password": "password123", "initial_balance": 100000},
        )
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "dup-agent", "password": "password123", "initial_balance": 100000},
        )
        # Should get a specific error code, not a 500
        self.assertIn(response.status_code, (400, 409))

    def test_internal_error_returns_generic_message(self):
        """When an unexpected exception occurs inside the registration try
        block, the 500 response must contain only a generic message, not the
        raw exception string.

        We patch ``hash_password`` (called inside the try block at line ~571)
        rather than ``get_db_connection`` (which is called *before* the try
        block at line 563 and therefore is not covered by the fix's
        except-clause).
        """
        secret_message = "SECRET_DB_CONNECTION_STRING_12345"
        with patch(
            "routes_agent.hash_password",
            side_effect=RuntimeError(secret_message),
        ):
            response = self.client.post(
                "/api/claw/agents/selfRegister",
                json={"name": "fail-agent", "password": "password123", "initial_balance": 100000},
            )

        self.assertEqual(response.status_code, 500)
        detail = response.json().get("detail", "")

        # The critical assertion: internal exception details must NOT leak
        self.assertNotIn(secret_message, detail)
        self.assertNotIn("SECRET_DB_CONNECTION_STRING", detail)
        self.assertNotIn("RuntimeError", detail)

        # The response should contain only the generic message
        self.assertEqual(detail, "Agent registration failed")

    def test_internal_error_does_not_leak_traceback(self):
        """Ensure no traceback or Python-internal info leaks in error response.

        Like the test above, we patch a function that is called *inside* the
        try block so the fix's generic-error handler is exercised.
        """
        with patch(
            "routes_agent.hash_password",
            side_effect=ValueError("sqlite3.OperationalError: table agents has no column named secret"),
        ):
            response = self.client.post(
                "/api/claw/agents/selfRegister",
                json={"name": "trace-agent", "password": "password123", "initial_balance": 100000},
            )

        self.assertEqual(response.status_code, 500)
        body = response.text

        # None of these internal details should appear in the response
        self.assertNotIn("sqlite3", body)
        self.assertNotIn("OperationalError", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("File ", body)

        detail = response.json().get("detail", "")
        self.assertEqual(detail, "Agent registration failed")


if __name__ == "__main__":
    unittest.main()

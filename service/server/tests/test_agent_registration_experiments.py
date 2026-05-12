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
from experiments import create_experiment
from routes import create_app


class AgentRegistrationExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        create_experiment({
            "experiment_key": "registration-exp",
            "title": "Registration experiment",
            "variants_json": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
        })
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_self_register_assigns_active_agent_experiments(self):
        response = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "new-agent", "password": "password123", "initial_balance": 100000},
        )

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["name"], "new-agent")
        self.assertEqual(len(data["experiment_assignments"]), 1)
        assignment = data["experiment_assignments"][0]
        self.assertEqual(assignment["experiment_key"], "registration-exp")
        self.assertIn(assignment["variant_key"], {"control", "treatment"})

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT variant_key
            FROM experiment_assignments
            WHERE experiment_key = 'registration-exp' AND unit_type = 'agent' AND unit_id = ?
            """,
            (data["agent_id"],),
        )
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["variant_key"], assignment["variant_key"])
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM experiment_events
            WHERE event_type = 'experiment_assigned'
              AND experiment_key = 'registration-exp'
              AND actor_agent_id = ?
            """,
            (data["agent_id"],),
        )
        self.assertEqual(cursor.fetchone()["count"], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()

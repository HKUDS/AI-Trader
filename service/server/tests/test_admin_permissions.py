import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app
from routes_shared import utc_now_iso_z


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AdminPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.admin_id = self._create_agent("admin-agent", "admin")
        self.regular_id = self._create_agent("regular-agent", "agent")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, role: str) -> int:
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, role, points, cash, created_at, updated_at)
            VALUES (?, ?, ?, 0, 100000.0, ?, ?)
            """,
            (name, f"token-{name}", role, now, now),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_agent_me_returns_role_and_permissions(self):
        regular = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": "Bearer token-regular-agent"},
        )
        self.assertEqual(regular.status_code, 200, regular.text)
        self.assertEqual(regular.json()["role"], "agent")
        self.assertFalse(regular.json()["permissions"]["experiment_admin"])
        self.assertFalse(regular.json()["permissions"]["research_exports"])
        self.assertFalse(regular.json()["permissions"]["team_mission_admin"])

        admin = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": "Bearer token-admin-agent"},
        )
        self.assertEqual(admin.status_code, 200, admin.text)
        self.assertEqual(admin.json()["role"], "admin")
        self.assertTrue(admin.json()["permissions"]["experiment_admin"])
        self.assertTrue(admin.json()["permissions"]["research_exports"])
        self.assertTrue(admin.json()["permissions"]["team_mission_admin"])

    def test_regular_agent_cannot_manage_experiments(self):
        payload = {
            "title": "Blocked experiment",
            "experiment_key": "blocked-exp",
            "variants_json": [{"key": "control", "weight": 1}],
        }
        regular = self.client.post(
            "/api/experiments",
            headers={"Authorization": "Bearer token-regular-agent"},
            json=payload,
        )
        self.assertEqual(regular.status_code, 403, regular.text)

        admin = self.client.post(
            "/api/experiments",
            headers={"Authorization": "Bearer token-admin-agent"},
            json=payload,
        )
        self.assertEqual(admin.status_code, 200, admin.text)

    def test_regular_agent_cannot_create_or_operate_team_missions(self):
        due_at = iso(datetime.now(timezone.utc) + timedelta(hours=1))
        payload = {
            "mission_key": "admin-only-mission",
            "title": "Admin only mission",
            "market": "crypto",
            "symbol": "BTC",
            "submission_due_at": due_at,
        }
        regular = self.client.post(
            "/api/team-missions",
            headers={"Authorization": "Bearer token-regular-agent"},
            json=payload,
        )
        self.assertEqual(regular.status_code, 403, regular.text)

        admin = self.client.post(
            "/api/team-missions",
            headers={"Authorization": "Bearer token-admin-agent"},
            json=payload,
        )
        self.assertEqual(admin.status_code, 200, admin.text)

        join = self.client.post(
            "/api/team-missions/admin-only-mission/join",
            headers={"Authorization": "Bearer token-regular-agent"},
            json={},
        )
        self.assertEqual(join.status_code, 200, join.text)

        auto_form = self.client.post(
            "/api/team-missions/admin-only-mission/auto-form-teams",
            headers={"Authorization": "Bearer token-regular-agent"},
            json={},
        )
        self.assertEqual(auto_form.status_code, 403, auto_form.text)

import json
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
from experiment_notifications import (
    MAX_LIMIT,
    _clamp_limit,
    resolve_unread_active_experiment_targets,
)
from experiments import create_experiment
from routes import create_app
from routes_shared import utc_now_iso_z


class ExperimentNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.admin_id = self._create_agent("notify-admin", role="experiment_admin")
        self.agent_control = self._create_agent("notify-control")
        self.agent_treatment = self._create_agent("notify-treatment")
        self.agent_extra = self._create_agent("notify-extra")
        create_experiment({
            "experiment_key": "notify-exp",
            "title": "Notification experiment",
            "variants_json": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
        })
        self._assign(self.agent_control, "control")
        self._assign(self.agent_treatment, "treatment")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, role: str = "agent") -> int:
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, role, created_at, updated_at)
            VALUES (?, ?, 0, 100000.0, ?, ?, ?)
            """,
            (name, f"token-{name}", role, now, now),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _assign(self, agent_id: int, variant_key: str) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO experiment_assignments
            (experiment_key, unit_type, unit_id, variant_key, assignment_reason, metadata_json, created_at)
            VALUES ('notify-exp', 'agent', ?, ?, 'fixture', '{}', ?)
            """,
            (agent_id, variant_key, utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

    def _notify(self, **overrides):
        payload = {
            "message_type": "experiment_announcement",
            "title": "Experiment notice",
            "content": "You are included in an AI-Trader experiment notification campaign.",
            "dry_run": True,
            "limit": 500,
        }
        payload.update(overrides)
        return self.client.post(
            "/api/experiments/notify-exp/notify",
            headers={"Authorization": "Bearer token-notify-admin"},
            json=payload,
        )

    def test_regular_agent_cannot_send_experiment_notifications(self):
        response = self.client.post(
            "/api/experiments/notify-exp/notify",
            headers={"Authorization": "Bearer token-notify-control"},
            json={
                "message_type": "experiment_announcement",
                "title": "Experiment notice",
                "content": "This should be blocked.",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_dry_run_resolves_experiment_targets_without_writing_messages(self):
        response = self._notify()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["target_count"], 2)
        self.assertEqual({row["agent_id"] for row in data["targets_preview"]}, {self.agent_control, self.agent_treatment})

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM agent_messages")
        self.assertEqual(cursor.fetchone()["count"], 0)
        cursor.execute("SELECT event_type, metadata_json FROM experiment_events WHERE event_type = 'experiment_notification_sent'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        metadata = json.loads(row["metadata_json"])
        self.assertTrue(metadata["dry_run"])
        self.assertEqual(metadata["target_count"], 2)
        conn.close()

    def test_variant_filter_limits_targets(self):
        response = self._notify(variant_key="treatment")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["target_count"], 1)
        self.assertEqual(data["targets_preview"][0]["agent_id"], self.agent_treatment)
        self.assertEqual(data["targets_preview"][0]["variant_key"], "treatment")

    def test_agent_ids_are_intersected_with_experiment_targets(self):
        response = self._notify(agent_ids=[self.agent_treatment, self.agent_extra])
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["target_count"], 1)
        self.assertEqual(data["targets_preview"][0]["agent_id"], self.agent_treatment)

    def test_notification_limit_matches_frozen_full_cohort_size(self):
        self.assertEqual(MAX_LIMIT, 5289)
        self.assertEqual(_clamp_limit(6000), 5289)

    def test_experiment_targets_respect_enrollment_limit(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE experiments SET variants_json = ? WHERE experiment_key = 'notify-exp'",
            (
                json.dumps({
                    "variants": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
                    "enrollment_max_unit_id": self.agent_treatment,
                    "enrollment_status": "closed",
                }),
            ),
        )
        conn.commit()
        conn.close()
        self._assign(self.agent_extra, "control")

        response = self._notify(limit=6000)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["target_count"], 2)
        self.assertEqual({row["agent_id"] for row in data["targets_preview"]}, {self.agent_control, self.agent_treatment})

    def test_bulk_send_writes_agent_messages_and_audit_event(self):
        response = self._notify(dry_run=False, create_task=True, task_type="submit_strategy")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["sent_count"], 2)
        self.assertEqual(data["task_created_count"], 2)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT agent_id, type, content, data FROM agent_messages ORDER BY agent_id")
        rows = [dict(row) for row in cursor.fetchall()]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["agent_id"] for row in rows}, {self.agent_control, self.agent_treatment})
        self.assertTrue(all(row["type"] == "experiment_announcement" for row in rows))
        self.assertTrue(all(json.loads(row["data"])["campaign_id"] == data["campaign_id"] for row in rows))
        cursor.execute("SELECT COUNT(*) AS count FROM agent_tasks WHERE type = 'submit_strategy'")
        self.assertEqual(cursor.fetchone()["count"], 2)
        cursor.execute(
            """
            SELECT event_type, metadata_json
            FROM experiment_events
            WHERE object_id = ?
            ORDER BY id
            """,
            (data["campaign_id"],),
        )
        events = [dict(row) for row in cursor.fetchall()]
        event_types = {row["event_type"] for row in events}
        self.assertIn("experiment_notification_sent", event_types)
        self.assertIn("experiment_tasks_created", event_types)
        notification = next(row for row in events if row["event_type"] == "experiment_notification_sent")
        metadata = json.loads(notification["metadata_json"])
        self.assertEqual(metadata["sent_count"], 2)
        self.assertEqual(metadata["task_created_count"], 2)
        conn.close()

    def test_unsupported_message_type_returns_400(self):
        response = self._notify(message_type="not_allowed", create_task=True, task_type="submit_strategy")
        self.assertEqual(response.status_code, 400, response.text)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM agent_tasks")
        self.assertEqual(cursor.fetchone()["count"], 0)
        conn.close()

    def test_unread_summary_and_recent_include_experiment_category(self):
        send_response = self._notify(dry_run=False)
        self.assertEqual(send_response.status_code, 200, send_response.text)

        summary = self.client.get(
            "/api/claw/messages/unread-summary",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(summary.status_code, 200, summary.text)
        data = summary.json()
        self.assertEqual(data["experiment_unread"], 1)
        self.assertEqual(data["discussion_unread"], 0)
        self.assertEqual(data["strategy_unread"], 0)

        recent = self.client.get(
            "/api/claw/messages/recent?category=experiment&limit=5",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(recent.status_code, 200, recent.text)
        self.assertEqual(len(recent.json()["messages"]), 1)
        self.assertTrue(recent.json()["agent_notice"]["experiment_unread"])
        self.assertEqual(
            recent.json()["agent_notice"]["recommended_action"]["endpoint"],
            "/api/claw/messages/read-experiment",
        )

    def test_read_experiment_endpoint_returns_and_marks_experiment_messages(self):
        send_response = self._notify(dry_run=False)
        self.assertEqual(send_response.status_code, 200, send_response.text)

        response = self.client.post(
            "/api/claw/messages/read-experiment",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message_count"], 1)
        self.assertEqual(data["updated"], 1)
        self.assertEqual(data["unread_before"], 1)
        self.assertEqual(data["remaining_unread_count"], 0)
        self.assertEqual(data["messages"][0]["type"], "experiment_announcement")
        self.assertEqual(data["messages"][0]["read"], 1)

        summary = self.client.get(
            "/api/claw/messages/unread-summary",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["experiment_unread"], 0)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM experiment_events
            WHERE event_type = 'experiment_messages_read'
              AND actor_agent_id = ?
            """,
            (self.agent_control,),
        )
        self.assertEqual(cursor.fetchone()["count"], 1)
        conn.close()

    def test_agent_me_and_count_attach_unified_notice_when_authorized(self):
        send_response = self._notify(dry_run=False)
        self.assertEqual(send_response.status_code, 200, send_response.text)

        me = self.client.get(
            "/api/claw/agents/me",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertTrue(me.json()["agent_notice"]["experiment_unread"])

        count = self.client.get(
            "/api/claw/agents/count",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(count.status_code, 200, count.text)
        self.assertEqual(count.json()["count"], 4)
        self.assertTrue(count.json()["agent_notice"]["experiment_unread"])

        public_count = self.client.get("/api/claw/agents/count")
        self.assertEqual(public_count.status_code, 200, public_count.text)
        self.assertNotIn("agent_notice", public_count.json())

    def test_heartbeat_includes_behavior_experiment_context(self):
        response = self.client.post(
            "/api/claw/agents/heartbeat",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        context = response.json()["experiment_context"]

        self.assertEqual(context["primary_metric_family"], "active_agent_behavior")
        self.assertEqual(context["read_receipts_role"], "diagnostic_only")
        self.assertFalse(context["message_read_state_required"])
        self.assertEqual(context["assignments"][0]["experiment_key"], "notify-exp")
        self.assertEqual(context["assignments"][0]["variant_key"], "control")
        self.assertFalse(context["assignments"][0]["message_read_state_required"])

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT experiment_key, variant_key
            FROM experiment_events
            WHERE event_type = 'agent_heartbeat'
              AND actor_agent_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (self.agent_control,),
        )
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row["experiment_key"], "notify-exp")
        self.assertEqual(row["variant_key"], "control")

    def test_heartbeat_task_read_event_includes_experiment_context(self):
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_tasks (agent_id, type, status, input_data, created_at, updated_at)
            VALUES (?, 'submit_strategy', 'pending', '{}', ?, ?)
            """,
            (self.agent_control, now, now),
        )
        conn.commit()
        conn.close()

        response = self.client.post(
            "/api/claw/agents/heartbeat",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(response.status_code, 200, response.text)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT experiment_key, variant_key
            FROM experiment_events
            WHERE event_type = 'agent_tasks_read'
              AND actor_agent_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (self.agent_control,),
        )
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row["experiment_key"], "notify-exp")
        self.assertEqual(row["variant_key"], "control")

    def test_trending_attaches_unified_notice_when_authorized(self):
        send_response = self._notify(dry_run=False)
        self.assertEqual(send_response.status_code, 200, send_response.text)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO positions (agent_id, symbol, market, side, quantity, entry_price, current_price, opened_at)
            VALUES (?, 'AAPL', 'us-stock', 'long', 1, 100, 110, ?)
            """,
            (self.agent_control, utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

        response = self.client.get(
            "/api/trending?limit=5",
            headers={"Authorization": "Bearer token-notify-control"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["trending"][0]["symbol"], "AAPL")
        self.assertTrue(data["agent_notice"]["experiment_unread"])
        self.assertEqual(data["agent_notice"]["must_call"], "/api/claw/messages/read-experiment")

    def test_unread_active_targets_require_activity_unread_and_no_recent_conversion_reminder(self):
        send_response = self._notify(dry_run=False)
        self.assertEqual(send_response.status_code, 200, send_response.text)

        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO experiment_events
            (event_id, event_type, actor_agent_id, object_type, object_id, experiment_key, variant_key, metadata_json, created_at)
            VALUES ('active-control', 'agent_heartbeat', ?, 'agent', ?, 'notify-exp', 'control', '{}', ?)
            """,
            (self.agent_control, str(self.agent_control), now),
        )
        cursor.execute(
            """
            INSERT INTO experiment_events
            (event_id, event_type, actor_agent_id, object_type, object_id, experiment_key, variant_key, metadata_json, created_at)
            VALUES ('active-treatment', 'agent_heartbeat', ?, 'agent', ?, 'notify-exp', 'treatment', '{}', ?)
            """,
            (self.agent_treatment, str(self.agent_treatment), now),
        )
        cursor.execute(
            """
            INSERT INTO agent_messages (agent_id, type, content, data, read, created_at)
            VALUES (?, 'experiment_reminder', 'recent conversion', ?, 0, ?)
            """,
            (
                self.agent_treatment,
                json.dumps({"purpose": "read_conversion"}),
                now,
            ),
        )
        conn.commit()
        conn.close()

        targets = resolve_unread_active_experiment_targets(
            "notify-exp",
            active_since="2000-01-01T00:00:00Z",
            reminder_since="2000-01-01T00:00:00Z",
            limit=10,
        )
        self.assertEqual([row["agent_id"] for row in targets], [self.agent_control])
        self.assertEqual(targets[0]["unread_experiment_count"], 1)

    def test_websocket_allows_matching_token_and_rejects_mismatch(self):
        with self.client.websocket_connect(f"/ws/notify/{self.agent_control}?token=token-notify-control") as websocket:
            websocket.send_text("ping")

        with self.assertRaises(Exception):
            with self.client.websocket_connect(f"/ws/notify/{self.agent_control}?token=token-notify-treatment"):
                pass

    def test_online_agent_receives_websocket_payload(self):
        with self.client.websocket_connect(f"/ws/notify/{self.agent_control}?token=token-notify-control") as websocket:
            response = self._notify(dry_run=False, agent_ids=[self.agent_control])
            self.assertEqual(response.status_code, 200, response.text)
            payload = websocket.receive_json()
            self.assertEqual(payload["type"], "experiment_announcement")
            self.assertIn("experiment notification campaign", payload["content"])
            self.assertEqual(payload["data"]["target_agent_id"], self.agent_control)


if __name__ == "__main__":
    unittest.main()

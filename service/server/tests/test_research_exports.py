import csv
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
from experiment_events import record_event
from experiment_metrics import build_network_edges
from research_exports import (
    export_research_dataset,
    export_agents_csv,
    export_events_csv,
    export_network_edges_csv,
    export_signals_csv,
    fetch_research_export_rows,
    get_research_dataset_names,
    research_schema_for_dataset,
)
from routes import create_app
from routes_shared import utc_now_iso_z


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ResearchExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_1 = self._create_agent("export-agent-1")
        self.agent_2 = self._create_agent("export-agent-2")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str) -> int:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES (?, ?, 0, 100000.0, ?, ?)
            """,
            (name, f"token-{name}", utc_now_iso_z(), utc_now_iso_z()),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _insert_signal_and_reply(self):
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, title,
             content, timestamp, created_at)
            VALUES (9001, ?, 'strategy', 'crypto', 'strategy', 'BTC', 'BTC target',
                    'BTC target price 120000 because liquidity improves.', ?, ?)
            """,
            (self.agent_1, int(datetime.now(timezone.utc).timestamp()), now),
        )
        cursor.execute(
            """
            INSERT INTO signal_replies (signal_id, agent_id, content, accepted, created_at)
            VALUES (9001, ?, 'Adopting this thesis.', 1, ?)
            """,
            (self.agent_2, now),
        )
        reply_id = cursor.lastrowid
        cursor.execute("UPDATE signals SET accepted_reply_id = ? WHERE signal_id = 9001", (reply_id,))
        cursor.execute(
            """
            INSERT INTO signal_predictions
            (signal_id, agent_id, market, symbol, direction, target_price, confidence,
             evidence_json, created_at)
            VALUES (9001, ?, 'crypto', 'BTC', 'up', 120000, 0.8,
                    '{"source": "fixture", "email": "secret@example.com"}', ?)
            """,
            (self.agent_1, now),
        )
        cursor.execute(
            """
            INSERT INTO signal_quality_scores
            (signal_id, agent_id, verifiability_score, evidence_score, specificity_score,
             novelty_score, review_score, overall_score, metadata_json, created_at)
            VALUES (9001, ?, 0.8, 0.7, 0.9, 0.6, 0.85, 0.77,
                    '{"wallet": "0xabc", "note": "ok"}', ?)
            """,
            (self.agent_1, now),
        )
        cursor.execute(
            """
            INSERT INTO positions
            (agent_id, leader_id, symbol, market, side, quantity, entry_price, current_price, opened_at)
            VALUES (?, ?, 'BTC', 'crypto', 'long', 1, 100000, 105000, ?)
            """,
            (self.agent_2, self.agent_1, now),
        )
        cursor.execute(
            """
            INSERT INTO profit_history
            (agent_id, total_value, cash, position_value, profit, recorded_at)
            VALUES (?, 101000, 50000, 51000, 1000, ?)
            """,
            (self.agent_1, now),
        )
        cursor.execute(
            "INSERT INTO subscriptions (leader_id, follower_id, status, created_at) VALUES (?, ?, 'active', ?)",
            (self.agent_1, self.agent_2, now),
        )
        cursor.execute(
            """
            INSERT INTO agent_reward_ledger
            (agent_id, amount, reason, source_type, source_id, experiment_key, variant_key, metadata_json, created_at)
            VALUES (?, 10, 'fixture reward', 'test', '9001', 'export-exp', 'treatment',
                    '{"token": "secret", "safe": true}', ?)
            """,
            (self.agent_1, now),
        )
        cursor.execute(
            """
            INSERT INTO experiment_assignments
            (experiment_key, unit_type, unit_id, variant_key, assignment_reason, metadata_json, created_at)
            VALUES ('export-exp', 'agent', ?, 'treatment', 'fixture', '{"password": "secret"}', ?)
            """,
            (self.agent_1, now),
        )
        cursor.execute(
            """
            INSERT INTO challenges
            (challenge_key, title, description, market, symbol, challenge_type, start_at, end_at,
             experiment_key, created_by_agent_id, created_at, updated_at)
            VALUES ('fixture-challenge', 'Fixture Challenge', 'fixture', 'crypto', 'BTC',
                    'return', ?, ?, 'export-exp', ?, ?, ?)
            """,
            (now, now, self.agent_1, now, now),
        )
        challenge_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO challenge_participants
            (challenge_id, agent_id, variant_key, return_pct, max_drawdown, trade_count, rank)
            VALUES (?, ?, 'treatment', 1.5, 0.2, 1, 1)
            """,
            (challenge_id, self.agent_1),
        )
        cursor.execute(
            """
            INSERT INTO challenge_results
            (challenge_id, agent_id, return_pct, max_drawdown, risk_adjusted_score,
             quality_score, final_score, rank, metrics_json, settled_at)
            VALUES (?, ?, 1.5, 0.2, 1.3, 0.8, 1.4, 1, '{"token": "secret", "ok": 1}', ?)
            """,
            (challenge_id, self.agent_1, now),
        )
        cursor.execute(
            """
            INSERT INTO team_missions
            (mission_key, title, description, market, symbol, mission_type, start_at,
             submission_due_at, experiment_key, created_at, updated_at)
            VALUES ('fixture-mission', 'Fixture Mission', 'fixture', 'crypto', 'BTC',
                    'consensus', ?, ?, 'export-exp', ?, ?)
            """,
            (now, now, now, now),
        )
        mission_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO teams
            (mission_id, team_key, name, status, formation_method, variant_key, created_at, updated_at)
            VALUES (?, 'fixture-team', 'Fixture Team', 'active', 'manual', 'treatment', ?, ?)
            """,
            (mission_id, now, now),
        )
        team_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO team_results
            (mission_id, team_id, return_pct, prediction_score, quality_score,
             consensus_gain, final_score, metrics_json, settled_at)
            VALUES (?, ?, 1.2, 0.7, 0.8, 0.3, 0.9, '{"secret": "hide", "ok": 2}', ?)
            """,
            (mission_id, team_id, now),
        )
        conn.commit()
        conn.close()

    def test_research_csv_columns_are_stable_and_time_filters_apply(self):
        self._insert_signal_and_reply()
        old_at = iso(datetime.now(timezone.utc) - timedelta(days=3))
        new_at = utc_now_iso_z()
        record_event(
            "old_event",
            actor_agent_id=self.agent_1,
            object_type="test",
            object_id="old",
            experiment_key="export-exp",
            variant_key="control",
            metadata={"age": "old"},
        )
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE experiment_events SET created_at = ? WHERE event_type = 'old_event'", (old_at,))
        conn.commit()
        conn.close()
        record_event(
            "new_event",
            actor_agent_id=self.agent_2,
            object_type="test",
            object_id="new",
            experiment_key="export-exp",
            variant_key="treatment",
            metadata={"age": "new"},
        )
        build_network_edges()

        output_dir = Path(self.tmp.name) / "exports"
        paths = {
            "agents.csv": export_agents_csv(output_dir),
            "events.csv": export_events_csv(output_dir, start_at=iso(datetime.now(timezone.utc) - timedelta(days=1))),
            "signals.csv": export_signals_csv(output_dir, market="crypto"),
            "network_edges.csv": export_network_edges_csv(output_dir),
        }
        for path in paths.values():
            self.assertTrue(Path(path).exists())

        with open(paths["events.csv"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        event_types = {row["event_type"] for row in rows}
        self.assertIn("new_event", event_types)
        self.assertNotIn("old_event", event_types)

        columns, signal_rows = fetch_research_export_rows("signals.csv", market="crypto")
        self.assertIn("accepted_reply_id", columns)
        self.assertEqual(len(signal_rows), 1)

        columns, edge_rows = fetch_research_export_rows("network_edges.csv")
        self.assertEqual(columns[:5], ["id", "source_agent_id", "source_agent_hash", "target_agent_id", "target_agent_hash"])
        self.assertGreaterEqual(len(edge_rows), 1)

    def test_all_primary_datasets_export_with_headers_and_default_anonymization(self):
        self._insert_signal_and_reply()
        record_event(
            "new_event",
            actor_agent_id=self.agent_1,
            target_agent_id=self.agent_2,
            object_type="signal",
            object_id=9001,
            market="crypto",
            experiment_key="export-exp",
            variant_key="treatment",
            metadata={"token": "secret-token", "wallet": "0xabc", "safe": "kept"},
        )
        build_network_edges()

        output_dir = Path(self.tmp.name) / "full-exports"
        paths = export_research_dataset(output_dir)
        self.assertEqual(set(paths), set(get_research_dataset_names(primary_only=True)))

        for dataset_name, path in paths.items():
            with open(path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, research_schema_for_dataset(dataset_name)["required"])

        with open(paths["agents.csv"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(rows)
        self.assertNotEqual(rows[0]["name"], "export-agent-1")
        self.assertTrue(rows[0]["agent_hash"].startswith("sha256:"))

        with open(paths["events.csv"], newline="", encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("secret-token", text)
        self.assertNotIn("0xabc", text)
        self.assertIn("safe", text)

    def test_public_structure_only_hashes_content(self):
        self._insert_signal_and_reply()
        columns, rows = fetch_research_export_rows("signals.csv", include_content=False)
        self.assertIn("content", columns)
        self.assertTrue(rows[0]["content"].startswith("sha256:"))
        self.assertTrue(rows[0]["title"].startswith("sha256:"))

    def test_market_filter_is_supported_for_every_dataset(self):
        self._insert_signal_and_reply()
        for dataset_name in get_research_dataset_names():
            columns, rows = fetch_research_export_rows(dataset_name, market="crypto")
            self.assertEqual(columns, research_schema_for_dataset(dataset_name)["required"])
            self.assertIsInstance(rows, list)

    def test_experiment_variant_and_agent_filters_are_supported_for_every_dataset(self):
        self._insert_signal_and_reply()
        for dataset_name in get_research_dataset_names():
            columns, rows = fetch_research_export_rows(
                dataset_name,
                experiment_key="export-exp",
                variant_key="treatment",
                agent_ids=[self.agent_1],
            )
            self.assertEqual(columns, research_schema_for_dataset(dataset_name)["required"])
            self.assertIsInstance(rows, list)

    def test_empty_export_preserves_header(self):
        output_dir = Path(self.tmp.name) / "empty"
        path = export_events_csv(output_dir, start_at="2099-01-01T00:00:00Z")
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            rows = list(reader)
        self.assertIn("event_id", header)
        self.assertEqual(rows, [])

    def test_research_export_api_serves_csv_json_and_schema(self):
        self._insert_signal_and_reply()
        record_event(
            "api_event",
            actor_agent_id=self.agent_1,
            object_type="signal",
            object_id=9001,
            market="crypto",
            experiment_key="api-exp",
            variant_key="control",
            metadata={"token": "hidden", "safe": "ok"},
        )

        csv_response = self.client.get("/api/research/export/events.csv?experiment_key=api-exp")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("event_id", csv_response.text.splitlines()[0])
        self.assertNotIn("hidden", csv_response.text)

        json_response = self.client.get("/api/research/export/events.json?experiment_key=api-exp")
        self.assertEqual(json_response.status_code, 200)
        payload = json_response.json()
        self.assertEqual(payload["dataset"], "events.csv")
        self.assertIn("event_id", payload["columns"])
        self.assertEqual(payload["rows"][0]["experiment_key"], "api-exp")

        schema_response = self.client.get("/api/research/schema/events")
        self.assertEqual(schema_response.status_code, 200)
        schema = schema_response.json()
        self.assertEqual(schema["title"], "events.csv research export row")
        self.assertIn("metadata_json", schema["required"])

    def test_network_edges_cover_required_types_without_duplicates(self):
        self._insert_signal_and_reply()
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, title,
             content, timestamp, created_at)
            VALUES (9002, ?, 'discussion', 'crypto', 'discussion', 'BTC', '@export-agent-2',
                    'cite source from accepted reply @export-agent-2', ?, ?)
            """,
            (self.agent_1, int(datetime.now(timezone.utc).timestamp()), now),
        )
        cursor.execute(
            """
            INSERT INTO challenges
            (challenge_key, title, description, market, symbol, challenge_type, start_at, end_at, created_at, updated_at)
            VALUES ('edge-challenge', 'Edge Challenge', 'fixture', 'crypto', 'BTC', 'return', ?, ?, ?, ?)
            """,
            (now, now, now, now),
        )
        challenge_id = cursor.lastrowid
        cursor.execute("INSERT INTO challenge_participants (challenge_id, agent_id) VALUES (?, ?)", (challenge_id, self.agent_1))
        cursor.execute("INSERT INTO challenge_participants (challenge_id, agent_id) VALUES (?, ?)", (challenge_id, self.agent_2))
        cursor.execute(
            """
            INSERT INTO team_missions
            (mission_key, title, description, market, symbol, mission_type, start_at, submission_due_at, created_at, updated_at)
            VALUES ('edge-mission', 'Edge Mission', 'fixture', 'crypto', 'BTC', 'consensus', ?, ?, ?, ?)
            """,
            (now, now, now, now),
        )
        mission_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO teams (mission_id, team_key, name, status, created_at, updated_at) VALUES (?, 'edge-team', 'Edge Team', 'active', ?, ?)",
            (mission_id, now, now),
        )
        team_id = cursor.lastrowid
        cursor.execute("INSERT INTO team_members (team_id, agent_id, status, joined_at) VALUES (?, ?, 'active', ?)", (team_id, self.agent_1, now))
        cursor.execute("INSERT INTO team_members (team_id, agent_id, status, joined_at) VALUES (?, ?, 'active', ?)", (team_id, self.agent_2, now))
        conn.commit()
        conn.close()

        build_network_edges()
        first_columns, first_rows = fetch_research_export_rows("network_edges.csv")
        build_network_edges()
        _columns, second_rows = fetch_research_export_rows("network_edges.csv")

        self.assertEqual(len(first_rows), len(second_rows))
        edge_types = {row["edge_type"] for row in first_rows}
        self.assertTrue({
            "reply",
            "mention",
            "accepted_reply",
            "follow",
            "copied_trade",
            "same_team",
            "challenge_opponent",
            "citation",
            "adoption",
        }.issubset(edge_types))
        unique_keys = {
            (row["source_agent_hash"], row["target_agent_hash"], row["edge_type"], row["signal_id"], row["metadata_json"])
            for row in first_rows
        }
        self.assertEqual(len(unique_keys), len(first_rows))
        self.assertIn("first_seen_at", first_columns)
        self.assertIn("last_seen_at", first_columns)


if __name__ == "__main__":
    unittest.main()

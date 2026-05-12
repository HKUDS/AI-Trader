import os
import sys
import tempfile
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from experiments import (
    ExperimentError,
    assign_unit_to_experiment,
    create_experiment,
    get_experiment_assignments,
    stable_bucket,
    variant_for_agent,
)
from routes_shared import utc_now_iso_z


class ExperimentAssignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_ids = [self._create_agent(f"agent-{idx}") for idx in range(12)]

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

    def test_same_agent_stably_assigns_to_same_variant(self):
        create_experiment({
            "experiment_key": "stable-reward-test",
            "title": "Stable reward test",
            "variants_json": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
        })

        first = assign_unit_to_experiment("stable-reward-test", "agent", self.agent_ids[0])
        second = assign_unit_to_experiment("stable-reward-test", "agent", self.agent_ids[0])

        self.assertEqual(first["variant_key"], second["variant_key"])
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(stable_bucket("stable-reward-test", "agent", self.agent_ids[0]), stable_bucket("stable-reward-test", "agent", self.agent_ids[0]))

    def test_stratified_bucket_does_not_put_all_high_activity_agents_in_one_variant(self):
        create_experiment({
            "experiment_key": "activity-strata",
            "title": "Activity strata",
            "variants_json": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
        })

        assignments = [
            assign_unit_to_experiment(
                "activity-strata",
                "agent",
                agent_id,
                metadata={"strata_key": "high-activity"},
            )
            for agent_id in self.agent_ids
        ]
        variants = {assignment["variant_key"] for assignment in assignments}

        self.assertGreater(len(variants), 1)

    def test_assignment_summary_includes_variant_metrics(self):
        create_experiment({
            "experiment_key": "metric-summary",
            "title": "Metric summary",
            "variants_json": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
        })
        assignment = assign_unit_to_experiment("metric-summary", "agent", self.agent_ids[0])

        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_metric_snapshots
            (agent_id, window_key, window_start_at, window_end_at, return_pct,
             max_drawdown, trade_count, strategy_count, discussion_count,
             reply_count, accepted_reply_count, citation_count, adoption_count,
             quality_score_avg, risk_violation_count, metadata_json, created_at)
            VALUES (?, '7d', ?, ?, 12.5, 3.5, 4, 2, 1, 5, 1, 2, 3, 4.25, 0, '{}', ?)
            """,
            (self.agent_ids[0], now, now, now),
        )
        conn.commit()
        conn.close()

        summary = get_experiment_assignments("metric-summary")
        metrics = {row["variant_key"]: row for row in summary["variant_metrics"]}

        self.assertIn(assignment["variant_key"], metrics)
        variant_row = metrics[assignment["variant_key"]]
        self.assertEqual(variant_row["agent_count"], 1)
        self.assertEqual(variant_row["trade_count"], 4)
        self.assertAlmostEqual(variant_row["quality_score_avg"], 4.25)

    def test_enrollment_limit_blocks_new_assignments_but_keeps_existing(self):
        create_experiment({
            "experiment_key": "limited-exp",
            "title": "Limited experiment",
            "variants_json": {
                "variants": [{"key": "control", "weight": 1}, {"key": "treatment", "weight": 1}],
                "enrollment_max_unit_id": self.agent_ids[1],
                "enrollment_status": "closed",
            },
        })

        first = assign_unit_to_experiment("limited-exp", "agent", self.agent_ids[0])
        second = assign_unit_to_experiment("limited-exp", "agent", self.agent_ids[0])

        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        with self.assertRaises(ExperimentError):
            assign_unit_to_experiment("limited-exp", "agent", self.agent_ids[2])
        self.assertEqual(variant_for_agent(self.agent_ids[2]), [])

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM experiment_assignments
            WHERE experiment_key = 'limited-exp' AND unit_id = ?
            """,
            (self.agent_ids[2],),
        )
        self.assertEqual(cursor.fetchone()["count"], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()

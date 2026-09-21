import os
import sys
import tempfile
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from research_exports import (
    fetch_research_export_rows,
    get_research_dataset_names,
    get_research_export_columns,
)


def _masked_columns(columns: list) -> list:
    """Id columns that carry a hashed counterpart in the same dataset."""
    return [
        column
        for column in columns
        if column.endswith("_id") and column[: -len("_id")] + "_hash" in columns
    ]


class ResearchExportAnonymizationTests(unittest.TestCase):
    """An export that claims to be anonymized must not ship the raw id."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        for agent_id, name in ((41, "export-agent-a"), (42, "export-agent-b")):
            cursor.execute(
                "INSERT INTO agents (id, name, token, cash) VALUES (?, ?, ?, 100000.0)",
                (agent_id, name, f"token-{agent_id}"),
            )
        cursor.execute(
            "INSERT INTO subscriptions (follower_id, leader_id, status) VALUES (42, 41, 'active')"
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_every_hashed_id_column_is_blank_when_anonymized(self) -> None:
        checked = 0
        for dataset_name in get_research_dataset_names():
            columns, rows = fetch_research_export_rows(dataset_name)
            if not rows:
                continue
            for column in _masked_columns(columns):
                checked += 1
                for row in rows:
                    self.assertIn(
                        row[column],
                        (None, ""),
                        f"{dataset_name} still carries a raw {column}",
                    )
        self.assertGreater(checked, 0, "no dataset produced a row, nothing was measured")

    def test_the_hashed_counterpart_is_still_populated(self) -> None:
        columns, rows = fetch_research_export_rows("agents.csv")

        self.assertTrue(rows)
        self.assertIsNone(rows[0]["agent_id"])
        self.assertTrue(str(rows[0]["agent_hash"]).startswith("sha256:"))

    def test_the_raw_id_is_kept_when_anonymization_is_switched_off(self) -> None:
        columns, rows = fetch_research_export_rows("agents.csv", anonymize=False)

        self.assertTrue(rows)
        self.assertEqual({row["agent_id"] for row in rows}, {41, 42})

    def test_the_column_list_is_unchanged(self) -> None:
        columns, _ = fetch_research_export_rows("agents.csv")

        self.assertEqual(columns, get_research_export_columns("agents.csv"))
        self.assertIn("agent_id", columns)

    def test_a_column_without_a_hashed_counterpart_is_untouched(self) -> None:
        columns, rows = fetch_research_export_rows("subscriptions.csv")

        self.assertTrue(rows)
        self.assertNotIn("id", _masked_columns(columns))
        self.assertIsNotNone(rows[0]["id"])


if __name__ == "__main__":
    unittest.main()

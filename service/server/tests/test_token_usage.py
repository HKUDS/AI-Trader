# ruff: noqa: E402

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from routes import create_app
from routes_shared import RouteContext, utc_now_iso_z
from routes_token_usage import (
    TOKEN_USAGE_REPORT_WINDOW_SECONDS,
    _prune_idle_rate_limit_agents,
    register_token_usage_routes,
)
from token_usage import MAX_REPORTS_PER_BATCH, compute_cost_usd, estimate_tokens


class TokenUsageEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

        self.agent_token = "token-agent-a"
        self.other_token = "token-agent-b"
        self.agent_id = self._create_agent("agent-a", self.agent_token)
        self.other_id = self._create_agent("agent-b", self.other_token)

        app = FastAPI()
        register_token_usage_routes(app, RouteContext())
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, token: str) -> int:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES (?, ?, 0, 100000.0, ?, ?)
            """,
            (name, token, utc_now_iso_z(), utc_now_iso_z()),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _insert_backdated_usage(self, agent_id: int, model: str, day: str) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage
            (agent_id, model, provider, input_tokens, output_tokens, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (agent_id, model, "openai", 100, 100, 0.001, f"{day} 09:00:00"),
        )
        conn.commit()
        conn.close()

    def test_report_then_aggregate_sums_by_model(self) -> None:
        payload = {
            "model": "claude-opus-4-8",
            "provider": "anthropic",
            "input_tokens": 1000,
            "output_tokens": 500,
        }
        first = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["success"])

        second = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        self.assertEqual(second.status_code, 200)

        response = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token))
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(len(body["usage"]), 1)
        row = body["usage"][0]
        self.assertEqual(row["model"], "claude-opus-4-8")
        self.assertEqual(row["input_tokens"], 2000)
        self.assertEqual(row["output_tokens"], 1000)
        self.assertEqual(row["total_tokens"], 3000)
        self.assertEqual(row["call_count"], 2)
        # (2000/1M * 5) + (1000/1M * 25) = 0.01 + 0.025 = 0.035
        self.assertAlmostEqual(row["cost_usd"], 0.035, places=6)
        self.assertEqual(body["totals"]["total_tokens"], 3000)

    def test_unknown_model_has_no_cost(self) -> None:
        payload = {"model": "mystery-model-9", "input_tokens": 100, "output_tokens": 100}
        response = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["usage"]["cost_usd"])

        overview = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token))
        self.assertIsNone(overview.json()["usage"][0]["cost_usd"])
        self.assertIsNone(overview.json()["totals"]["cost_usd"])

    def test_model_and_provider_are_trimmed_before_storage(self) -> None:
        payload = {
            "model": "  gpt-5.2  ",
            "provider": "  openai  ",
            "input_tokens": 100,
            "output_tokens": 100,
        }
        response = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        self.assertEqual(response.status_code, 200)
        usage = response.json()["usage"]
        self.assertEqual(usage["model"], "gpt-5.2")
        self.assertEqual(usage["provider"], "openai")

    def test_whitespace_model_is_rejected(self) -> None:
        response = self.client.post(
            "/api/claw/usage",
            json={"model": "   ", "input_tokens": 10, "output_tokens": 10},
            headers=self._auth(self.agent_token),
        )
        self.assertEqual(response.status_code, 422)

    def test_grouping_splits_by_day_and_model(self) -> None:
        self._insert_backdated_usage(self.agent_id, "gpt-5.2", "2026-07-01")
        self._insert_backdated_usage(self.agent_id, "gpt-5.2", "2026-07-02")
        self._insert_backdated_usage(self.agent_id, "claude-haiku-4-5", "2026-07-02")

        body = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token)).json()
        buckets = {(row["usage_date"], row["model"]) for row in body["usage"]}
        self.assertEqual(
            buckets,
            {
                ("2026-07-01", "gpt-5.2"),
                ("2026-07-02", "gpt-5.2"),
                ("2026-07-02", "claude-haiku-4-5"),
            },
        )

    def test_date_filter_bounds_results(self) -> None:
        self._insert_backdated_usage(self.agent_id, "gpt-5.2", "2026-07-01")
        self._insert_backdated_usage(self.agent_id, "gpt-5.2", "2026-07-05")

        response = self.client.get(
            "/api/claw/usage",
            params={"start_date": "2026-07-02", "end_date": "2026-07-06"},
            headers=self._auth(self.agent_token),
        )
        dates = [row["usage_date"] for row in response.json()["usage"]]
        self.assertEqual(dates, ["2026-07-05"])

    def test_malformed_date_is_rejected(self) -> None:
        response = self.client.get(
            "/api/claw/usage",
            params={"start_date": "07/01/2026"},
            headers=self._auth(self.agent_token),
        )
        self.assertEqual(response.status_code, 400)

    def test_impossible_date_is_rejected(self) -> None:
        response = self.client.get(
            "/api/usage/models",
            params={"start_date": "2026-99-99"},
        )
        self.assertEqual(response.status_code, 400)

    def test_start_date_after_end_date_is_rejected(self) -> None:
        response = self.client.get(
            "/api/claw/usage",
            params={"start_date": "2026-07-05", "end_date": "2026-07-01"},
            headers=self._auth(self.agent_token),
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_token_is_unauthorized(self) -> None:
        payload = {"model": "gpt-5.2", "input_tokens": 10, "output_tokens": 10}
        self.assertEqual(self.client.post("/api/claw/usage", json=payload).status_code, 401)
        self.assertEqual(
            self.client.post("/api/claw/usage", json=payload, headers=self._auth("bogus")).status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/claw/usage").status_code, 401)

    def test_negative_and_oversized_tokens_are_rejected(self) -> None:
        negative = self.client.post(
            "/api/claw/usage",
            json={"model": "gpt-5.2", "input_tokens": -1, "output_tokens": 0},
            headers=self._auth(self.agent_token),
        )
        self.assertEqual(negative.status_code, 422)

        oversized = self.client.post(
            "/api/claw/usage",
            json={"model": "gpt-5.2", "input_tokens": 999_999_999, "output_tokens": 0},
            headers=self._auth(self.agent_token),
        )
        self.assertEqual(oversized.status_code, 422)

    def test_token_usage_reports_are_rate_limited_per_agent(self) -> None:
        payload = {"model": "gpt-5.2", "input_tokens": 10, "output_tokens": 10}
        with patch("routes_token_usage.TOKEN_USAGE_REPORT_WINDOW_LIMIT", 2):
            first = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
            second = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
            third = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)

    def test_per_agent_reads_are_isolated_but_overview_is_shared(self) -> None:
        self.client.post(
            "/api/claw/usage",
            json={"model": "gpt-5.2", "input_tokens": 100, "output_tokens": 100},
            headers=self._auth(self.agent_token),
        )
        self.client.post(
            "/api/claw/usage",
            json={"model": "claude-haiku-4-5", "input_tokens": 200, "output_tokens": 200},
            headers=self._auth(self.other_token),
        )

        mine = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token)).json()
        self.assertEqual({row["model"] for row in mine["usage"]}, {"gpt-5.2"})

        overview = self.client.get("/api/usage/models").json()
        self.assertEqual({row["model"] for row in overview["usage"]}, {"gpt-5.2", "claude-haiku-4-5"})

    def test_token_usage_routes_are_registered_on_full_app(self) -> None:
        client = TestClient(create_app())
        payload = {"model": "gpt-5.2", "input_tokens": 100, "output_tokens": 100}

        report = client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        self.assertEqual(report.status_code, 200)

        overview = client.get("/api/usage/models")
        self.assertEqual(overview.status_code, 200)
        self.assertIn("usage", overview.json())

    def test_responses_declare_utc_day_bucket(self) -> None:
        self._insert_backdated_usage(self.agent_id, "gpt-5.2", "2026-07-01")
        mine = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token)).json()
        overview = self.client.get("/api/usage/models").json()
        self.assertEqual(mine["timezone"], "UTC")
        self.assertEqual(overview["timezone"], "UTC")

    def test_batch_report_records_every_entry(self) -> None:
        batch = {
            "reports": [
                {"model": "gpt-5.2", "input_tokens": 100, "output_tokens": 100},
                {"model": "gpt-5.2", "input_tokens": 50, "output_tokens": 50},
                {"model": "claude-haiku-4-5", "input_tokens": 10, "output_tokens": 10},
            ]
        }
        response = self.client.post("/api/claw/usage/batch", json=batch, headers=self._auth(self.agent_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 3)

        body = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token)).json()
        by_model = {row["model"]: row for row in body["usage"]}
        self.assertEqual(by_model["gpt-5.2"]["call_count"], 2)
        self.assertEqual(by_model["gpt-5.2"]["total_tokens"], 300)
        self.assertEqual(by_model["claude-haiku-4-5"]["call_count"], 1)

    def test_batch_counts_as_a_single_write_against_the_rate_limit(self) -> None:
        batch = {"reports": [{"model": "gpt-5.2", "input_tokens": 1, "output_tokens": 1}] * 3}
        with patch("routes_token_usage.TOKEN_USAGE_REPORT_WINDOW_LIMIT", 1):
            first = self.client.post("/api/claw/usage/batch", json=batch, headers=self._auth(self.agent_token))
            second = self.client.post("/api/claw/usage/batch", json=batch, headers=self._auth(self.agent_token))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["count"], 3)
        self.assertEqual(second.status_code, 429)

    def test_empty_and_oversized_batches_are_rejected(self) -> None:
        empty = self.client.post(
            "/api/claw/usage/batch", json={"reports": []}, headers=self._auth(self.agent_token)
        )
        self.assertEqual(empty.status_code, 422)

        one = {"model": "gpt-5.2", "input_tokens": 1, "output_tokens": 1}
        oversized = self.client.post(
            "/api/claw/usage/batch",
            json={"reports": [one] * (MAX_REPORTS_PER_BATCH + 1)},
            headers=self._auth(self.agent_token),
        )
        self.assertEqual(oversized.status_code, 422)

    def test_repeated_client_event_id_is_not_double_counted(self) -> None:
        payload = {
            "model": "gpt-5.2",
            "input_tokens": 100,
            "output_tokens": 100,
            "client_event_id": "evt-1",
        }
        first = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        second = self.client.post("/api/claw/usage", json=payload, headers=self._auth(self.agent_token))
        self.assertFalse(first.json()["usage"]["deduplicated"])
        self.assertTrue(second.json()["usage"]["deduplicated"])
        self.assertEqual(first.json()["usage"]["id"], second.json()["usage"]["id"])

        body = self.client.get("/api/claw/usage", headers=self._auth(self.agent_token)).json()
        self.assertEqual(len(body["usage"]), 1)
        self.assertEqual(body["usage"][0]["call_count"], 1)
        self.assertEqual(body["usage"][0]["total_tokens"], 200)

    def test_overview_is_cached_within_ttl(self) -> None:
        self._insert_backdated_usage(self.agent_id, "gpt-5.2", "2026-07-01")
        first = self.client.get("/api/usage/models").json()

        # A row inserted after the first call must not appear until the cache expires.
        self._insert_backdated_usage(self.agent_id, "gpt-5-mini", "2026-07-02")
        second = self.client.get("/api/usage/models").json()

        self.assertEqual(second, first)
        self.assertNotIn("gpt-5-mini", {row["model"] for row in second["usage"]})

    def test_idle_agents_are_pruned_from_rate_limit_state(self) -> None:
        now_ts = time.time()
        state = {
            1: [now_ts],
            2: [now_ts - (TOKEN_USAGE_REPORT_WINDOW_SECONDS + 10)],
            3: [],
        }
        _prune_idle_rate_limit_agents(state, now_ts)
        self.assertEqual(set(state), {1})

    def test_cost_and_estimate_helpers(self) -> None:
        # (1_000_000/1M * 3) + (1_000_000/1M * 15) = 18.0 for claude-sonnet-4-6
        self.assertAlmostEqual(compute_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000), 18.0, places=6)
        self.assertIsNone(compute_cost_usd("unknown-model", 100, 100))
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd" * 25), 25)


if __name__ == "__main__":
    unittest.main()

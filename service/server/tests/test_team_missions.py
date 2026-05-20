import csv
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
from research_exports import export_team_tables
from routes_shared import utc_now_iso_z
from team_matching import form_team_groups
from team_missions import (
    auto_form_teams,
    create_team_mission,
    get_agent_team_missions,
    get_team,
    join_team_mission,
    record_team_message_from_signal,
    score_team_contributions,
    settle_team_mission,
    submit_team,
)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TeamMissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.admin_agent = self._create_agent("admin-agent", role="team_mission_admin")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str, *, profit: float = 0.0, market: str = "crypto", role: str = "agent") -> int:
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
        cursor.execute(
            """
            INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
            VALUES (?, ?, 100000.0, 0.0, ?, ?)
            """,
            (agent_id, 100000.0 + profit, profit, now),
        )
        signal_id = 10_000 + agent_id
        for offset, message_type in enumerate(("operation", "strategy", "discussion")):
            cursor.execute(
                """
                INSERT INTO signals
                (signal_id, agent_id, message_type, market, signal_type, symbol, title,
                 content, timestamp, created_at, executed_at)
                VALUES (?, ?, ?, ?, ?, 'BTC', ?, ?, ?, ?, ?)
                """,
                (
                    signal_id + offset * 100_000,
                    agent_id,
                    message_type,
                    market,
                    "realtime" if message_type == "operation" else message_type,
                    f"{message_type} {name}",
                    f"{message_type} content from {name}",
                    int(datetime.now(timezone.utc).timestamp()),
                    now,
                    now,
                ),
            )
        conn.commit()
        conn.close()
        return agent_id

    def _create_mission(self, key: str, **overrides):
        now = datetime.now(timezone.utc)
        payload = {
            "mission_key": key,
            "title": f"Team Mission {key}",
            "description": "Coordinate a market thesis and submit one team conclusion.",
            "market": "crypto",
            "symbol": "BTC",
            "assignment_mode": "random",
            "team_size_min": 3,
            "team_size_max": 3,
            "start_at": iso(now - timedelta(minutes=5)),
            "submission_due_at": iso(now + timedelta(hours=1)),
            "rules_json": {
                "team_reward_points": {"1": 30, "2": 20, "3": 10},
                "contribution_reward_per_point": 1,
            },
        }
        payload.update(overrides)
        return create_team_mission(payload, created_by_agent_id=self.admin_agent)

    def test_matching_modes_are_deterministic_and_distinct(self):
        features = [
            {"agent_id": 1, "primary_market": "crypto", "feature_score": 50.0},
            {"agent_id": 2, "primary_market": "crypto", "feature_score": 10.0},
            {"agent_id": 3, "primary_market": "us-stock", "feature_score": 45.0},
            {"agent_id": 4, "primary_market": "us-stock", "feature_score": 5.0},
            {"agent_id": 5, "primary_market": "polymarket", "feature_score": 35.0},
            {"agent_id": 6, "primary_market": "polymarket", "feature_score": 15.0},
        ]

        random_a = form_team_groups(features, assignment_mode="random", team_size=2, mission_key="match-check")
        random_b = form_team_groups(features, assignment_mode="random", team_size=2, mission_key="match-check")
        homogeneous = form_team_groups(features, assignment_mode="homogeneous", team_size=2, mission_key="match-check")
        heterogeneous = form_team_groups(features, assignment_mode="heterogeneous", team_size=2, mission_key="match-check")

        self.assertEqual(random_a, random_b)
        self.assertNotEqual(homogeneous, heterogeneous)
        self.assertEqual([member["agent_id"] for member in homogeneous[0]], [2, 1])
        self.assertEqual([member["agent_id"] for member in heterogeneous[0]], [3, 2])

    def test_thirty_agent_mission_forms_ten_teams_settles_rewards_and_exports(self):
        markets = ["crypto", "us-stock", "polymarket"]
        agent_ids = [
            self._create_agent(f"team-agent-{idx:02d}", profit=idx * 100.0, market=markets[idx % len(markets)])
            for idx in range(30)
        ]
        mission = self._create_mission("ten-team-mission")

        first_join = join_team_mission(mission["mission_key"], agent_ids[0])
        second_join = join_team_mission(mission["mission_key"], agent_ids[0])
        self.assertTrue(first_join["joined"])
        self.assertFalse(second_join["joined"])
        for agent_id in agent_ids[1:]:
            join_team_mission(mission["mission_key"], agent_id)

        formed = auto_form_teams(mission["mission_key"], assignment_mode="random")
        teams = formed["teams"]
        self.assertEqual(len(teams), 10)

        signal_id = 50_000
        for team_row in teams:
            detail = get_team(team_row["team_key"])
            self.assertEqual(len(detail["members"]), 3)
            self.assertTrue(all(member["role"] for member in detail["members"]))
            lead_agent_id = detail["members"][0]["agent_id"]

            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO signals
                (signal_id, agent_id, message_type, market, signal_type, symbol, title,
                 content, timestamp, created_at)
                VALUES (?, ?, 'strategy', 'crypto', 'strategy', 'BTC', ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    lead_agent_id,
                    f"Strategy for {detail['name']}",
                    f"Evidence and role synthesis for {detail['name']}",
                    int(datetime.now(timezone.utc).timestamp()),
                    utc_now_iso_z(),
                ),
            )
            record_team_message_from_signal(
                cursor,
                mission_key=mission["mission_key"],
                team_key=team_row["team_key"],
                agent_id=lead_agent_id,
                signal_id=signal_id,
                message_type="strategy",
                content=f"Team thesis for {detail['name']}",
            )
            conn.commit()
            conn.close()
            signal_id += 1

            submit_team(
                team_row["team_key"],
                lead_agent_id,
                {
                    "title": f"Consensus {detail['name']}",
                    "content": "Final team view with risk framing and evidence.",
                    "prediction_json": {"symbol": "BTC", "direction": "up"},
                    "confidence": 0.75,
                },
            )

        scored = score_team_contributions(mission["mission_key"])
        self.assertGreaterEqual(scored["inserted"], 10)

        settled = settle_team_mission(mission["mission_key"])
        leaderboard = settled["leaderboard"]
        self.assertEqual(len(leaderboard), 10)
        self.assertEqual([row["rank"] for row in leaderboard], list(range(1, 11)))

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM team_results")
        self.assertEqual(cursor.fetchone()["count"], 10)
        cursor.execute("SELECT COUNT(*) AS count FROM team_submissions")
        self.assertEqual(cursor.fetchone()["count"], 10)
        cursor.execute("SELECT COUNT(*) AS count FROM team_contributions")
        self.assertGreaterEqual(cursor.fetchone()["count"], 20)
        cursor.execute("SELECT COUNT(*) AS count FROM agent_reward_ledger WHERE source_type LIKE 'team_%'")
        self.assertGreater(cursor.fetchone()["count"], 0)
        cursor.execute("SELECT event_type FROM experiment_events")
        event_types = {row["event_type"] for row in cursor.fetchall()}
        self.assertTrue({
            "team_mission_created",
            "team_mission_joined",
            "team_created",
            "team_joined",
            "team_role_assigned",
            "team_signal_linked",
            "team_submission_created",
            "team_contribution_scored",
            "team_mission_settled",
            "team_reward_granted",
        }.issubset(event_types))
        conn.close()

        mine = get_agent_team_missions(agent_ids[0])
        self.assertEqual(mine["missions"][0]["mission_key"], mission["mission_key"])
        self.assertTrue(mine["missions"][0]["team_key"])

        export_dir = Path(self.tmp.name) / "exports"
        paths = export_team_tables(export_dir, mission_key=mission["mission_key"])
        expected_files = {
            "team_missions.csv",
            "teams.csv",
            "team_members.csv",
            "team_messages.csv",
            "team_submissions.csv",
            "team_contributions.csv",
            "team_results.csv",
        }
        self.assertEqual(set(paths), expected_files)
        with open(paths["team_results.csv"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 10)


if __name__ == "__main__":
    unittest.main()

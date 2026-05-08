import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import cache
import database
import routes_shared
import services
import challenges
import market_intel
import team_missions
from challenge_scoring import rank_scored_results, score_agent_trades
from experiment_events import record_event, record_reward_event
from research_exports import fetch_challenge_export_rows, fetch_team_export_rows
from rewards import grant_agent_reward, reverse_agent_reward
from routes_shared import utc_now_iso_z
from team_matching import assign_roles, form_team_groups
from team_scoring import (
    contribution_score_for_message,
    contribution_score_for_submission,
    score_team_results,
)
from utils import (
    _extract_token,
    build_agent_password_reset_challenge,
    cleanup_expired_tokens,
    generate_verification_code,
    hash_password,
    recover_signed_address,
    validate_address,
    verify_password,
)


class UtilityFunctionTests(unittest.TestCase):
    def test_password_hash_verification_and_invalid_hash(self) -> None:
        password_hash = hash_password("secret")

        self.assertTrue(verify_password("secret", password_hash))
        self.assertFalse(verify_password("wrong", password_hash))
        self.assertFalse(verify_password("secret", "not-a-valid-hash"))

    def test_verification_code_is_zero_padded(self) -> None:
        with patch("utils.random.randint", return_value=42):
            self.assertEqual(generate_verification_code(), "000042")

    def test_password_reset_challenge_contains_expected_fields(self) -> None:
        challenge = build_agent_password_reset_challenge(
            7,
            "agent",
            "0xabc",
            "nonce",
            "2026-01-01T00:00:00Z",
        )

        self.assertIn("AI-Trader password reset", challenge)
        self.assertIn("Agent ID: 7", challenge)
        self.assertIn("Sign this message to reset your password.", challenge)

    def test_address_and_token_helpers_cover_empty_invalid_and_bearer(self) -> None:
        self.assertEqual(validate_address(""), "")
        self.assertEqual(validate_address("0x" + "A" * 40), "0x" + "a" * 40)
        self.assertEqual(validate_address("B" * 40), "0x" + "b" * 40)
        self.assertEqual(validate_address("0xnot-hex"), "")
        self.assertIsNone(_extract_token(None))
        self.assertEqual(_extract_token("Bearer abc"), "abc")
        self.assertEqual(_extract_token("raw-token"), "raw-token")

    def test_recover_signed_address_rejects_empty_or_invalid_signature(self) -> None:
        self.assertIsNone(recover_signed_address("", "sig"))
        self.assertIsNone(recover_signed_address("message", ""))
        self.assertIsNone(recover_signed_address("message", "bad-signature"))


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        cache._redis_client = None
        cache._last_connect_attempt_at = 0.0
        cache._last_connect_error = None

    def test_namespaced_rejects_blank_keys(self) -> None:
        with self.assertRaises(ValueError):
            cache._namespaced(" ")

    def test_unconfigured_cache_noops(self) -> None:
        with patch("cache.REDIS_ENABLED", False), patch("cache.REDIS_URL", ""):
            self.assertFalse(cache.redis_configured())
            self.assertIsNone(cache.get_redis_client())
            self.assertIsNone(cache.get_json("key"))
            self.assertFalse(cache.set_json("key", {"a": 1}))
            self.assertEqual(cache.delete("key"), 0)
            self.assertEqual(cache.delete_pattern("key:*"), 0)
            self.assertIsNone(cache.acquire_lock("name"))
            self.assertEqual(cache.publish("channel", {"a": 1}), 0)
            self.assertIsNone(cache.create_pubsub())

    def test_redis_client_success_and_cache_operations(self) -> None:
        fake_client = Mock()
        fake_client.get.side_effect = ['{"ok":true}', None, "not-json"]
        fake_client.set.return_value = True
        fake_client.delete.return_value = 2
        fake_client.scan_iter.return_value = ["a", "b"]
        fake_client.publish.return_value = 3
        fake_client.pubsub.return_value = "pubsub"
        fake_lock = object()
        fake_client.lock.return_value = fake_lock
        fake_redis = Mock()
        fake_redis.Redis.from_url.return_value = fake_client

        with (
            patch("cache.REDIS_ENABLED", True),
            patch("cache.REDIS_URL", "redis://localhost:6379/0"),
            patch("cache.redis", fake_redis),
        ):
            self.assertIs(cache.get_redis_client(), fake_client)
            self.assertEqual(cache.get_cache_status()["available"], True)
            self.assertEqual(cache.get_json("payload"), {"ok": True})
            self.assertIsNone(cache.get_json("missing"))
            self.assertIsNone(cache.get_json("bad-json"))
            self.assertTrue(cache.set_json("payload", {"value": 1}, ttl_seconds=30))
            self.assertTrue(cache.set_json("payload", {"value": 1}, ttl_seconds=0))
            self.assertEqual(cache.delete("payload"), 2)
            self.assertEqual(cache.delete_pattern("payload:*"), 2)
            self.assertIs(cache.acquire_lock("name"), fake_lock)
            self.assertEqual(cache.publish("events", {"value": 1}), 3)
            self.assertEqual(cache.publish("events", "ready"), 3)
            self.assertEqual(cache.create_pubsub(), "pubsub")

    def test_redis_connection_failure_and_retry_window(self) -> None:
        fake_redis = Mock()
        fake_redis.Redis.from_url.side_effect = RuntimeError("boom")

        with (
            patch("cache.REDIS_ENABLED", True),
            patch("cache.REDIS_URL", "redis://localhost:6379/0"),
            patch("cache.redis", fake_redis),
            patch("cache.time.time", return_value=100.0),
        ):
            self.assertIsNone(cache.get_redis_client())
            self.assertEqual(cache._last_connect_error, "boom")
            self.assertIsNone(cache.get_redis_client())
            self.assertEqual(fake_redis.Redis.from_url.call_count, 1)

    def test_cache_inner_lock_returns_existing_client_or_retry_none(self) -> None:
        fake_client = Mock()

        class ExistingClientLock:
            def __enter__(self):
                cache._redis_client = fake_client

            def __exit__(self, _exc_type, _exc, _tb):
                return False

        with (
            patch("cache.REDIS_ENABLED", True),
            patch("cache.REDIS_URL", "redis://localhost:6379/0"),
            patch("cache.redis", Mock()),
            patch("cache._client_lock", ExistingClientLock()),
            patch("cache.time.time", return_value=100.0),
        ):
            self.assertIs(cache.get_redis_client(), fake_client)

        cache._redis_client = None
        cache._last_connect_attempt_at = 100.0

        class RetryWindowLock:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                return False

        with (
            patch("cache.REDIS_ENABLED", True),
            patch("cache.REDIS_URL", "redis://localhost:6379/0"),
            patch("cache.redis", Mock()),
            patch("cache._client_lock", RetryWindowLock()),
            patch("cache.time.time", return_value=105.0),
        ):
            self.assertIsNone(cache.get_redis_client())

    def test_delete_pattern_with_no_matches_returns_zero(self) -> None:
        fake_client = Mock()
        fake_client.scan_iter.return_value = []
        with patch("cache.get_redis_client", return_value=fake_client):
            self.assertEqual(cache.delete_pattern("missing:*"), 0)
            fake_client.delete.assert_not_called()


class ScoringTests(unittest.TestCase):
    def test_challenge_scoring_covers_invalid_short_cover_and_manual_disqualification(self) -> None:
        challenge = {
            "initial_capital": 1000.0,
            "max_position_pct": 0,
            "max_drawdown_pct": 1,
            "scoring_method": "risk_adjusted",
            "rules_json": {"disqualify_on_drawdown": True, "allowed_drawdown": 0, "drawdown_penalty": 2},
        }
        participant = {"agent_id": 1, "starting_cash": 1000.0}
        short_result = score_agent_trades(
            challenge,
            participant,
            [
                {"id": 2, "market": "crypto", "symbol": "BTC", "side": "cover", "price": 90, "quantity": 1, "executed_at": "2"},
                {"id": 1, "market": "crypto", "symbol": "BTC", "side": "short", "price": 100, "quantity": 1, "executed_at": "1"},
            ],
        )
        self.assertAlmostEqual(short_result["ending_value"], 1010.0)
        self.assertIsNone(short_result["disqualified_reason"])

        invalid = score_agent_trades(challenge, participant, [{"side": "buy", "price": 0, "quantity": 1}])
        self.assertEqual(invalid["disqualified_reason"], "invalid_trade_snapshot")

        manual = score_agent_trades(challenge, {"agent_id": 2, "status": "disqualified"}, [])
        self.assertEqual(manual["disqualified_reason"], "manual_disqualification")

        no_rules = score_agent_trades({"initial_capital": 0}, {"agent_id": 3}, [])
        self.assertEqual(no_rules["return_pct"], 0.0)

    def test_challenge_scoring_disqualifies_conflicting_or_oversized_trades(self) -> None:
        base = {"initial_capital": 1000.0, "max_position_pct": 100.0, "rules_json": "not-json"}
        participant = {"agent_id": 1}

        self.assertEqual(
            score_agent_trades(base, participant, [{"side": "sell", "price": 10, "quantity": 1, "symbol": "BTC"}])["disqualified_reason"],
            "sell_exceeds_challenge_long:BTC",
        )
        self.assertEqual(
            score_agent_trades(base, participant, [{"side": "cover", "price": 10, "quantity": 1, "symbol": "BTC"}])["disqualified_reason"],
            "cover_exceeds_challenge_short:BTC",
        )
        self.assertEqual(
            score_agent_trades(base, participant, [{"side": "hold", "price": 10, "quantity": 1}])["disqualified_reason"],
            "unsupported_side:hold",
        )
        self.assertEqual(
            score_agent_trades(
                base,
                participant,
                [
                    {"side": "buy", "price": 10, "quantity": 1, "symbol": "BTC"},
                    {"side": "short", "price": 10, "quantity": 1, "symbol": "BTC"},
                ],
            )["disqualified_reason"],
            "short_used_while_long:BTC",
        )
        self.assertEqual(
            score_agent_trades(
                base,
                participant,
                [
                    {"side": "short", "price": 10, "quantity": 1, "symbol": "BTC"},
                    {"side": "buy", "price": 10, "quantity": 1, "symbol": "BTC"},
                ],
            )["disqualified_reason"],
            "buy_used_while_short:BTC",
        )

        partial_cover = score_agent_trades(
            {"initial_capital": 1000.0, "max_position_pct": 0},
            participant,
            [
                {"side": "short", "price": 100, "quantity": 2, "symbol": "BTC", "market": "crypto"},
                {"side": "cover", "price": 90, "quantity": 1, "symbol": "BTC", "market": "crypto"},
            ],
        )
        self.assertEqual(partial_cover["metrics"]["positions"][0]["quantity"], -1.0)

        pre_disqualified = score_agent_trades(
            {"initial_capital": 1000.0, "max_position_pct": 0},
            {"agent_id": 1, "disqualified_reason": "preexisting"},
            [{"side": "buy", "price": 10, "quantity": 1}],
        )
        self.assertEqual(pre_disqualified["disqualified_reason"], "preexisting")

        drawdown = score_agent_trades(
            {
                "initial_capital": 1000.0,
                "max_position_pct": 0,
                "max_drawdown_pct": 1.0,
                "rules_json": {"disqualify_on_drawdown": True},
            },
            participant,
            [
                {"side": "buy", "price": 100, "quantity": 5, "symbol": "BTC", "market": "crypto"},
                {"side": "sell", "price": 90, "quantity": 5, "symbol": "BTC", "market": "crypto"},
            ],
        )
        self.assertEqual(drawdown["disqualified_reason"], "max_drawdown_pct_exceeded")

    def test_rank_scored_results_keeps_disqualified_unranked(self) -> None:
        ranked = rank_scored_results([
            {"agent_id": 1, "final_score": 10.0},
            {"agent_id": 2, "final_score": None, "disqualified_reason": "bad"},
            {"agent_id": 3, "final_score": 20.0},
        ])

        self.assertEqual([row["rank"] for row in ranked], [2, None, 1])

    def test_team_matching_and_scoring_branches(self) -> None:
        features = [
            {"agent_id": 1, "primary_market": "a", "feature_score": 1},
            {"agent_id": 2, "primary_market": "b", "feature_score": 2},
            {"agent_id": 3, "primary_market": "c", "feature_score": 3},
        ]
        self.assertEqual(len(form_team_groups(features, assignment_mode="heterogeneous", team_size=2, mission_key="m")), 2)
        self.assertEqual(assign_roles([{"agent_id": 1}, {"agent_id": 2}], []), {1: "lead", 2: "analyst"})
        self.assertEqual(contribution_score_for_message({"message_type": "discussion", "content": "x" * 800}), 5.0)
        self.assertEqual(contribution_score_for_message({"message_type": "reply", "content": ""}), 2.0)
        self.assertEqual(contribution_score_for_message({"message_type": "other", "content": ""}), 1.0)
        self.assertEqual(contribution_score_for_submission({"confidence": "bad", "content": "x" * 2000}), 8.5)

        results = score_team_results(
            {"id": 1, "assignment_mode": "random"},
            [{"id": 1, "formation_method": "manual"}, {"id": 2, "formation_method": "manual"}],
            {1: [{"agent_id": 1, "return_pct_30d": "10"}], 2: []},
            {1: [{"confidence": 0.5}], 2: []},
            {1: [{"agent_id": 1, "contribution_score": "4"}], 2: []},
        )
        self.assertEqual([row["rank"] for row in results], [1, 2])
        self.assertGreater(results[0]["prediction_score"], 0)


class ChallengeAndMissionHelperTests(unittest.TestCase):
    def test_challenge_serialization_datetime_key_and_validation_errors(self) -> None:
        self.assertEqual(challenges._model_dump({"a": 1}), {"a": 1})

        class Model:
            def model_dump(self):
                return {"b": 2}

        self.assertEqual(challenges._model_dump(Model()), {"b": 2})
        self.assertIsNone(challenges._json_dumps(None))
        self.assertEqual(challenges._json_dumps("raw"), "raw")
        self.assertEqual(challenges._json_loads("", {"fallback": True}), {"fallback": True})
        self.assertEqual(challenges._json_loads({"x": 1}), {"x": 1})
        with self.assertRaises(challenges.ChallengeError):
            challenges._parse_dt("not-date")
        with self.assertRaises(challenges.ChallengeError):
            challenges._normalize_key("***", "")
        self.assertIn("my-title", challenges._normalize_key(None, "My Title"))
        self.assertEqual(challenges._derive_status("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "settled"), "settled")
        with self.assertRaises(challenges.ChallengeError):
            challenges._derive_status("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "bad")
        self.assertEqual(challenges._serialize_challenge({}, 1), {})
        serialized = challenges._serialize_challenge({"rules_json": '{"a": 1}'}, 2)
        self.assertEqual(serialized["rules"], {"a": 1})
        self.assertEqual(serialized["participant_count"], 2)

        for payload, message in [
            ({}, "title is required"),
            ({"title": "T"}, "market is required"),
            ({"title": "T", "market": "crypto", "scoring_method": "bad"}, "Unsupported scoring_method"),
            (
                {
                    "title": "T",
                    "market": "crypto",
                    "start_at": "2026-01-02T00:00:00Z",
                    "end_at": "2026-01-01T00:00:00Z",
                },
                "end_at must be after start_at",
            ),
        ]:
            with self.assertRaisesRegex(challenges.ChallengeError, message):
                challenges.create_challenge(payload, 1)

    def test_team_mission_serialization_datetime_key_variant_and_validation_errors(self) -> None:
        self.assertEqual(team_missions._model_dump(None), {})
        self.assertEqual(team_missions._model_dump({"a": 1}), {"a": 1})
        self.assertIsNone(team_missions._json_dumps(None))
        self.assertEqual(team_missions._json_dumps("raw"), "raw")
        self.assertEqual(team_missions._json_loads("", {"fallback": True}), {"fallback": True})
        self.assertEqual(team_missions._json_loads("[1]"), [1])
        with self.assertRaises(team_missions.TeamMissionError):
            team_missions._parse_dt("not-date")
        with self.assertRaises(team_missions.TeamMissionError):
            team_missions._normalize_key("***", "", "mission")
        self.assertIn("team-title", team_missions._normalize_key(None, "Team Title", "mission"))
        self.assertEqual(team_missions._derive_status("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "canceled"), "canceled")
        with self.assertRaises(team_missions.TeamMissionError):
            team_missions._derive_status("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "bad")
        self.assertEqual(team_missions._serialize_mission({}, 1, 2), {})
        mission = team_missions._serialize_mission({"required_roles_json": '["lead"]', "rules_json": '{"x": 1}'}, 1, 2)
        self.assertEqual(mission["required_roles"], ["lead"])
        self.assertEqual(mission["rules"], {"x": 1})
        self.assertEqual(team_missions._serialize_team({"id": 1}, 3)["member_count"], 3)

        class Cursor:
            def __init__(self, row=None):
                self.row = row
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))

            def fetchone(self):
                return self.row

        self.assertEqual(team_missions._resolve_variant(Cursor(), None, 1, "A"), "A")
        self.assertEqual(team_missions._resolve_variant(Cursor({"variant_key": "B"}), "exp", 1, "A"), "B")
        cursor = Cursor()
        self.assertEqual(team_missions._resolve_variant(cursor, "exp", 1, "A"), "A")
        self.assertTrue(any("INSERT INTO experiment_assignments" in sql for sql, _params in cursor.statements))

        for payload, message in [
            ({}, "title is required"),
            ({"title": "T"}, "market is required"),
            (
                {
                    "title": "T",
                    "market": "crypto",
                    "start_at": "2026-01-02T00:00:00Z",
                    "submission_due_at": "2026-01-01T00:00:00Z",
                },
                "submission_due_at must be after start_at",
            ),
            ({"title": "T", "market": "crypto", "team_size_min": -1}, "Invalid team size settings"),
            ({"title": "T", "market": "crypto", "team_size_min": 3, "team_size_max": 2}, "Invalid team size settings"),
        ]:
            with self.assertRaisesRegex(team_missions.TeamMissionError, message):
                team_missions.create_team_mission(payload, 1)


class MarketIntelUtilityTests(unittest.TestCase):
    def setUp(self) -> None:
        market_intel._stock_quote_cache_local.clear()

    def test_datetime_parsers_market_hours_and_price_metadata(self) -> None:
        self.assertIsNone(market_intel._parse_iso_datetime(None))
        self.assertIsNone(market_intel._parse_iso_datetime(" "))
        self.assertIsNone(market_intel._parse_iso_datetime("bad"))
        self.assertEqual(market_intel._parse_iso_datetime("2026-01-01T00:00:00").tzinfo, timezone.utc)
        self.assertEqual(market_intel._parse_alpha_intraday_timestamp("bad"), None)
        self.assertTrue(market_intel._parse_alpha_intraday_timestamp("2026-01-05 10:30:00").endswith("Z"))
        self.assertIsNone(market_intel._daily_close_as_of_iso("bad"))
        self.assertTrue(market_intel._daily_close_as_of_iso("2026-01-05").endswith("Z"))
        self.assertFalse(market_intel._is_us_market_open(datetime(2026, 1, 4, 15, 0, tzinfo=timezone.utc)))
        self.assertTrue(market_intel._is_us_market_open(datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)))

        with patch("market_intel._utc_now", return_value=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)):
            stale = market_intel._build_stock_price_metadata(None, None)
            realtime = market_intel._build_stock_price_metadata("2026-01-05T14:59:30Z", "alpha_vantage_time_series_intraday")
        self.assertTrue(stale["price_stale"])
        self.assertEqual(realtime["price_status"], "realtime")

        with patch("market_intel._utc_now", return_value=datetime(2026, 1, 5, 22, 0, tzinfo=timezone.utc)):
            session_close = market_intel._build_stock_price_metadata("2026-01-05T21:00:00Z", "alpha_vantage_time_series_intraday")
        self.assertEqual(session_close["price_status"], "session_close")

    def test_stock_quote_cache_get_set_and_fetch_paths(self) -> None:
        with patch("market_intel.time.time", return_value=100.0), patch("market_intel.set_json") as mock_set:
            market_intel._stock_quote_cache_set("AAPL", {"available": True, "price": 1}, ttl_seconds=10)
        mock_set.assert_called_once()

        with patch("market_intel.time.time", return_value=105.0):
            self.assertEqual(market_intel._stock_quote_cache_get("AAPL")["price"], 1)

        with patch("market_intel.time.time", return_value=200.0), patch("market_intel.get_json", return_value={"available": False}):
            self.assertEqual(market_intel._stock_quote_cache_get("AAPL"), {"available": False})

        payload = {
            "Meta Data": {"3. Last Refreshed": "2026-01-05 10:30:00"},
            "Time Series (1min)": {"2026-01-05 10:30:00": {"4. close": "123.456"}},
        }
        quote = market_intel._extract_intraday_quote(payload)
        self.assertEqual(quote["current_price"], 123.46)
        self.assertIsNone(market_intel._extract_intraday_quote({}))
        self.assertIsNone(market_intel._extract_intraday_quote({"Time Series (1min)": {"x": {}}}))

        with patch("market_intel.ALPHA_VANTAGE_API_KEY", "demo"):
            self.assertIsNone(market_intel._fetch_stock_quote_payload("AAPL"))
        with patch("market_intel._stock_quote_cache_get", return_value={"available": False}):
            self.assertIsNone(market_intel._get_stock_quote_payload("AAPL"))
        with (
            patch("market_intel._stock_quote_cache_get", return_value=None),
            patch("market_intel._fetch_stock_quote_payload", return_value={"available": True, "current_price": 1}),
            patch("market_intel._stock_quote_cache_set") as mock_cache_set,
        ):
            self.assertEqual(market_intel._get_stock_quote_payload("AAPL")["current_price"], 1)
        self.assertTrue(mock_cache_set.called)

    def test_stock_quote_extraction_decorate_and_alpha_errors(self) -> None:
        self.assertIsNone(market_intel._parse_alpha_timestamp(None))
        self.assertEqual(market_intel._parse_alpha_timestamp("20260105T1500"), "2026-01-05T15:00:00Z")
        self.assertEqual(market_intel._format_price_levels([1, 2, 3, 4]), "1.00, 2.00, 3.00")
        self.assertEqual(market_intel._format_price_levels([]), "N/A")

        with patch("market_intel._get_stock_quote_payload", return_value={"current_price": 55, "price_as_of": "2026-01-05T15:00:00Z", "price_source": "manual"}):
            decorated = market_intel._decorate_stock_analysis_with_quote(
                {"available": True, "symbol": "AAPL", "current_price": 50, "analysis": {"as_of": "2026-01-03"}}
            )
        self.assertEqual(decorated["current_price"], 55)
        self.assertEqual(market_intel._decorate_stock_analysis_with_quote({"available": False}), {"available": False})

        with patch("market_intel.ALPHA_VANTAGE_API_KEY", "demo"):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                market_intel._alpha_vantage_get({})

        response = Mock()
        response.json.return_value = {"Error Message": "bad"}
        with patch("market_intel.ALPHA_VANTAGE_API_KEY", "key"), patch("market_intel.requests.get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "bad"):
                market_intel._alpha_vantage_get({"function": "X"})

    def test_openrouter_text_and_news_normalization(self) -> None:
        self.assertEqual(market_intel._extract_openrouter_text({}), "")
        self.assertEqual(market_intel._extract_openrouter_text({"choices": [{"message": {"content": " hi "}}]}), "hi")
        self.assertEqual(
            market_intel._extract_openrouter_text({"choices": [{"message": {"content": [" a ", {"text": " b "}, {"no": "x"}]}}]}),
            "a\nb",
        )
        self.assertIsNone(market_intel._normalize_news_item({"title": ""}))
        self.assertIsNone(market_intel._normalize_news_item({"title": "T", "time_published": "bad"}))
        item = market_intel._normalize_news_item(
            {
                "title": " News ",
                "url": " https://example.com ",
                "source": " Source ",
                "time_published": "20260105T150000",
                "ticker_sentiment": [
                    {"ticker": "AAPL", "relevance_score": "0.5", "ticker_sentiment_score": "0.2", "ticker_sentiment_label": "Bullish"},
                    {"ticker": ""},
                    "bad",
                ],
                "topics": [{"topic": "Tech", "relevance_score": "0.9"}, {"topic": ""}, "bad"],
            }
        )
        self.assertEqual(item["title"], "News")
        self.assertEqual(item["ticker_sentiment"][0]["ticker"], "AAPL")
        self.assertEqual(item["topics"][0]["topic"], "Tech")


class DatabaseBackedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_counter = 0
        self.agent_id = self._create_agent("agent")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_agent(self, name: str | None = None) -> int:
        self.agent_counter += 1
        agent_name = name or f"agent-{self.agent_counter}"
        now = utc_now_iso_z()
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (name, token, points, cash, created_at, updated_at)
            VALUES (?, ?, 0, 100000.0, ?, ?)
            """,
            (agent_name, f"token-{agent_name}", now, now),
        )
        agent_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_reward_grant_idempotent_history_and_reverse(self) -> None:
        first = grant_agent_reward(self.agent_id, 5, "reason", source_type="test", source_id=1, metadata={"b": 2})
        second = grant_agent_reward(self.agent_id, 5, "reason", source_type="test", source_id=1)

        self.assertTrue(second["idempotent"])
        self.assertEqual(second["ledger_id"], first["ledger_id"])
        history = __import__("rewards").get_agent_reward_history(self.agent_id, limit=999, offset=-5)
        self.assertEqual(len(history), 1)

        reversed_result = reverse_agent_reward(first["ledger_id"], reason="void")
        self.assertTrue(reversed_result["reversed"])
        self.assertFalse(reverse_agent_reward(first["ledger_id"])["reversed"])
        self.assertFalse(grant_agent_reward(self.agent_id, 0, "zero")["success"])

    def test_reward_cursor_path_and_rollback_on_error(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        result = grant_agent_reward(self.agent_id, 3, "cursor", cursor=cursor)
        self.assertTrue(result["success"])
        reversed_result = reverse_agent_reward(result["ledger_id"], cursor=cursor)
        self.assertTrue(reversed_result["reversed"])
        conn.rollback()
        conn.close()

        class FailingCursor:
            lastrowid = 0

            def execute(self, sql, params=()):
                if sql.strip().startswith("INSERT INTO agent_reward_ledger"):
                    raise RuntimeError("insert failed")

        fake_conn = Mock()
        fake_conn.cursor.return_value = FailingCursor()
        with patch("rewards.get_db_connection", return_value=fake_conn), self.assertRaises(RuntimeError):
            grant_agent_reward(self.agent_id, 1, "boom")
        fake_conn.rollback.assert_called_once()
        fake_conn.close.assert_called_once()

    def test_events_with_own_connection_and_cursor(self) -> None:
        event_id = record_event(
            "custom",
            actor_agent_id=self.agent_id,
            object_type="thing",
            object_id=123,
            metadata={"value": object()},
        )
        self.assertTrue(event_id)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        reward_event_id = record_reward_event(self.agent_id, 7, "bonus", source_type="manual", source_id=456, cursor=cursor)
        conn.commit()
        cursor.execute("SELECT event_type, object_id FROM experiment_events WHERE event_id = ?", (reward_event_id,))
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row["event_type"], "reward_granted")
        self.assertEqual(row["object_id"], "456")

    def test_event_json_dumps_none(self) -> None:
        self.assertIsNone(__import__("experiment_events")._json_dumps(None))

    def test_cleanup_expired_tokens_deletes_only_expired(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES ('u@example.com', 'hash', ?)",
            (utc_now_iso_z(),),
        )
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO user_tokens (user_id, token, expires_at, created_at) VALUES (?, 'old', '2000-01-01T00:00:00Z', ?)",
            (user_id, utc_now_iso_z()),
        )
        cursor.execute(
            "INSERT INTO user_tokens (user_id, token, expires_at, created_at) VALUES (?, 'new', '2999-01-01T00:00:00Z', ?)",
            (user_id, utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

        self.assertEqual(cleanup_expired_tokens(), 1)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM user_tokens")
        tokens = [row["token"] for row in cursor.fetchall()]
        conn.close()
        self.assertEqual(tokens, ["new"])

        self.assertEqual(cleanup_expired_tokens(), 0)

    def test_agent_user_and_signal_service_helpers(self) -> None:
        self.assertIsNone(services._get_agent_by_token(""))
        self.assertIsNone(services._get_agent_by_id(None))
        self.assertIsNone(services._get_agent_by_name(" "))
        self.assertEqual(services._get_agent_by_token("token-agent")["id"], self.agent_id)
        self.assertEqual(services._get_agent_by_id(self.agent_id)["name"], "agent")
        self.assertEqual(services._get_agent_by_name("agent")["id"], self.agent_id)

        with patch("services.secrets.token_urlsafe", return_value="new-agent-token"):
            self.assertEqual(services._issue_agent_token(self.agent_id), "new-agent-token")
        self.assertEqual(services._get_agent_by_token("new-agent-token")["id"], self.agent_id)

        self.assertFalse(services._add_agent_points(self.agent_id, 0))
        self.assertTrue(services._add_agent_points(self.agent_id, 2, "service-test"))
        self.assertEqual(services._get_agent_points(self.agent_id), 2)
        self.assertEqual(services._get_agent_points(999999), 0)

        with patch("services.secrets.token_urlsafe", return_value="session-token"):
            session_token = services._create_user_session(self._create_user())
        self.assertEqual(session_token, "session-token")
        self.assertEqual(services._get_user_by_token("session-token")["email"], "user-service@example.com")
        self.assertIsNone(services._get_user_by_token(""))
        self.assertIsNone(services._get_user_by_token("missing"))

        self.assertGreater(services._reserve_signal_id(), 0)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        self.assertGreater(services._reserve_signal_id(cursor), 0)
        conn.rollback()
        conn.close()

    def _create_user(self) -> int:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES ('user-service@example.com', 'hash', ?)",
            (utc_now_iso_z(),),
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id

    def _position_rows(self) -> list[dict]:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, market, token_id, outcome, side, quantity, entry_price, leader_id FROM positions ORDER BY id")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def test_update_position_long_short_polymarket_and_errors(self) -> None:
        now = utc_now_iso_z()
        services._update_position_from_signal(self.agent_id, "BTC", "crypto", "buy", 2, 100, now, leader_id=42)
        services._update_position_from_signal(self.agent_id, "BTC", "crypto", "buy", 2, 120, now)
        self.assertEqual(self._position_rows()[0]["quantity"], 4.0)
        self.assertEqual(self._position_rows()[0]["leader_id"], 42)
        self.assertAlmostEqual(self._position_rows()[0]["entry_price"], 110.0)

        services._update_position_from_signal(self.agent_id, "BTC", "crypto", "sell", 1, 130, now)
        self.assertEqual(self._position_rows()[0]["quantity"], 3.0)
        services._update_position_from_signal(self.agent_id, "BTC", "crypto", "sell", 3, 130, now)
        self.assertEqual(self._position_rows(), [])

        services._update_position_from_signal(self.agent_id, "ETH", "crypto", "short", 3, 50, now, leader_id=7)
        services._update_position_from_signal(self.agent_id, "ETH", "crypto", "cover", 1, 40, now)
        self.assertEqual(self._position_rows()[0]["quantity"], -2.0)
        services._update_position_from_signal(self.agent_id, "ETH", "crypto", "cover", 2, 40, now)
        self.assertEqual(self._position_rows(), [])

        services._update_position_from_signal(
            self.agent_id,
            "POLY",
            "polymarket",
            "buy",
            1,
            0.42,
            now,
            token_id="token-yes",
            outcome="YES",
        )
        poly = self._position_rows()[0]
        self.assertEqual(poly["token_id"], "token-yes")
        self.assertEqual(poly["outcome"], "YES")

        with self.assertRaisesRegex(ValueError, "Polymarket trades require token_id"):
            conn = database.get_db_connection()
            cursor = conn.cursor()
            try:
                services._update_position_from_signal(self.agent_id, "POLY", "polymarket", "buy", 1, 0.5, now, cursor=cursor)
            finally:
                conn.close()
        with self.assertRaisesRegex(ValueError, "Polymarket does not support"):
            conn = database.get_db_connection()
            cursor = conn.cursor()
            try:
                services._update_position_from_signal(
                    self.agent_id,
                    "POLY",
                    "polymarket",
                    "short",
                    1,
                    0.5,
                    now,
                    cursor=cursor,
                    token_id="token-no",
                )
            finally:
                conn.close()
        error_cases = [
            ("Invalid quantity", ("X", "crypto", "buy", None, 1, now), {}),
            ("Quantity must be positive", ("X", "crypto", "buy", 0, 1, now), {}),
            ("No long position to sell", ("NONE", "crypto", "sell", 1, 1, now), {}),
            ("Insufficient long position quantity", ("POLY", "polymarket", "sell", 2, 0.5, now), {"token_id": "token-yes"}),
            ("No short position to cover", ("NONE", "crypto", "cover", 1, 1, now), {}),
            ("Insufficient short position quantity", ("ETH", "crypto", "short", 1, 1, now), {}),
        ]
        for message, args, kwargs in error_cases:
            conn = database.get_db_connection()
            cursor = conn.cursor()
            try:
                if message == "Insufficient short position quantity":
                    services._update_position_from_signal(self.agent_id, "ERRSHORT", "crypto", "short", 1, 10, now, cursor=cursor)
                    with self.assertRaisesRegex(ValueError, message):
                        services._update_position_from_signal(self.agent_id, "ERRSHORT", "crypto", "cover", 2, 10, now, cursor=cursor)
                else:
                    with self.assertRaisesRegex(ValueError, message):
                        services._update_position_from_signal(self.agent_id, *args, cursor=cursor, **kwargs)
            finally:
                conn.rollback()
                conn.close()

    def test_broadcast_signal_to_followers_counts_active_non_filtered(self) -> None:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        follower_1 = self._create_agent()
        follower_2 = self._create_agent()
        cursor.execute("INSERT INTO subscriptions (follower_id, leader_id, status, created_at) VALUES (?, ?, 'active', ?)", (follower_1, self.agent_id, utc_now_iso_z()))
        cursor.execute("INSERT INTO subscriptions (follower_id, leader_id, status, created_at) VALUES (?, ?, 'paused', ?)", (follower_2, self.agent_id, utc_now_iso_z()))
        conn.commit()
        conn.close()

        import asyncio

        self.assertEqual(asyncio.run(services._broadcast_signal_to_followers(self.agent_id, {"symbol": "BTC"})), 1)


class RouteSharedHelperTests(unittest.TestCase):
    def test_polymarket_format_and_decoration_fallbacks(self) -> None:
        self.assertEqual(routes_shared.format_polymarket_reference(""), "")
        self.assertEqual(routes_shared.format_polymarket_reference("0xabc"), "0xabc")
        self.assertEqual(routes_shared.format_polymarket_reference("123"), "123")
        self.assertEqual(routes_shared.format_polymarket_reference("will-it-rain"), "will it rain")

        non_poly = {"market": "crypto", "symbol": "BTC"}
        self.assertIs(routes_shared.decorate_polymarket_item(non_poly), non_poly)
        item = routes_shared.decorate_polymarket_item({"market": "polymarket", "symbol": "will-it-rain", "outcome": "YES"})
        self.assertEqual(item["display_title"], "will it rain [YES]")

        with patch.dict(sys.modules, {"price_fetcher": Mock(describe_polymarket_contract=Mock(side_effect=RuntimeError("bad")))}):
            item = routes_shared.decorate_polymarket_item({"market": "polymarket", "symbol": "slug"}, fetch_remote=True)
        self.assertEqual(item["market_title"], "slug")

    def test_numeric_mentions_and_market_helpers(self) -> None:
        self.assertEqual(routes_shared.clamp_profit_for_display(None), 0.0)
        self.assertEqual(routes_shared.clamp_profit_for_display("bad"), 0.0)
        self.assertEqual(routes_shared.clamp_profit_for_display(2e12), routes_shared.MAX_ABS_PROFIT_DISPLAY)
        self.assertEqual(routes_shared.clamp_profit_for_display(-2e12), -routes_shared.MAX_ABS_PROFIT_DISPLAY)
        self.assertEqual(set(routes_shared.extract_mentions("@alice @bob @alice @x")), {"alice", "bob"})
        self.assertTrue(routes_shared.is_market_open("crypto"))
        self.assertTrue(routes_shared.is_market_open("unknown"))

    def test_rate_limit_allows_then_rejects_cooldown_window_and_duplicate(self) -> None:
        ctx = routes_shared.RouteContext()
        with patch("routes_shared.time.time", return_value=100.0):
            routes_shared.enforce_content_rate_limit(ctx, 1, "discussion", "hello", "thread")

        with patch("routes_shared.time.time", return_value=101.0):
            with self.assertRaises(routes_shared.HTTPException) as caught:
                routes_shared.enforce_content_rate_limit(ctx, 1, "discussion", "new", "thread")
        self.assertEqual(caught.exception.status_code, 429)

        with patch("routes_shared.time.time", return_value=200.0):
            with self.assertRaises(routes_shared.HTTPException) as caught:
                routes_shared.enforce_content_rate_limit(ctx, 1, "discussion", " hello ", "thread")
        self.assertIn("Duplicate", caught.exception.detail)

        ctx.content_rate_limit_state[(2, "reply")] = {
            "timestamps": [100.0 + idx for idx in range(routes_shared.REPLY_WINDOW_LIMIT)],
            "last_ts": 0.0,
            "fingerprints": {},
        }
        with patch("routes_shared.time.time", return_value=200.0):
            with self.assertRaises(routes_shared.HTTPException) as caught:
                routes_shared.enforce_content_rate_limit(ctx, 2, "reply", "fresh", "thread")
        self.assertIn("rate limit", caught.exception.detail)

    def test_validate_executed_at_paths(self) -> None:
        self.assertTrue(routes_shared.validate_executed_at("2026-01-05T15:00:00Z", "us-stock")[0])
        closed, message = routes_shared.validate_executed_at("2026-01-04T15:00:00Z", "us-stock")
        self.assertFalse(closed)
        self.assertIn("US market is closed", message)
        valid, message = routes_shared.validate_executed_at("2026-01-05T15:00:00", "crypto")
        self.assertFalse(valid)
        self.assertIn("UTC format", message)
        valid, message = routes_shared.validate_executed_at("not-dateZ", "crypto")
        self.assertFalse(valid)
        self.assertIn("Invalid datetime format", message)

    def test_position_price_cache_and_resolve_prices(self) -> None:
        rows = [
            {"symbol": "BTC", "market": "crypto", "token_id": None, "outcome": None, "current_price": 100.0},
            {"symbol": "BTC", "market": "crypto", "token_id": None, "outcome": None, "current_price": 200.0},
        ]
        self.assertEqual(routes_shared.resolve_position_prices(rows, utc_now_iso_z()), {("BTC", "crypto", "", ""): 100.0})

        fake_price_fetcher = Mock(get_price_from_market=Mock(return_value=77.0))
        with (
            patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "true"}),
            patch.dict(sys.modules, {"price_fetcher": fake_price_fetcher}),
        ):
            resolved = routes_shared.resolve_position_prices(
                [{"symbol": "ETH", "market": "crypto", "token_id": None, "outcome": None, "current_price": None}],
                utc_now_iso_z(),
            )
        self.assertEqual(resolved[("ETH", "crypto", "", "")], 77.0)

    def test_remote_polymarket_decoration_and_rate_limit_gate(self) -> None:
        fake_price_fetcher = Mock(
            describe_polymarket_contract=Mock(
                return_value={
                    "token_id": "remote-token",
                    "outcome": "YES",
                    "market_title": "Will BTC rise?",
                    "market_slug": "will-btc-rise",
                    "display_title": "Will BTC rise? [YES]",
                }
            )
        )
        with patch.dict(sys.modules, {"price_fetcher": fake_price_fetcher}):
            item = routes_shared.decorate_polymarket_item({"market": "polymarket", "symbol": "btc"}, fetch_remote=True)

        self.assertEqual(item["token_id"], "remote-token")
        self.assertEqual(item["display_title"], "Will BTC rise? [YES]")

        ctx = routes_shared.RouteContext()
        with patch("routes_shared.datetime") as mock_datetime:
            mock_datetime.now.return_value.timestamp.return_value = 100.0
            self.assertTrue(routes_shared.check_price_api_rate_limit(ctx, 1))
            mock_datetime.now.return_value.timestamp.return_value = 100.5
            self.assertFalse(routes_shared.check_price_api_rate_limit(ctx, 1))

    def test_market_open_validate_now_and_cache_invalidators(self) -> None:
        class FakeDateTime(routes_shared.datetime):
            @classmethod
            def now(cls, tz=None):
                return routes_shared.datetime(2026, 1, 5, 15, 0, tzinfo=tz)

        with patch("routes_shared.datetime", FakeDateTime):
            self.assertTrue(routes_shared.is_us_market_open())
            self.assertTrue(routes_shared.validate_executed_at("now", "us-stock")[0])

        class ClosedDateTime(routes_shared.datetime):
            @classmethod
            def now(cls, tz=None):
                return routes_shared.datetime(2026, 1, 4, 15, 0, tzinfo=tz)

        with patch("routes_shared.datetime", ClosedDateTime):
            self.assertFalse(routes_shared.is_us_market_open())
            valid, message = routes_shared.validate_executed_at("now", "us-stock")
        self.assertFalse(valid)
        self.assertIn("US market is closed", message)

        ctx = routes_shared.RouteContext(
            grouped_signals_cache={("a", "b", 1, 2): (1.0, {})},
            agent_signals_cache={(1, "x", 1): (1.0, {})},
            leaderboard_cache={(1, 2, 3, False): (1.0, {})},
        )
        fake_tasks = Mock(trending_cache={"x": 1})
        with (
            patch.dict(sys.modules, {"tasks": fake_tasks}),
            patch("cache.delete_pattern") as mock_delete_pattern,
            patch("cache.delete") as mock_delete,
        ):
            routes_shared.invalidate_signal_read_caches(ctx, refresh_trending=True)

        self.assertEqual(ctx.grouped_signals_cache, {})
        self.assertEqual(ctx.agent_signals_cache, {})
        self.assertEqual(ctx.leaderboard_cache, {})
        self.assertEqual(fake_tasks.trending_cache, {})
        self.assertTrue(mock_delete_pattern.called)
        mock_delete.assert_called_once_with(routes_shared.TRENDING_CACHE_KEY)

    def test_position_snapshot_push_and_notify_followers(self) -> None:
        class Cursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params=()):
                self.calls.append((sql, params))

            def fetchone(self):
                return {"quantity": 1, "entry_price": 2}

        cursor = Cursor()
        self.assertEqual(routes_shared.get_position_snapshot(cursor, 1, "polymarket", "SYM", "tok")["quantity"], 1)
        self.assertEqual(cursor.calls[-1][1], (1, "polymarket", "tok"))
        self.assertEqual(routes_shared.get_position_snapshot(cursor, 1, "crypto", "BTC", None)["entry_price"], 2)
        self.assertEqual(cursor.calls[-1][1], (1, "BTC", "crypto"))

        ctx = routes_shared.RouteContext()
        sent = []

        async def fake_push(_ctx, follower_id, notify_type, content, payload):
            sent.append((follower_id, notify_type, content, payload))

        class NotifyCursor:
            def execute(self, _sql, _params=()):
                return None

            def fetchall(self):
                return [{"follower_id": 2}, {"follower_id": 1}, {"follower_id": 3}]

        fake_conn = Mock()
        fake_conn.cursor.return_value = NotifyCursor()

        import asyncio

        with patch("routes_shared.get_db_connection", return_value=fake_conn), patch("routes_shared.push_agent_message", side_effect=fake_push):
            asyncio.run(routes_shared.notify_followers_of_post(ctx, 1, "Leader", "strategy", 9, "crypto", title="Plan"))
            asyncio.run(routes_shared.notify_followers_of_post(ctx, 1, "Leader", "discussion", 10, "crypto", symbol="BTC"))

        self.assertEqual(len(sent), 4)
        self.assertEqual(sent[0][1], "strategy_published")
        self.assertIn("Plan", sent[0][2])
        self.assertEqual(sent[-1][1], "discussion_started")
        self.assertIn("BTC", sent[-1][2])


if __name__ == "__main__":
    unittest.main()

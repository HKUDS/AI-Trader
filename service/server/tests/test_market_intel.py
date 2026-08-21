import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import market_intel


def _snapshot_payload(symbol: str = "HD") -> dict:
    return {
        "available": True,
        "symbol": symbol,
        "market": "us-stock",
        "analysis_id": f"{symbol}:snapshot",
        "current_price": 338.91,
        "currency": "USD",
        "signal": "hold",
        "signal_score": 1.5,
        "trend_status": "constructive",
        "support_levels": [330.0],
        "resistance_levels": [350.0],
        "bullish_factors": ["Momentum improved."],
        "risk_factors": ["Resistance is nearby."],
        "summary": "Base daily snapshot summary.",
        "analysis": {
            "symbol": symbol,
            "market": "us-stock",
            "current_price": 338.91,
            "signal": "hold",
            "as_of": "2026-04-17",
        },
        "created_at": "2026-04-20T02:00:00Z",
    }


class MarketIntelLatestPayloadTests(unittest.TestCase):
    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel.ADANOS_API_KEY", "")
    def test_adanos_sentiment_is_disabled_without_api_key(self, _mock_get_json, _mock_set_json) -> None:
        payload = market_intel._get_adanos_stock_sentiment_payload("AAPL")

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "ADANOS_API_KEY is not configured")

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel.ADANOS_API_KEY", "sk_live_test")
    @patch("market_intel.requests.get")
    def test_adanos_sentiment_payload_collects_available_sources(
        self,
        mock_get,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        class Response:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return self._payload

        mock_get.side_effect = [
            Response({
                "found": True,
                "sentiment_score": 0.22,
                "buzz_score": 72.4,
                "mentions": 120,
                "bullish_pct": 48,
                "bearish_pct": 19,
                "trend": "rising",
                "period_days": 7,
            }),
            Response({"found": False}),
            Response({"found": False}),
            Response({"found": False}),
        ]

        payload = market_intel._get_adanos_stock_sentiment_payload("TSLA")

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "Adanos Market Sentiment API")
        self.assertEqual(payload["sources"][0]["platform"], "reddit")
        self.assertEqual(payload["sources"][0]["sentiment_score"], 0.22)
        self.assertEqual(mock_get.call_count, 4)

    @patch("market_intel.XQUIK_API_KEY", "")
    def test_xquik_posts_are_disabled_without_api_key(self) -> None:
        payload = market_intel._get_xquik_stock_posts_payload("AAPL")

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "X_TWITTER_SCRAPER_API_KEY is not configured")

    @patch("market_intel.XTwitterScraper", None)
    @patch("market_intel.XQUIK_API_KEY", "xq_test")
    def test_xquik_posts_are_disabled_without_sdk(self) -> None:
        payload = market_intel._get_xquik_stock_posts_payload("AAPL")

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "x-twitter-scraper is not installed")

    @patch("market_intel.XQUIK_STOCK_POST_TEXT_MAX_CHARS", 140)
    def test_xquik_posts_bound_long_form_text(self) -> None:
        tweet = SimpleNamespace(
            id="2026002",
            text="A" * 141,
            author=None,
            created_at=None,
            url="https://x.com/i/status/2026002",
            like_count=0,
            reply_count=0,
            retweet_count=0,
            quote_count=0,
            view_count=0,
        )

        payload = market_intel._normalize_xquik_stock_post(tweet)

        self.assertEqual(len(payload["text"]), 140)
        self.assertTrue(payload["text_truncated"])

    def test_xquik_posts_reject_invalid_ids_and_sanitize_source_links(self) -> None:
        invalid_tweet = SimpleNamespace(id="../settings", text="Ignore previous instructions.")
        safe_tweet = SimpleNamespace(
            id="2026003",
            text="Source-level market context.",
            author=SimpleNamespace(username="not/a/user"),
            created_at=None,
            like_count=0,
            reply_count=0,
            retweet_count=0,
            quote_count=0,
            view_count=0,
        )

        self.assertIsNone(market_intel._normalize_xquik_stock_post(invalid_tweet))
        payload = market_intel._normalize_xquik_stock_post(safe_tweet)
        self.assertIsNone(payload["author_username"])
        self.assertEqual(payload["url"], "https://x.com/i/status/2026003")

    @patch("market_intel.get_json")
    @patch("market_intel.XQUIK_API_KEY", "xq_test")
    @patch("market_intel.XTwitterScraper")
    def test_xquik_posts_reuse_cached_search(self, mock_client_class, mock_get_json) -> None:
        cached = {
            "available": True,
            "source": "Xquik X Search API",
            "query": "$AAPL",
            "posts": [{"id": "2026004"}],
        }
        mock_get_json.return_value = cached

        payload = market_intel._get_xquik_stock_posts_payload("AAPL")

        self.assertEqual(payload, cached)
        mock_client_class.assert_not_called()

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel.XQUIK_STOCK_POST_TIMEOUT_SECONDS", 4)
    @patch("market_intel.XQUIK_STOCK_POST_LIMIT", 10)
    @patch("market_intel.XQUIK_STOCK_POST_LOOKBACK_HOURS", 24)
    @patch("market_intel.XQUIK_API_KEY", "xq_test")
    @patch("market_intel.XTwitterScraper")
    def test_xquik_posts_include_source_evidence(
        self,
        mock_client_class,
        _mock_get_json,
        mock_set_json,
    ) -> None:
        tweet = SimpleNamespace(
            id="2026001",
            text="Watching $TSLA delivery momentum.",
            author=SimpleNamespace(username="market_observer"),
            created_at="2026-04-20T12:00:00Z",
            url=None,
            like_count=21,
            reply_count=2,
            retweet_count=4,
            quote_count=1,
            view_count=900,
        )
        response = SimpleNamespace(tweets=[tweet], has_next_page=True)
        client = mock_client_class.return_value.__enter__.return_value
        client.x.tweets.search.return_value = response

        with patch("market_intel._utc_now", return_value=datetime(2026, 4, 20, 14, 0, tzinfo=timezone.utc)):
            payload = market_intel._get_xquik_stock_posts_payload("tsla")

        mock_client_class.assert_called_once_with(api_key="xq_test", max_retries=0, timeout=4)
        client.x.tweets.search.assert_called_once_with(
            q="$TSLA",
            limit=10,
            query_type="Latest",
            replies="exclude",
            retweets="exclude",
            safe=True,
            since_time="2026-04-19T14:00:00Z",
        )
        self.assertTrue(payload["available"])
        self.assertEqual(payload["query"], "$TSLA")
        self.assertEqual(payload["fetched_at"], "2026-04-20T14:00:00Z")
        self.assertTrue(payload["has_next_page"])
        self.assertEqual(payload["posts"][0]["author_username"], "market_observer")
        self.assertEqual(payload["posts"][0]["url"], "https://x.com/market_observer/status/2026001")
        self.assertFalse(payload["posts"][0]["text_truncated"])
        self.assertEqual(payload["posts"][0]["view_count"], 900)
        mock_set_json.assert_called_once()

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel.XQUIK_API_KEY", "xq_test")
    @patch("market_intel.XTwitterScraper")
    def test_xquik_posts_hide_provider_error_details(
        self,
        mock_client_class,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_client_class.return_value.__enter__.side_effect = RuntimeError("private provider detail")

        payload = market_intel._get_xquik_stock_posts_payload("AAPL")

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "Xquik search is temporarily unavailable")
        self.assertNotIn("private provider detail", str(payload))

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel._get_xquik_stock_posts_payload")
    @patch("market_intel._get_stock_quote_payload")
    @patch("market_intel._get_adanos_stock_sentiment_payload")
    @patch("market_intel._get_stock_analysis_snapshot_payload")
    def test_latest_payload_prefers_intraday_quote(
        self,
        mock_snapshot_payload,
        mock_adanos_payload,
        mock_quote_payload,
        mock_xquik_payload,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_snapshot_payload.return_value = _snapshot_payload("HD")
        mock_adanos_payload.return_value = {"available": False, "reason": "ADANOS_API_KEY is not configured"}
        mock_xquik_payload.return_value = {
            "available": False,
            "reason": "X_TWITTER_SCRAPER_API_KEY is not configured",
        }
        mock_quote_payload.return_value = {
            "available": True,
            "current_price": 352.11,
            "price_as_of": "2026-04-20T14:35:00Z",
            "price_source": "alpha_vantage_time_series_intraday",
        }

        with patch("market_intel._utc_now", return_value=datetime(2026, 4, 20, 14, 40, tzinfo=timezone.utc)):
            payload = market_intel.get_stock_analysis_latest_payload("HD")

        self.assertEqual(payload["current_price"], 352.11)
        self.assertEqual(payload["price_source"], "alpha_vantage_time_series_intraday")
        self.assertEqual(payload["price_as_of"], "2026-04-20T14:35:00Z")
        self.assertFalse(payload["price_stale"])
        self.assertEqual(payload["price_status"], "realtime")
        self.assertEqual(payload["analysis"]["as_of"], "2026-04-17")
        self.assertFalse(payload["adanos_sentiment"]["available"])
        self.assertFalse(payload["xquik_posts"]["available"])

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel._get_xquik_stock_posts_payload")
    @patch("market_intel._get_stock_quote_payload", return_value=None)
    @patch("market_intel._get_adanos_stock_sentiment_payload")
    @patch("market_intel._get_stock_analysis_snapshot_payload")
    def test_latest_payload_falls_back_to_daily_snapshot_when_quote_missing(
        self,
        mock_snapshot_payload,
        mock_adanos_payload,
        _mock_quote_payload,
        mock_xquik_payload,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_snapshot_payload.return_value = _snapshot_payload("AAPL")
        mock_adanos_payload.return_value = {"available": False, "reason": "ADANOS_API_KEY is not configured"}
        mock_xquik_payload.return_value = {
            "available": False,
            "reason": "X_TWITTER_SCRAPER_API_KEY is not configured",
        }

        with patch("market_intel._utc_now", return_value=datetime(2026, 4, 20, 14, 40, tzinfo=timezone.utc)):
            payload = market_intel.get_stock_analysis_latest_payload("AAPL")

        self.assertEqual(payload["current_price"], 338.91)
        self.assertEqual(payload["price_source"], "alpha_vantage_time_series_daily_adjusted")
        self.assertEqual(payload["price_as_of"], "2026-04-17T20:00:00Z")
        self.assertTrue(payload["price_stale"])
        self.assertEqual(payload["price_status"], "stale")

    @patch("market_intel.set_json")
    @patch("market_intel.get_json", return_value=None)
    @patch("market_intel.get_stock_analysis_latest_payload", side_effect=AssertionError("featured should not call latest"))
    @patch("market_intel._get_stock_analysis_snapshot_payload")
    @patch("market_intel._get_hot_us_stock_symbols", return_value=["AAPL", "MSFT"])
    def test_featured_payload_uses_snapshot_payloads_only(
        self,
        _mock_symbols,
        mock_snapshot_payload,
        _mock_latest_payload,
        _mock_get_json,
        _mock_set_json,
    ) -> None:
        mock_snapshot_payload.side_effect = [
            _snapshot_payload("AAPL"),
            _snapshot_payload("MSFT"),
        ]

        payload = market_intel.get_featured_stock_analysis_payload(limit=2)

        self.assertTrue(payload["available"])
        self.assertEqual([item["symbol"] for item in payload["items"]], ["AAPL", "MSFT"])


class StockPriceMetadataTests(unittest.TestCase):
    """Coverage for _build_stock_price_metadata staleness classification.

    The intent of `price_status="session_close"` is "the latest US session has
    closed; this intraday quote is the most-recent available data until the
    next open". The staleness check must therefore accept Friday's close as
    `session_close` on Saturday/Sunday, and accept the previous trading day's
    close as `session_close` during the next day's pre-market hours.
    """

    def _intraday(self, price_as_of: str) -> dict:
        return {
            "price_as_of": price_as_of,
            "price_source": "alpha_vantage_time_series_intraday",
        }

    def test_metadata_during_market_open_realtime(self) -> None:
        # Tuesday 14:35 ET, quote from 14:34 ET (1 min ago) → realtime.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 21, 18, 35, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-21T18:34:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "realtime")

    def test_metadata_post_close_same_day_session_close(self) -> None:
        # Tuesday 18:00 ET (after 16:00 close), quote from Tuesday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 21, 22, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-21T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_friday_close_on_saturday_is_session_close(self) -> None:
        # Saturday 10:00 ET, quote from Friday 16:00 ET.
        # Friday's close IS the latest available real-time data until Monday's
        # open — current behavior incorrectly classifies it as `stale`.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-24T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_friday_close_on_sunday_is_session_close(self) -> None:
        # Sunday 12:00 ET, quote from Friday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 26, 16, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-24T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_premarket_next_day_is_session_close(self) -> None:
        # Tuesday 08:00 ET (pre-market), quote from Monday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-20T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_premarket_monday_uses_friday_close(self) -> None:
        # Monday 08:00 ET pre-market, quote from previous Friday 16:00 ET.
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-24T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertFalse(meta["price_stale"])
        self.assertEqual(meta["price_status"], "session_close")

    def test_metadata_quote_older_than_last_session_is_stale(self) -> None:
        # Saturday 10:00 ET, quote from Wednesday 16:00 ET (2 sessions stale).
        with patch(
            "market_intel._utc_now",
            return_value=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        ):
            meta = market_intel._build_stock_price_metadata(
                "2026-04-22T20:00:00Z",
                "alpha_vantage_time_series_intraday",
            )
        self.assertTrue(meta["price_stale"])
        self.assertEqual(meta["price_status"], "stale")

    def test_metadata_daily_fallback_remains_stale(self) -> None:
        meta = market_intel._build_stock_price_metadata(
            "2026-04-17T20:00:00Z",
            "alpha_vantage_time_series_daily_adjusted",
        )
        self.assertTrue(meta["price_stale"])
        self.assertEqual(meta["price_status"], "stale")

    def test_metadata_unparseable_timestamp_is_stale(self) -> None:
        meta = market_intel._build_stock_price_metadata(None, None)
        self.assertTrue(meta["price_stale"])
        self.assertEqual(meta["price_status"], "stale")
        self.assertIsNone(meta["price_age_seconds"])


if __name__ == "__main__":
    unittest.main()

"""Tests for the TW news RSS aggregator.

Covers RSS 2.0 + Atom parsing, missing-field tolerance, fetch failures,
dedup-by-link, and the env-driven source override. All HTTP is faked
through `requests.Session` mocks so the tests don't touch the network.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import requests

from news import tw_news


def _mock_resp(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock(return_value=None)
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return resp


_RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>鉅亨網-台股</title>
    <item>
      <title>台積電 ADR 收漲 1.5%</title>
      <link>https://news.cnyes.com/news/id/1</link>
      <description>美股盤後台積電 ADR 收漲。</description>
      <pubDate>Tue, 12 May 2025 03:00:00 +0800</pubDate>
    </item>
    <item>
      <title>聯發科 Q1 法說會重點</title>
      <link>https://news.cnyes.com/news/id/2</link>
      <description>毛利率優於預期。</description>
      <pubDate>Mon, 11 May 2025 14:30:00 +0800</pubDate>
    </item>
    <item>
      <title></title>
      <link>https://news.cnyes.com/news/id/3</link>
      <description>missing title — should be skipped</description>
    </item>
  </channel>
</rss>
"""


_ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>鉅亨網國際股</title>
  <entry>
    <title>美股早盤台積電 ADR 漲幅持續擴大</title>
    <link href="https://news.cnyes.com/news/id/atom-1"/>
    <summary>盤前漲幅 2%。</summary>
    <updated>2025-05-12T10:00:00Z</updated>
  </entry>
</feed>
"""


class ParseRssTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = tw_news.NewsSource(
            slug="test_src", name_zh="測試源", feed_url="https://example.com/feed"
        )

    def test_rss_two_items_parsed(self) -> None:
        items = tw_news.parse_rss(_RSS_SAMPLE, self.source)
        self.assertEqual(len(items), 2)  # Third item has empty title → skipped
        self.assertEqual(items[0].title, "台積電 ADR 收漲 1.5%")
        self.assertEqual(items[0].link, "https://news.cnyes.com/news/id/1")
        self.assertTrue(items[0].published_at.startswith("2025-05-11T19"))  # +0800 → UTC

    def test_atom_entry_parsed(self) -> None:
        items = tw_news.parse_rss(_ATOM_SAMPLE, self.source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].link, "https://news.cnyes.com/news/id/atom-1")
        self.assertEqual(items[0].published_at, "2025-05-12T10:00:00Z")

    def test_missing_link_skipped(self) -> None:
        broken = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>only title</title></item>
</channel></rss>"""
        self.assertEqual(tw_news.parse_rss(broken, self.source), [])

    def test_malformed_xml_returns_empty(self) -> None:
        self.assertEqual(tw_news.parse_rss("<not valid", self.source), [])

    def test_summary_strips_html(self) -> None:
        html_rss = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>t</title>
    <link>https://x/y</link>
    <description>&lt;p&gt;HTML &lt;b&gt;summary&lt;/b&gt;&lt;/p&gt;</description>
  </item>
</channel></rss>"""
        items = tw_news.parse_rss(html_rss, self.source)
        self.assertEqual(items[0].summary, "HTML summary")


class FetchSourceTests(unittest.TestCase):
    def test_successful_fetch_returns_items(self) -> None:
        source = tw_news.NewsSource(slug="s", name_zh="名", feed_url="https://example.com/f")
        session = MagicMock()
        session.get.return_value = _mock_resp(_RSS_SAMPLE)
        items = tw_news.fetch_source(source, session=session)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source_slug, "s")

    def test_http_error_returns_empty(self) -> None:
        source = tw_news.NewsSource(slug="s", name_zh="名", feed_url="https://example.com/f")
        session = MagicMock()
        session.get.return_value = _mock_resp("", status=500)
        self.assertEqual(tw_news.fetch_source(source, session=session), [])

    def test_network_error_returns_empty(self) -> None:
        source = tw_news.NewsSource(slug="s", name_zh="名", feed_url="https://example.com/f")
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("offline")
        self.assertEqual(tw_news.fetch_source(source, session=session), [])


class FetchAllSourcesTests(unittest.TestCase):
    def test_merges_and_dedupes_by_link(self) -> None:
        rss_dup = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>same wire</title><link>https://shared/link</link></item>
</channel></rss>"""
        source_a = tw_news.NewsSource("a", "甲", "https://a/feed")
        source_b = tw_news.NewsSource("b", "乙", "https://b/feed")
        session = MagicMock()
        # Same link served by both feeds.
        session.get.return_value = _mock_resp(rss_dup)
        items = tw_news.fetch_all_sources(
            sources=[source_a, source_b], session=session
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_slug, "a")  # First source wins

    def test_one_failing_source_does_not_break_others(self) -> None:
        source_a = tw_news.NewsSource("a", "甲", "https://a/feed")
        source_b = tw_news.NewsSource("b", "乙", "https://b/feed")
        session = MagicMock()

        def get(url, **_kwargs):
            if url == "https://a/feed":
                raise requests.ConnectionError("a is down")
            return _mock_resp(_ATOM_SAMPLE)

        session.get.side_effect = get
        items = tw_news.fetch_all_sources(
            sources=[source_a, source_b], session=session
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_slug, "b")


class SourceOverrideTests(unittest.TestCase):
    def test_default_sources_include_cnyes(self) -> None:
        slugs = [s.slug for s in tw_news.DEFAULT_SOURCES]
        self.assertIn("cnyes_tw_stock", slugs)

    def test_env_override_replaces_default_list(self) -> None:
        with patch.dict("os.environ", {"TW_NEWS_SOURCES": "custom:https://x/feed"}):
            resolved = tw_news._resolve_sources()
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0].slug, "custom")
            self.assertEqual(resolved[0].feed_url, "https://x/feed")

    def test_invalid_env_override_falls_back_to_default(self) -> None:
        with patch.dict("os.environ", {"TW_NEWS_SOURCES": "garbage_no_colon"}):
            resolved = tw_news._resolve_sources()
            self.assertEqual(resolved, tw_news.DEFAULT_SOURCES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

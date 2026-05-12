"""TW financial news RSS aggregator.

Stdlib-only — `xml.etree.ElementTree` is sufficient for the RSS 2.0 and
Atom shapes the TW press uses, and we avoid pulling in `feedparser` so
the server's `requirements.txt` stays small.

Each source is declared as a `NewsSource` (display name + feed URL +
optional category hint). The aggregator fetches each source with a tight
timeout, parses the RSS payload, and folds items into a uniform
`NewsItem` shape. Failures are non-fatal: a flaky source returns an
empty list, the rest still come through.

This module does NO persistence — it just fetches and normalises. The
caller (route handler / background loop) decides whether to cache the
output in Redis or snapshot it to the DB.
"""

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional

import requests

logger = logging.getLogger(__name__)


# Atom uses the namespaced `{http://www.w3.org/2005/Atom}entry` tag; RSS 2.0
# uses plain `item`. We strip namespaces during parse so the consumer code
# can be naïve about the source format.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class NewsSource:
    """A single RSS / Atom feed we know how to fetch."""

    slug: str
    name_zh: str
    feed_url: str
    category: str = "tw_finance"


@dataclass
class NewsItem:
    """Normalised news item across all TW sources."""

    title: str
    link: str
    source: str
    source_slug: str
    published_at: Optional[str] = None  # ISO 8601 UTC
    summary: str = ""
    category: str = "tw_finance"


# Default source list. URLs are the publicly documented RSS endpoints for
# each outlet. Operators can override the list (e.g. add a niche feed or
# disable one that's gone stale) via TW_NEWS_SOURCES=slug:url,slug:url.
DEFAULT_SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        slug="cnyes_tw_stock",
        name_zh="鉅亨網-台股",
        feed_url="https://news.cnyes.com/rss/cat/tw_stock",
    ),
    NewsSource(
        slug="cnyes_wd_stock",
        name_zh="鉅亨網-國際股",
        feed_url="https://news.cnyes.com/rss/cat/wd_stock",
    ),
    NewsSource(
        slug="ctee_industry",
        name_zh="工商時報-產業",
        feed_url="https://ctee.com.tw/category/news/industry/feed",
    ),
    NewsSource(
        slug="money_udn",
        name_zh="經濟日報",
        feed_url="https://money.udn.com/rssfeed/news/1001/5588/5589?ch=money",
    ),
    NewsSource(
        slug="cna_aopl",
        name_zh="中央社-產經",
        feed_url="https://feeds.feedburner.com/rsscna/finance",
    ),
)


def _resolve_sources() -> tuple[NewsSource, ...]:
    """Return the configured source list, honouring the env override."""
    override = os.environ.get("TW_NEWS_SOURCES", "").strip()
    if not override:
        return DEFAULT_SOURCES
    custom: list[NewsSource] = []
    for chunk in override.split(","):
        if ":" not in chunk:
            continue
        slug, _, url = chunk.partition(":")
        slug = slug.strip()
        url = url.strip()
        if not slug or not url:
            continue
        custom.append(NewsSource(slug=slug, name_zh=slug, feed_url=url))
    return tuple(custom) if custom else DEFAULT_SOURCES


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _coerce_published(raw: Optional[str]) -> Optional[str]:
    """Best-effort RFC-2822 / ISO 8601 → ISO 8601 UTC.

    RSS commonly uses RFC-2822 (`Tue, 12 May 2025 03:00:00 +0800`); Atom uses
    ISO 8601 directly. Anything that doesn't parse is returned as None
    rather than raising — a missing timestamp shouldn't drop the item.
    """
    if not raw:
        return None
    raw = raw.strip()
    # RFC-2822 first (Atom timestamps with explicit offset survive this too).
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    # Fall back to ISO 8601.
    try:
        cleaned = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


_TAG_STRIPPER = re.compile(r"<[^>]+>")


def _clean_summary(text: Optional[str], max_len: int = 280) -> str:
    if not text:
        return ""
    cleaned = _TAG_STRIPPER.sub("", text).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1] + "…"
    return cleaned


def parse_rss(xml_text: str, source: NewsSource) -> list[NewsItem]:
    """Parse an RSS or Atom feed body into NewsItem instances.

    Liberal in what we accept — we look for `<item>` (RSS 2.0) AND
    `<entry>` (Atom), pick the first non-empty title/link, and tolerate
    missing optional fields.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("tw_news[%s] XML parse failed: %s", source.slug, exc)
        return []

    items: list[NewsItem] = []
    # Walk all descendants — works for both RSS (channel/item) and Atom (feed/entry).
    for node in root.iter():
        tag = _strip_ns(node.tag)
        if tag not in ("item", "entry"):
            continue
        title = ""
        link = ""
        summary = ""
        published_raw: Optional[str] = None
        for child in node:
            ctag = _strip_ns(child.tag)
            if ctag == "title" and not title:
                title = (child.text or "").strip()
            elif ctag == "link" and not link:
                # Atom uses href attribute; RSS uses element text.
                link = (child.get("href") or child.text or "").strip()
            elif ctag in ("description", "summary", "content") and not summary:
                summary = _clean_summary(child.text)
            elif ctag in ("pubDate", "published", "updated") and not published_raw:
                published_raw = child.text
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                link=link,
                source=source.name_zh,
                source_slug=source.slug,
                published_at=_coerce_published(published_raw),
                summary=summary,
                category=source.category,
            )
        )
    return items


def fetch_source(
    source: NewsSource,
    *,
    timeout_seconds: float = 6.0,
    session: Optional[requests.Session] = None,
) -> list[NewsItem]:
    """Fetch and parse a single source. Returns [] on any failure."""
    client = session or requests
    headers = {
        "User-Agent": "bw-trader-news/1.0 (+https://github.com/HKUDS/AI-Trader)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
    }
    try:
        resp = client.get(source.feed_url, headers=headers, timeout=timeout_seconds)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("tw_news[%s] fetch failed: %s", source.slug, exc)
        return []
    return parse_rss(resp.text, source)


def fetch_all_sources(
    sources: Optional[Iterable[NewsSource]] = None,
    *,
    timeout_seconds: float = 6.0,
    limit_per_source: int = 10,
    session: Optional[requests.Session] = None,
) -> list[NewsItem]:
    """Fetch every configured source, return a merged + dedup'd item list.

    Deduplication is by `link` URL — two outlets often syndicate the same
    Reuters / 中央社 wire story, and we don't want duplicate cards in the UI.
    The earliest occurrence wins (so the *primary* source's framing
    survives over a syndication).
    """
    resolved = tuple(sources) if sources else _resolve_sources()
    seen_links: set[str] = set()
    merged: list[NewsItem] = []
    for source in resolved:
        items = fetch_source(source, timeout_seconds=timeout_seconds, session=session)
        for item in items[:limit_per_source]:
            if item.link in seen_links:
                continue
            seen_links.add(item.link)
            merged.append(item)
    return merged

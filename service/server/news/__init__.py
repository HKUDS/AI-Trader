"""TW financial news aggregation.

Pulls RSS / public feeds from Taiwan financial press (鉅亨網, 工商時報,
經濟日報, 中央社, 聯合新聞網) and normalises items into a single shape
the market-intel pipeline can render alongside US news.
"""

from .tw_news import (
    DEFAULT_SOURCES,
    NewsItem,
    NewsSource,
    fetch_all_sources,
    fetch_source,
    parse_rss,
)

__all__ = [
    "DEFAULT_SOURCES",
    "NewsItem",
    "NewsSource",
    "fetch_all_sources",
    "fetch_source",
    "parse_rss",
]

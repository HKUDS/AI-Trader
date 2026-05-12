from typing import Optional

from fastapi import FastAPI

from cache import get_json, set_json
from market_intel import (
    get_etf_flows_payload,
    get_featured_stock_analysis_payload,
    get_macro_signals_payload,
    get_market_intel_overview,
    get_market_news_payload,
    get_stock_analysis_history_payload,
    get_stock_analysis_latest_payload,
)
from news import fetch_all_sources
from research import is_backend_available, research
from routes_shared import utc_now_iso_z

try:
    from data_sources import institutional_flows as _institutional_flows
    from data_sources import tw_market_twstock as _tw_twstock
except ImportError:  # data_sources only ships in the real-TW-data PR
    _institutional_flows = None
    _tw_twstock = None


# 12-hour TTL: research synthesis decays slowly relative to price, and the
# upstream skill is expensive (multiple network round trips). Keys are
# namespaced so a cache-flush doesn't take out the price-quote cache.
_RESEARCH_CACHE_PREFIX = "market_intel:research"
_RESEARCH_CACHE_TTL_SECONDS = 12 * 60 * 60

# Short TTL on news: TW press wires get filed multiple times per hour, so a
# 5-minute cache is enough to absorb a UI hot-spot without serving stale
# headlines.
_TW_NEWS_CACHE_PREFIX = "market_intel:tw_news"
_TW_NEWS_CACHE_TTL_SECONDS = 5 * 60


def _build_research_enrichment(symbol: str) -> dict:
    """Best-effort enrich research output with realtime quote + 5-day 三大法人.

    Every leaf is wrapped in try/except so a single source failing never
    breaks the research endpoint. Each section reports its own `status`
    so the UI can show a clear "data unavailable" hint per pane.
    """
    import datetime as _dt

    enrichment: dict = {}

    if _tw_twstock is not None:
        try:
            quote = _tw_twstock.fetch_realtime(symbol)
            enrichment["realtime"] = {"status": "ok", "data": quote}
        except Exception as exc:  # pragma: no cover — defensive
            enrichment["realtime"] = {"status": "error", "error": type(exc).__name__}
    else:
        enrichment["realtime"] = {"status": "unavailable"}

    if _institutional_flows is not None:
        try:
            end = _dt.date.today()
            start = end - _dt.timedelta(days=10)
            rows = _institutional_flows.fetch_institutional_flows(
                symbol, start.isoformat(), end.isoformat()
            )
            if rows is None:
                enrichment["institutional"] = {"status": "error", "rows": []}
            else:
                enrichment["institutional"] = {
                    "status": "ok",
                    "rows": rows[-5:],
                }
        except Exception as exc:  # pragma: no cover — defensive
            enrichment["institutional"] = {
                "status": "error",
                "error": type(exc).__name__,
                "rows": [],
            }
    else:
        enrichment["institutional"] = {"status": "unavailable", "rows": []}

    return enrichment


def register_market_routes(app: FastAPI) -> None:
    @app.get('/health')
    async def health_check():
        return {'status': 'ok', 'timestamp': utc_now_iso_z()}

    @app.get('/api/market-intel/overview')
    async def market_intel_overview():
        return get_market_intel_overview()

    @app.get('/api/market-intel/news')
    async def market_intel_news(category: Optional[str] = None, limit: int = 5):
        safe_limit = max(1, min(limit, 12))
        return get_market_news_payload(category=category, limit=safe_limit)

    @app.get('/api/market-intel/macro-signals')
    async def market_intel_macro_signals():
        return get_macro_signals_payload()

    @app.get('/api/market-intel/etf-flows')
    async def market_intel_etf_flows():
        return get_etf_flows_payload()

    @app.get('/api/market-intel/stocks/featured')
    async def market_intel_featured_stocks(limit: int = 6):
        return get_featured_stock_analysis_payload(limit=max(1, min(limit, 12)))

    @app.get('/api/market-intel/stocks/{symbol}/latest')
    async def market_intel_stock_latest(symbol: str):
        return get_stock_analysis_latest_payload(symbol)

    @app.get('/api/market-intel/stocks/{symbol}/history')
    async def market_intel_stock_history(symbol: str, limit: int = 10):
        return get_stock_analysis_history_payload(symbol, limit=limit)

    @app.get('/api/market-intel/news/tw')
    async def market_intel_tw_news(limit: int = 20, refresh: bool = False):
        """Aggregated TW finance press headlines.

        Pulls 鉅亨網, 工商時報, 經濟日報, 中央社 RSS feeds, dedup'd by URL.
        Cached 5 minutes — long enough to absorb a homepage hot-spot,
        short enough that breaking-news still surfaces quickly.
        """
        safe_limit = max(1, min(limit, 50))
        cache_key = f"{_TW_NEWS_CACHE_PREFIX}:limit={safe_limit}"
        if not refresh:
            cached = get_json(cache_key)
            if cached:
                cached["cache_hit"] = True
                return cached

        items = fetch_all_sources(limit_per_source=10)
        # Sort newest-first; items with no parsed timestamp go to the bottom
        # so a feed with malformed dates doesn't dominate the top of the UI.
        items.sort(
            key=lambda it: it.published_at or "",
            reverse=True,
        )
        payload = {
            "items": [
                {
                    "title": it.title,
                    "link": it.link,
                    "source": it.source,
                    "source_slug": it.source_slug,
                    "published_at": it.published_at,
                    "summary": it.summary,
                    "category": it.category,
                }
                for it in items[:safe_limit]
            ],
            "fetched_at": utc_now_iso_z(),
            "cache_hit": False,
            "total_available": len(items),
        }
        set_json(cache_key, payload, ttl_seconds=_TW_NEWS_CACHE_TTL_SECONDS)
        return payload

    @app.get('/api/market-intel/research/{symbol}')
    async def market_intel_research(symbol: str, deep: bool = False, refresh: bool = False):
        """Last-30-days social/web research for a symbol.

        Cached for 12 hours so repeated UI hits don't re-shell-out to the
        skill. Set `refresh=true` to bypass the cache (used by the scheduler
        when it intentionally wants a fresh pull).

        Returns `status="unavailable"` when the last30days skill isn't
        installed — callers should treat that as "no research available"
        and not as an error.
        """
        normalized = symbol.strip().upper()
        if not normalized:
            return {"status": "error", "error": "symbol is required"}

        cache_key = f"{_RESEARCH_CACHE_PREFIX}:{normalized}:{'deep' if deep else 'std'}"
        if not refresh:
            cached = get_json(cache_key)
            if cached:
                cached["cache_hit"] = True
                return cached

        if not is_backend_available():
            return {
                "status": "unavailable",
                "symbol": normalized,
                "error": "last30days skill not installed",
                "cache_hit": False,
            }

        topic = f"台股 {normalized} 投資人討論 最近 30 天"
        result = research(topic=topic, sources=None, deep=deep)
        payload = result.to_cache_payload()
        payload["symbol"] = normalized
        payload["fetched_at"] = utc_now_iso_z()
        payload["cache_hit"] = False
        payload["enrichment"] = _build_research_enrichment(normalized)
        if result.status == "ok":
            set_json(cache_key, payload, ttl_seconds=_RESEARCH_CACHE_TTL_SECONDS)
        return payload

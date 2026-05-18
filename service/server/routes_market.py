from typing import Optional

from fastapi import FastAPI

from market_intel import (
    get_etf_flows_payload,
    get_featured_stock_analysis_payload,
    get_macro_signals_payload,
    get_market_intel_overview,
    get_market_news_payload,
    get_stock_analysis_history_payload,
    get_stock_analysis_latest_payload,
)
from routes_shared import (
    MARKET_INTEL_CACHE_KEY_PREFIX,
    MARKET_INTEL_CACHE_TTL_SECONDS,
    RouteContext,
    get_short_cached_payload,
    set_short_cached_payload,
    utc_now_iso_z,
)


def register_market_routes(app: FastAPI, ctx: RouteContext) -> None:
    def _cached_market_payload(cache_key: str, builder):
        redis_key = f'{MARKET_INTEL_CACHE_KEY_PREFIX}:{cache_key}'
        cached = get_short_cached_payload(ctx, ctx.market_intel_cache, redis_key, MARKET_INTEL_CACHE_TTL_SECONDS)
        if isinstance(cached, dict):
            return cached
        payload = builder()
        return set_short_cached_payload(
            ctx,
            ctx.market_intel_cache,
            redis_key,
            payload,
            MARKET_INTEL_CACHE_TTL_SECONDS,
        )

    @app.get('/health')
    async def health_check():
        return {'status': 'ok', 'timestamp': utc_now_iso_z()}

    @app.get('/api/market-intel/overview')
    async def market_intel_overview():
        return _cached_market_payload('overview', get_market_intel_overview)

    @app.get('/api/market-intel/news')
    async def market_intel_news(category: Optional[str] = None, limit: int = 5):
        safe_limit = max(1, min(limit, 12))
        category_key = (category or 'all').strip() or 'all'
        return _cached_market_payload(
            f'news:category={category_key}:limit={safe_limit}',
            lambda: get_market_news_payload(category=category, limit=safe_limit),
        )

    @app.get('/api/market-intel/macro-signals')
    async def market_intel_macro_signals():
        return _cached_market_payload('macro_signals', get_macro_signals_payload)

    @app.get('/api/market-intel/etf-flows')
    async def market_intel_etf_flows():
        return _cached_market_payload('etf_flows', get_etf_flows_payload)

    @app.get('/api/market-intel/stocks/featured')
    async def market_intel_featured_stocks(limit: int = 6):
        safe_limit = max(1, min(limit, 12))
        return _cached_market_payload(
            f'stocks_featured:limit={safe_limit}',
            lambda: get_featured_stock_analysis_payload(limit=safe_limit),
        )

    @app.get('/api/market-intel/stocks/{symbol}/latest')
    async def market_intel_stock_latest(symbol: str):
        normalized_symbol = (symbol or '').strip().upper()
        return _cached_market_payload(
            f'stock_latest:symbol={normalized_symbol}',
            lambda: get_stock_analysis_latest_payload(normalized_symbol),
        )

    @app.get('/api/market-intel/stocks/{symbol}/history')
    async def market_intel_stock_history(symbol: str, limit: int = 10):
        normalized_symbol = (symbol or '').strip().upper()
        safe_limit = max(1, min(limit, 100))
        return _cached_market_payload(
            f'stock_history:symbol={normalized_symbol}:limit={safe_limit}',
            lambda: get_stock_analysis_history_payload(normalized_symbol, limit=safe_limit),
        )

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
from routes_shared import utc_now_iso_z


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

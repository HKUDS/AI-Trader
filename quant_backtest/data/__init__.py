"""
Data module for fetching and managing market data.

Data Sources:
=============
1. Sample Data - Instant, no API needed (for testing)
2. Yahoo Finance - FREE, no API key (recommended)
3. Alpha Vantage - FREE API key (fundamentals, technicals)
4. Finnhub - FREE API key (news, sentiment, real-time)

Usage:
======
# Quick start with sample data
from quant_backtest.data import generate_sample_data
data = generate_sample_data(["AAPL", "GOOGL"])

# Real data from Yahoo Finance (no key needed)
from quant_backtest.data import DataFetcher
fetcher = DataFetcher()
data = fetcher.fetch_yahoo(["AAPL", "GOOGL"], "2023-01-01", "2024-01-01")

# Full featured with API keys
from quant_backtest.data.providers import UnifiedDataProvider
provider = UnifiedDataProvider(finnhub_key="YOUR_KEY")
data = provider.get_historical("AAPL", "2023-01-01")
news = provider.get_news("AAPL")
"""

from .data_fetcher import DataFetcher
from .sample_data import generate_sample_data, SAMPLE_SYMBOLS

# Import providers
from .providers import (
    YahooFinanceProvider,
    AlphaVantageProvider,
    FinnhubProvider,
    UnifiedDataProvider,
    get_us_stocks_provider,
    US_STOCKS,
    get_stock_list,
    print_api_summary,
)

__all__ = [
    # Core
    "DataFetcher",
    "generate_sample_data",
    "SAMPLE_SYMBOLS",

    # Providers
    "YahooFinanceProvider",
    "AlphaVantageProvider",
    "FinnhubProvider",
    "UnifiedDataProvider",

    # Utilities
    "get_us_stocks_provider",
    "US_STOCKS",
    "get_stock_list",
    "print_api_summary",
]

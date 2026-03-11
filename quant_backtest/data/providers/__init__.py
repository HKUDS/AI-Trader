"""
Data Providers - Real API Integrations for US Stocks

FREE APIs for US Stocks:
========================

1. Yahoo Finance (RECOMMENDED - No API key needed)
   - Stocks, ETFs, Indices
   - Rate limit: ~2000/hour
   - pip install yfinance

2. Alpha Vantage (Free API key required)
   - Get key: https://www.alphavantage.co/support/#api-key
   - 25 requests/day (free tier)
   - Fundamentals, Technical Indicators

3. Finnhub (Free API key required)
   - Get key: https://finnhub.io/register
   - 60 requests/minute
   - Real-time quotes, News, Sentiment

Usage Examples:
===============

# Simple - Yahoo Finance only (no key needed)
from quant_backtest.data.providers import YahooFinanceProvider
provider = YahooFinanceProvider()
data = provider.get_historical("AAPL", "2023-01-01", "2024-01-01")

# Full featured - with API keys
from quant_backtest.data.providers import UnifiedDataProvider
provider = UnifiedDataProvider(
    alpha_vantage_key="YOUR_KEY",
    finnhub_key="YOUR_KEY",
)
data = provider.get_historical("AAPL", "2023-01-01")
news = provider.get_news("AAPL")
sentiment = provider.get_sentiment("AAPL")

# From environment variables (ALPHA_VANTAGE_KEY, FINNHUB_KEY)
provider = UnifiedDataProvider.from_env()
"""

from .yahoo_provider import YahooFinanceProvider, US_STOCKS, get_stock_list
from .alpha_vantage_provider import AlphaVantageProvider
from .finnhub_provider import FinnhubProvider
from .unified_provider import UnifiedDataProvider, get_us_stocks_provider

__all__ = [
    # Providers
    "YahooFinanceProvider",
    "AlphaVantageProvider",
    "FinnhubProvider",
    "UnifiedDataProvider",

    # Utilities
    "get_us_stocks_provider",
    "get_stock_list",
    "US_STOCKS",
    "print_api_summary",
    "check_providers",
]


# API Information
API_INFO = {
    "yahoo_finance": {
        "name": "Yahoo Finance",
        "free": True,
        "key_required": False,
        "rate_limit": "~2000/hour",
        "data_types": ["stocks", "etfs", "indices"],
        "install": "pip install yfinance",
    },
    "alpha_vantage": {
        "name": "Alpha Vantage",
        "free": True,
        "key_required": True,
        "free_tier": "25 requests/day",
        "data_types": ["stocks", "fundamentals", "technicals", "forex", "crypto"],
        "signup_url": "https://www.alphavantage.co/support/#api-key",
    },
    "finnhub": {
        "name": "Finnhub",
        "free": True,
        "key_required": True,
        "free_tier": "60 calls/minute",
        "data_types": ["stocks", "quotes", "news", "sentiment", "earnings"],
        "signup_url": "https://finnhub.io/register",
    },
}


def get_api_info():
    """Get information about all available APIs."""
    return API_INFO


def print_api_summary():
    """Print summary of available APIs."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    FREE US STOCK DATA APIs                           ║
╠══════════════════════════════════════════════════════════════════════╣
║  Provider        │ Key Required │ Rate Limit    │ Best For           ║
╠══════════════════════════════════════════════════════════════════════╣
║  Yahoo Finance   │ NO           │ ~2000/hour    │ Historical, Quotes ║
║  Alpha Vantage   │ YES (free)   │ 25/day        │ Fundamentals, Tech ║
║  Finnhub         │ YES (free)   │ 60/min        │ News, Sentiment    ║
╚══════════════════════════════════════════════════════════════════════╝

Get Free API Keys:
- Alpha Vantage: https://www.alphavantage.co/support/#api-key
- Finnhub: https://finnhub.io/register
""")


def check_providers() -> dict:
    """
    Check which providers are available.

    Returns:
        Dictionary with provider availability status
    """
    import os

    status = {
        "yahoo_finance": {"available": False, "message": ""},
        "alpha_vantage": {"available": False, "message": ""},
        "finnhub": {"available": False, "message": ""},
    }

    # Check Yahoo Finance
    try:
        import yfinance
        status["yahoo_finance"]["available"] = True
        status["yahoo_finance"]["message"] = "Ready (no key needed)"
    except ImportError:
        status["yahoo_finance"]["message"] = "Install: pip install yfinance"

    # Check Alpha Vantage
    av_key = os.environ.get("ALPHA_VANTAGE_KEY") or os.environ.get("ALPHAVANTAGE_API_KEY")
    if av_key:
        status["alpha_vantage"]["available"] = True
        status["alpha_vantage"]["message"] = "API key found in environment"
    else:
        status["alpha_vantage"]["message"] = "Set ALPHA_VANTAGE_KEY env var"

    # Check Finnhub
    fh_key = os.environ.get("FINNHUB_KEY") or os.environ.get("FINNHUB_API_KEY")
    if fh_key:
        status["finnhub"]["available"] = True
        status["finnhub"]["message"] = "API key found in environment"
    else:
        status["finnhub"]["message"] = "Set FINNHUB_KEY env var"

    return status


def print_provider_status():
    """Print status of all providers."""
    status = check_providers()

    print("\nProvider Status:")
    print("-" * 50)
    for provider, info in status.items():
        icon = "✓" if info["available"] else "✗"
        print(f"  {icon} {provider}: {info['message']}")
    print()

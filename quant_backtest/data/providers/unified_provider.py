"""
Unified Data Provider - One interface for all US Stock APIs

Automatically selects the best available data source based on:
- API keys available
- Rate limits
- Data requirements

Usage:
    provider = UnifiedDataProvider()

    # Automatically uses best available source
    data = provider.get_historical("AAPL", "2023-01-01", "2024-01-01")
    quote = provider.get_quote("AAPL")
    news = provider.get_news("AAPL")
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from dataclasses import dataclass


@dataclass
class APIConfig:
    """API configuration container."""
    yahoo_enabled: bool = True
    alpha_vantage_key: Optional[str] = None
    finnhub_key: Optional[str] = None


class UnifiedDataProvider:
    """
    Unified data provider for US stocks.

    Combines Yahoo Finance, Alpha Vantage, and Finnhub into one interface.
    Automatically selects the best source for each request.

    Usage:
        # Basic - uses Yahoo Finance (no keys needed)
        provider = UnifiedDataProvider()

        # With API keys for more features
        provider = UnifiedDataProvider(
            alpha_vantage_key="YOUR_KEY",
            finnhub_key="YOUR_KEY",
        )

        # Or from environment variables
        # ALPHA_VANTAGE_KEY, FINNHUB_KEY
        provider = UnifiedDataProvider.from_env()
    """

    def __init__(
        self,
        alpha_vantage_key: str = None,
        finnhub_key: str = None,
    ):
        """
        Initialize unified provider.

        Args:
            alpha_vantage_key: Alpha Vantage API key (optional)
            finnhub_key: Finnhub API key (optional)
        """
        self._yahoo = None
        self._alpha_vantage = None
        self._finnhub = None

        # Always initialize Yahoo (no key needed)
        try:
            from .yahoo_provider import YahooFinanceProvider
            self._yahoo = YahooFinanceProvider()
        except ImportError:
            print("Warning: yfinance not installed. Install with: pip install yfinance")

        # Initialize Alpha Vantage if key provided
        if alpha_vantage_key:
            from .alpha_vantage_provider import AlphaVantageProvider
            self._alpha_vantage = AlphaVantageProvider(api_key=alpha_vantage_key)

        # Initialize Finnhub if key provided
        if finnhub_key:
            from .finnhub_provider import FinnhubProvider
            self._finnhub = FinnhubProvider(api_key=finnhub_key)

    @classmethod
    def from_env(cls) -> "UnifiedDataProvider":
        """
        Create provider from environment variables.

        Looks for:
        - ALPHA_VANTAGE_KEY or ALPHAVANTAGE_API_KEY
        - FINNHUB_KEY or FINNHUB_API_KEY
        """
        alpha_key = os.environ.get("ALPHA_VANTAGE_KEY") or os.environ.get("ALPHAVANTAGE_API_KEY")
        finnhub_key = os.environ.get("FINNHUB_KEY") or os.environ.get("FINNHUB_API_KEY")

        return cls(
            alpha_vantage_key=alpha_key,
            finnhub_key=finnhub_key,
        )

    @property
    def available_providers(self) -> List[str]:
        """List available data providers."""
        providers = []
        if self._yahoo:
            providers.append("Yahoo Finance (no key)")
        if self._alpha_vantage:
            providers.append("Alpha Vantage")
        if self._finnhub:
            providers.append("Finnhub")
        return providers

    def get_historical(
        self,
        symbol: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime] = None,
        interval: str = "1d",
        source: str = "auto",
    ) -> List[dict]:
        """
        Get historical OHLCV data.

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            start_date: Start date
            end_date: End date (defaults to today)
            interval: Data interval (1d, 1wk, etc.)
            source: Data source - "auto", "yahoo", "alpha_vantage", "finnhub"

        Returns:
            List of OHLCV dictionaries
        """
        if source == "auto":
            # Prefer Yahoo for historical data (best rate limits)
            if self._yahoo:
                source = "yahoo"
            elif self._finnhub:
                source = "finnhub"
            elif self._alpha_vantage:
                source = "alpha_vantage"

        if source == "yahoo" and self._yahoo:
            return self._yahoo.get_historical(symbol, start_date, end_date, interval)

        elif source == "finnhub" and self._finnhub:
            resolution_map = {"1d": "D", "1wk": "W", "1mo": "M", "1h": "60", "5m": "5"}
            resolution = resolution_map.get(interval, "D")
            if isinstance(start_date, datetime):
                start_date = start_date.strftime("%Y-%m-%d")
            if isinstance(end_date, datetime):
                end_date = end_date.strftime("%Y-%m-%d")
            return self._finnhub.get_candles(symbol, resolution, start_date, end_date)

        elif source == "alpha_vantage" and self._alpha_vantage:
            return self._alpha_vantage.get_daily(symbol)

        raise ValueError(f"No provider available for source: {source}")

    def get_multiple(
        self,
        symbols: List[str],
        start_date: Union[str, datetime],
        end_date: Union[str, datetime] = None,
        interval: str = "1d",
    ) -> Dict[str, List[dict]]:
        """
        Get historical data for multiple symbols.

        Args:
            symbols: List of tickers
            start_date: Start date
            end_date: End date
            interval: Data interval

        Returns:
            Dictionary of symbol -> OHLCV list
        """
        if self._yahoo:
            return self._yahoo.get_multiple(symbols, start_date, end_date, interval)

        # Fallback to fetching one by one
        result = {}
        for symbol in symbols:
            try:
                data = self.get_historical(symbol, start_date, end_date, interval)
                if data:
                    result[symbol] = data
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")

        return result

    def get_intraday(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "1d",
    ) -> List[dict]:
        """
        Get intraday data.

        Args:
            symbol: Stock ticker
            interval: 1m, 5m, 15m, 30m, 1h
            period: 1d, 5d, 1mo

        Returns:
            List of OHLCV with timestamps
        """
        if self._yahoo:
            return self._yahoo.get_intraday(symbol, period, interval)

        elif self._finnhub:
            interval_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60"}
            resolution = interval_map.get(interval, "5")
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")
            return self._finnhub.get_candles(symbol, resolution, start, end)

        raise ValueError("No provider available for intraday data")

    def get_quote(self, symbol: str) -> dict:
        """
        Get real-time quote.

        Args:
            symbol: Stock ticker

        Returns:
            Quote dictionary
        """
        # Prefer Finnhub for real-time (designed for it)
        if self._finnhub:
            return self._finnhub.get_quote(symbol)
        elif self._yahoo:
            return self._yahoo.get_quote(symbol)
        elif self._alpha_vantage:
            return self._alpha_vantage.get_quote(symbol)

        raise ValueError("No provider available for quotes")

    def get_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """Get quotes for multiple symbols."""
        return {symbol: self.get_quote(symbol) for symbol in symbols}

    def get_stock_info(self, symbol: str) -> dict:
        """
        Get detailed stock information.

        Combines data from available sources.
        """
        info = {"symbol": symbol}

        if self._yahoo:
            try:
                stock_info = self._yahoo.get_stock_info(symbol)
                info.update({
                    "name": stock_info.name,
                    "sector": stock_info.sector,
                    "industry": stock_info.industry,
                    "market_cap": stock_info.market_cap,
                    "pe_ratio": stock_info.pe_ratio,
                    "dividend_yield": stock_info.dividend_yield,
                    "fifty_two_week_high": stock_info.fifty_two_week_high,
                    "fifty_two_week_low": stock_info.fifty_two_week_low,
                })
            except:
                pass

        if self._finnhub:
            try:
                profile = self._finnhub.get_company_profile(symbol)
                info.update({
                    "name": profile.get("name") or info.get("name"),
                    "industry": profile.get("industry") or info.get("industry"),
                    "country": profile.get("country"),
                    "exchange": profile.get("exchange"),
                    "website": profile.get("website"),
                    "logo": profile.get("logo"),
                })
            except:
                pass

        if self._alpha_vantage:
            try:
                overview = self._alpha_vantage.get_company_overview(symbol)
                info.update({
                    "description": overview.get("description"),
                    "eps": overview.get("eps"),
                    "book_value": overview.get("book_value"),
                    "profit_margin": overview.get("profit_margin"),
                    "return_on_equity": overview.get("return_on_equity"),
                    "beta": overview.get("beta"),
                })
            except:
                pass

        return info

    def get_news(
        self,
        symbol: str = None,
        days: int = 7,
    ) -> List[dict]:
        """
        Get news articles.

        Args:
            symbol: Stock ticker (None for market news)
            days: Number of days of news

        Returns:
            List of news articles
        """
        if self._finnhub:
            if symbol:
                start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                end = datetime.now().strftime("%Y-%m-%d")
                return self._finnhub.get_company_news(symbol, start, end)
            else:
                return self._finnhub.get_market_news()

        return []

    def get_sentiment(self, symbol: str) -> dict:
        """
        Get social sentiment for a stock.

        Args:
            symbol: Stock ticker

        Returns:
            Sentiment scores
        """
        if self._finnhub:
            return self._finnhub.get_sentiment(symbol)

        return {"symbol": symbol, "sentiment": "N/A (Finnhub key required)"}

    def get_analyst_ratings(self, symbol: str) -> dict:
        """
        Get analyst recommendations and price targets.

        Args:
            symbol: Stock ticker

        Returns:
            Analyst data
        """
        result = {"symbol": symbol}

        if self._finnhub:
            try:
                recs = self._finnhub.get_recommendation_trends(symbol)
                if recs:
                    latest = recs[0]
                    result["recommendations"] = latest
                    result["consensus"] = self._calculate_consensus(latest)

                targets = self._finnhub.get_price_target(symbol)
                result["price_target"] = targets
            except:
                pass

        if self._yahoo:
            try:
                recs = self._yahoo.get_recommendations(symbol)
                if recs and not result.get("recommendations"):
                    result["recommendations_history"] = recs
            except:
                pass

        return result

    def _calculate_consensus(self, rec: dict) -> str:
        """Calculate consensus rating from recommendations."""
        strong_buy = rec.get("strong_buy", 0)
        buy = rec.get("buy", 0)
        hold = rec.get("hold", 0)
        sell = rec.get("sell", 0)
        strong_sell = rec.get("strong_sell", 0)

        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return "N/A"

        score = (strong_buy * 5 + buy * 4 + hold * 3 + sell * 2 + strong_sell * 1) / total

        if score >= 4.5:
            return "Strong Buy"
        elif score >= 3.5:
            return "Buy"
        elif score >= 2.5:
            return "Hold"
        elif score >= 1.5:
            return "Sell"
        else:
            return "Strong Sell"

    def get_financials(self, symbol: str) -> dict:
        """
        Get financial statements.

        Args:
            symbol: Stock ticker

        Returns:
            Financial data
        """
        result = {"symbol": symbol}

        if self._yahoo:
            try:
                financials = self._yahoo.get_financials(symbol)
                result.update(financials)
            except:
                pass

        if self._alpha_vantage:
            try:
                result["income_statement"] = self._alpha_vantage.get_income_statement(symbol)
                result["balance_sheet"] = self._alpha_vantage.get_balance_sheet(symbol)
                result["cash_flow"] = self._alpha_vantage.get_cash_flow(symbol)
            except:
                pass

        return result

    def get_earnings_calendar(
        self,
        symbol: str = None,
        days_ahead: int = 30,
    ) -> List[dict]:
        """
        Get earnings calendar.

        Args:
            symbol: Filter by symbol (optional)
            days_ahead: Number of days to look ahead

        Returns:
            List of upcoming earnings
        """
        if self._finnhub:
            start = datetime.now().strftime("%Y-%m-%d")
            end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            return self._finnhub.get_earnings_calendar(start, end, symbol)

        return []

    def get_technical_indicators(
        self,
        symbol: str,
        indicator: str,
        **kwargs,
    ) -> List[dict]:
        """
        Get technical indicators.

        Args:
            symbol: Stock ticker
            indicator: sma, rsi, macd, bbands
            **kwargs: Indicator parameters

        Returns:
            List of indicator values
        """
        if self._alpha_vantage:
            if indicator.lower() == "sma":
                return self._alpha_vantage.get_sma(symbol, **kwargs)
            elif indicator.lower() == "rsi":
                return self._alpha_vantage.get_rsi(symbol, **kwargs)
            elif indicator.lower() == "macd":
                return self._alpha_vantage.get_macd(symbol, **kwargs)
            elif indicator.lower() == "bbands":
                return self._alpha_vantage.get_bbands(symbol, **kwargs)

        raise ValueError(f"Indicator {indicator} not available (Alpha Vantage key required)")

    def search(self, query: str) -> List[dict]:
        """
        Search for symbols.

        Args:
            query: Search query

        Returns:
            List of matching symbols
        """
        results = []

        if self._finnhub:
            try:
                results.extend(self._finnhub.search_symbols(query))
            except:
                pass

        if self._alpha_vantage and not results:
            try:
                results.extend(self._alpha_vantage.search_symbols(query))
            except:
                pass

        if self._yahoo and not results:
            try:
                results.extend(self._yahoo.search_symbols(query))
            except:
                pass

        return results


# Convenience function
def get_us_stocks_provider(
    alpha_vantage_key: str = None,
    finnhub_key: str = None,
) -> UnifiedDataProvider:
    """
    Get a configured US stocks data provider.

    If no keys provided, will try to load from environment variables.
    """
    if not alpha_vantage_key and not finnhub_key:
        return UnifiedDataProvider.from_env()

    return UnifiedDataProvider(
        alpha_vantage_key=alpha_vantage_key,
        finnhub_key=finnhub_key,
    )

"""
Finnhub Provider - FREE API Key Required

Get your FREE API key: https://finnhub.io/register

Best for: US Stocks, Real-time Quotes, News, Sentiment, Earnings
Rate Limit: 60 API calls/minute (free tier)
Data: OHLCV, Real-time quotes, News, Sentiment, Earnings calendar
"""

import time
import urllib.request
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class FinnhubProvider:
    """
    Finnhub data provider.

    FREE tier: 60 API calls/minute

    Get your free API key at: https://finnhub.io/register

    Usage:
        provider = FinnhubProvider(api_key="YOUR_FREE_KEY")

        # Get candle data
        data = provider.get_candles("AAPL", "D", "2023-01-01", "2024-01-01")

        # Get real-time quote
        quote = provider.get_quote("AAPL")

        # Get news
        news = provider.get_company_news("AAPL")

        # Get sentiment
        sentiment = provider.get_sentiment("AAPL")
    """

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str = None):
        """
        Initialize Finnhub provider.

        Args:
            api_key: Your free API key from finnhub.io
        """
        self.api_key = api_key
        self._last_request_time = 0

    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make API request with rate limiting."""
        if not self.api_key:
            raise ValueError(
                "Finnhub API key required. Get free key at: https://finnhub.io/register"
            )

        # Rate limiting (60 requests per minute = 1 per second)
        current_time = time.time()
        if current_time - self._last_request_time < 1:
            time.sleep(1 - (current_time - self._last_request_time))

        params = params or {}
        params["token"] = self.api_key

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE_URL}/{endpoint}?{query_string}"

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode())

            self._last_request_time = time.time()
            return data

        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise ValueError("Rate limit exceeded. Please wait and try again.")
            raise
        except urllib.error.URLError as e:
            raise ConnectionError(f"Network error: {e}")

    def get_candles(
        self,
        symbol: str,
        resolution: str = "D",
        start_date: str = None,
        end_date: str = None,
    ) -> List[dict]:
        """
        Get OHLCV candle data.

        Args:
            symbol: Stock ticker
            resolution: D (daily), W (weekly), M (monthly),
                       1, 5, 15, 30, 60 (minutes)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of OHLCV dictionaries
        """
        # Default to last year if no dates specified
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Convert dates to Unix timestamps
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

        params = {
            "symbol": symbol,
            "resolution": resolution,
            "from": start_ts,
            "to": end_ts,
        }

        data = self._make_request("stock/candle", params)

        if data.get("s") != "ok":
            return []

        records = []
        timestamps = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        volumes = data.get("v", [])

        for i in range(len(timestamps)):
            dt = datetime.fromtimestamp(timestamps[i])
            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(opens[i], 2),
                "high": round(highs[i], 2),
                "low": round(lows[i], 2),
                "close": round(closes[i], 2),
                "volume": int(volumes[i]),
            })

        return records

    def get_quote(self, symbol: str) -> dict:
        """
        Get real-time quote.

        Args:
            symbol: Stock ticker

        Returns:
            Quote dictionary with current price, change, etc.
        """
        params = {"symbol": symbol}
        data = self._make_request("quote", params)

        return {
            "symbol": symbol,
            "price": data.get("c", 0),
            "change": data.get("d", 0),
            "change_percent": data.get("dp", 0),
            "high": data.get("h", 0),
            "low": data.get("l", 0),
            "open": data.get("o", 0),
            "previous_close": data.get("pc", 0),
            "timestamp": data.get("t", 0),
        }

    def get_company_profile(self, symbol: str) -> dict:
        """
        Get company profile/information.

        Args:
            symbol: Stock ticker

        Returns:
            Company profile dictionary
        """
        params = {"symbol": symbol}
        data = self._make_request("stock/profile2", params)

        return {
            "symbol": data.get("ticker", symbol),
            "name": data.get("name", ""),
            "country": data.get("country", ""),
            "currency": data.get("currency", ""),
            "exchange": data.get("exchange", ""),
            "industry": data.get("finnhubIndustry", ""),
            "ipo_date": data.get("ipo", ""),
            "logo": data.get("logo", ""),
            "market_cap": data.get("marketCapitalization", 0),
            "shares_outstanding": data.get("shareOutstanding", 0),
            "website": data.get("weburl", ""),
        }

    def get_company_news(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
    ) -> List[dict]:
        """
        Get company news.

        Args:
            symbol: Stock ticker
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of news articles
        """
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        params = {
            "symbol": symbol,
            "from": start_date,
            "to": end_date,
        }

        data = self._make_request("company-news", params)

        return [
            {
                "datetime": datetime.fromtimestamp(article.get("datetime", 0)).strftime("%Y-%m-%d %H:%M:%S"),
                "headline": article.get("headline", ""),
                "summary": article.get("summary", ""),
                "source": article.get("source", ""),
                "url": article.get("url", ""),
                "category": article.get("category", ""),
                "related": article.get("related", ""),
            }
            for article in data
        ]

    def get_market_news(self, category: str = "general") -> List[dict]:
        """
        Get market-wide news.

        Args:
            category: general, forex, crypto, merger

        Returns:
            List of news articles
        """
        params = {"category": category}
        data = self._make_request("news", params)

        return [
            {
                "datetime": datetime.fromtimestamp(article.get("datetime", 0)).strftime("%Y-%m-%d %H:%M:%S"),
                "headline": article.get("headline", ""),
                "summary": article.get("summary", ""),
                "source": article.get("source", ""),
                "url": article.get("url", ""),
                "category": article.get("category", ""),
            }
            for article in data
        ]

    def get_sentiment(self, symbol: str) -> dict:
        """
        Get social sentiment for a stock.

        Args:
            symbol: Stock ticker

        Returns:
            Sentiment scores from social media
        """
        params = {"symbol": symbol}
        data = self._make_request("stock/social-sentiment", params)

        reddit = data.get("reddit", [])
        twitter = data.get("twitter", [])

        # Aggregate recent sentiment
        reddit_score = sum(r.get("score", 0) for r in reddit[-10:]) / max(len(reddit[-10:]), 1)
        twitter_score = sum(t.get("score", 0) for t in twitter[-10:]) / max(len(twitter[-10:]), 1)

        return {
            "symbol": symbol,
            "reddit_sentiment": reddit_score,
            "twitter_sentiment": twitter_score,
            "reddit_mentions": sum(r.get("mention", 0) for r in reddit[-10:]),
            "twitter_mentions": sum(t.get("mention", 0) for t in twitter[-10:]),
            "overall_sentiment": (reddit_score + twitter_score) / 2,
        }

    def get_recommendation_trends(self, symbol: str) -> List[dict]:
        """
        Get analyst recommendation trends.

        Args:
            symbol: Stock ticker

        Returns:
            List of monthly recommendation trends
        """
        params = {"symbol": symbol}
        data = self._make_request("stock/recommendation", params)

        return [
            {
                "period": rec.get("period", ""),
                "strong_buy": rec.get("strongBuy", 0),
                "buy": rec.get("buy", 0),
                "hold": rec.get("hold", 0),
                "sell": rec.get("sell", 0),
                "strong_sell": rec.get("strongSell", 0),
            }
            for rec in data
        ]

    def get_price_target(self, symbol: str) -> dict:
        """
        Get analyst price targets.

        Args:
            symbol: Stock ticker

        Returns:
            Price target statistics
        """
        params = {"symbol": symbol}
        data = self._make_request("stock/price-target", params)

        return {
            "symbol": symbol,
            "target_high": data.get("targetHigh", 0),
            "target_low": data.get("targetLow", 0),
            "target_mean": data.get("targetMean", 0),
            "target_median": data.get("targetMedian", 0),
            "last_updated": data.get("lastUpdated", ""),
        }

    def get_earnings_calendar(
        self,
        start_date: str = None,
        end_date: str = None,
        symbol: str = None,
    ) -> List[dict]:
        """
        Get earnings calendar.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            symbol: Optional - filter by symbol

        Returns:
            List of upcoming earnings
        """
        if start_date is None:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if end_date is None:
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        params = {
            "from": start_date,
            "to": end_date,
        }
        if symbol:
            params["symbol"] = symbol

        data = self._make_request("calendar/earnings", params)
        earnings = data.get("earningsCalendar", [])

        return [
            {
                "symbol": e.get("symbol", ""),
                "date": e.get("date", ""),
                "hour": e.get("hour", ""),
                "eps_estimate": e.get("epsEstimate", 0),
                "eps_actual": e.get("epsActual"),
                "revenue_estimate": e.get("revenueEstimate", 0),
                "revenue_actual": e.get("revenueActual"),
                "quarter": e.get("quarter", 0),
                "year": e.get("year", 0),
            }
            for e in earnings
        ]

    def get_basic_financials(self, symbol: str) -> dict:
        """
        Get basic financial metrics.

        Args:
            symbol: Stock ticker

        Returns:
            Dictionary of financial metrics
        """
        params = {
            "symbol": symbol,
            "metric": "all",
        }

        data = self._make_request("stock/metric", params)
        metrics = data.get("metric", {})

        return {
            "symbol": symbol,
            "pe_ratio": metrics.get("peBasicExclExtraTTM", 0),
            "pb_ratio": metrics.get("pbQuarterly", 0),
            "ps_ratio": metrics.get("psAnnual", 0),
            "dividend_yield": metrics.get("dividendYieldIndicatedAnnual", 0),
            "eps_ttm": metrics.get("epsBasicExclExtraItemsTTM", 0),
            "revenue_per_share": metrics.get("revenuePerShareTTM", 0),
            "book_value_per_share": metrics.get("bookValuePerShareQuarterly", 0),
            "beta": metrics.get("beta", 0),
            "fifty_two_week_high": metrics.get("52WeekHigh", 0),
            "fifty_two_week_low": metrics.get("52WeekLow", 0),
            "market_cap": metrics.get("marketCapitalization", 0),
            "roe": metrics.get("roeTTM", 0),
            "roa": metrics.get("roaTTM", 0),
            "current_ratio": metrics.get("currentRatioQuarterly", 0),
            "debt_equity": metrics.get("totalDebt/totalEquityQuarterly", 0),
        }

    def search_symbols(self, query: str) -> List[dict]:
        """
        Search for symbols.

        Args:
            query: Search query

        Returns:
            List of matching symbols
        """
        params = {"q": query}
        data = self._make_request("search", params)

        return [
            {
                "symbol": item.get("symbol", ""),
                "description": item.get("description", ""),
                "type": item.get("type", ""),
            }
            for item in data.get("result", [])
        ]

    def get_peers(self, symbol: str) -> List[str]:
        """
        Get peer companies.

        Args:
            symbol: Stock ticker

        Returns:
            List of peer symbols
        """
        params = {"symbol": symbol}
        return self._make_request("stock/peers", params)

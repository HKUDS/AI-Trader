"""
Alpha Vantage Provider - FREE API Key Required

Get your FREE API key: https://www.alphavantage.co/support/#api-key

Best for: US Stocks, Fundamentals, Technical Indicators, Forex, Crypto
Rate Limit: 25 requests/day (free), 500/day (premium $50/mo)
Data: OHLCV, Fundamentals, 50+ Technical Indicators
"""

import time
import urllib.request
import json
from datetime import datetime
from typing import Dict, List, Optional, Union


class AlphaVantageProvider:
    """
    Alpha Vantage data provider.

    FREE tier: 25 API calls/day (enough for backtesting)

    Get your free API key at: https://www.alphavantage.co/support/#api-key

    Usage:
        provider = AlphaVantageProvider(api_key="YOUR_FREE_KEY")

        # Get daily data
        data = provider.get_daily("AAPL")

        # Get intraday data
        data = provider.get_intraday("AAPL", interval="5min")

        # Get fundamentals
        overview = provider.get_company_overview("AAPL")
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str = None):
        """
        Initialize Alpha Vantage provider.

        Args:
            api_key: Your free API key from alphavantage.co
        """
        self.api_key = api_key or self._get_demo_key()
        self._request_count = 0
        self._last_request_time = 0

    def _get_demo_key(self) -> str:
        """Get demo key (very limited, for testing only)."""
        return "demo"  # Only works for IBM ticker

    def _make_request(self, params: dict) -> dict:
        """Make API request with rate limiting."""
        # Rate limiting (max 5 requests per minute for free tier)
        current_time = time.time()
        if current_time - self._last_request_time < 12:  # 5 per minute = 12 sec gap
            time.sleep(12 - (current_time - self._last_request_time))

        params["apikey"] = self.api_key
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE_URL}?{query_string}"

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode())

            self._last_request_time = time.time()
            self._request_count += 1

            # Check for error messages
            if "Error Message" in data:
                raise ValueError(f"API Error: {data['Error Message']}")
            if "Note" in data:
                print(f"API Note: {data['Note']}")  # Rate limit warning

            return data

        except urllib.error.URLError as e:
            raise ConnectionError(f"Network error: {e}")

    def get_daily(
        self,
        symbol: str,
        outputsize: str = "full",
    ) -> List[dict]:
        """
        Get daily OHLCV data.

        Args:
            symbol: Stock ticker
            outputsize: "compact" (100 days) or "full" (20+ years)

        Returns:
            List of OHLCV dictionaries
        """
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
        }

        data = self._make_request(params)
        time_series = data.get("Time Series (Daily)", {})

        records = []
        for date_str, values in sorted(time_series.items()):
            records.append({
                "date": date_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "adjusted_close": float(values["5. adjusted close"]),
                "volume": int(values["6. volume"]),
                "dividend": float(values["7. dividend amount"]),
                "split_coefficient": float(values["8. split coefficient"]),
            })

        return records

    def get_intraday(
        self,
        symbol: str,
        interval: str = "5min",
        outputsize: str = "full",
    ) -> List[dict]:
        """
        Get intraday data.

        Args:
            symbol: Stock ticker
            interval: 1min, 5min, 15min, 30min, 60min
            outputsize: "compact" (100 points) or "full" (1-2 months)

        Returns:
            List of OHLCV dictionaries
        """
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
        }

        data = self._make_request(params)
        time_series = data.get(f"Time Series ({interval})", {})

        records = []
        for datetime_str, values in sorted(time_series.items()):
            records.append({
                "datetime": datetime_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            })

        return records

    def get_weekly(self, symbol: str) -> List[dict]:
        """Get weekly OHLCV data."""
        params = {
            "function": "TIME_SERIES_WEEKLY_ADJUSTED",
            "symbol": symbol,
        }

        data = self._make_request(params)
        time_series = data.get("Weekly Adjusted Time Series", {})

        records = []
        for date_str, values in sorted(time_series.items()):
            records.append({
                "date": date_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "adjusted_close": float(values["5. adjusted close"]),
                "volume": int(values["6. volume"]),
                "dividend": float(values["7. dividend amount"]),
            })

        return records

    def get_quote(self, symbol: str) -> dict:
        """Get real-time quote."""
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
        }

        data = self._make_request(params)
        quote = data.get("Global Quote", {})

        return {
            "symbol": quote.get("01. symbol", symbol),
            "open": float(quote.get("02. open", 0)),
            "high": float(quote.get("03. high", 0)),
            "low": float(quote.get("04. low", 0)),
            "price": float(quote.get("05. price", 0)),
            "volume": int(quote.get("06. volume", 0)),
            "latest_trading_day": quote.get("07. latest trading day", ""),
            "previous_close": float(quote.get("08. previous close", 0)),
            "change": float(quote.get("09. change", 0)),
            "change_percent": quote.get("10. change percent", "0%").replace("%", ""),
        }

    def get_company_overview(self, symbol: str) -> dict:
        """
        Get company fundamentals.

        Returns comprehensive company data including:
        - Description, Sector, Industry
        - Market Cap, PE Ratio, EPS
        - Dividend data
        - Profitability metrics
        """
        params = {
            "function": "OVERVIEW",
            "symbol": symbol,
        }

        data = self._make_request(params)

        return {
            "symbol": data.get("Symbol", symbol),
            "name": data.get("Name", ""),
            "description": data.get("Description", ""),
            "exchange": data.get("Exchange", ""),
            "sector": data.get("Sector", ""),
            "industry": data.get("Industry", ""),
            "market_cap": int(data.get("MarketCapitalization", 0)),
            "pe_ratio": float(data.get("PERatio", 0) or 0),
            "peg_ratio": float(data.get("PEGRatio", 0) or 0),
            "book_value": float(data.get("BookValue", 0) or 0),
            "dividend_per_share": float(data.get("DividendPerShare", 0) or 0),
            "dividend_yield": float(data.get("DividendYield", 0) or 0),
            "eps": float(data.get("EPS", 0) or 0),
            "revenue_ttm": int(data.get("RevenueTTM", 0) or 0),
            "profit_margin": float(data.get("ProfitMargin", 0) or 0),
            "operating_margin": float(data.get("OperatingMarginTTM", 0) or 0),
            "return_on_equity": float(data.get("ReturnOnEquityTTM", 0) or 0),
            "beta": float(data.get("Beta", 0) or 0),
            "fifty_two_week_high": float(data.get("52WeekHigh", 0) or 0),
            "fifty_two_week_low": float(data.get("52WeekLow", 0) or 0),
            "fifty_day_ma": float(data.get("50DayMovingAverage", 0) or 0),
            "two_hundred_day_ma": float(data.get("200DayMovingAverage", 0) or 0),
            "shares_outstanding": int(data.get("SharesOutstanding", 0) or 0),
        }

    def get_income_statement(self, symbol: str) -> List[dict]:
        """Get annual income statements."""
        params = {
            "function": "INCOME_STATEMENT",
            "symbol": symbol,
        }

        data = self._make_request(params)
        return data.get("annualReports", [])

    def get_balance_sheet(self, symbol: str) -> List[dict]:
        """Get annual balance sheets."""
        params = {
            "function": "BALANCE_SHEET",
            "symbol": symbol,
        }

        data = self._make_request(params)
        return data.get("annualReports", [])

    def get_cash_flow(self, symbol: str) -> List[dict]:
        """Get annual cash flow statements."""
        params = {
            "function": "CASH_FLOW",
            "symbol": symbol,
        }

        data = self._make_request(params)
        return data.get("annualReports", [])

    def get_earnings(self, symbol: str) -> dict:
        """Get earnings data (quarterly and annual)."""
        params = {
            "function": "EARNINGS",
            "symbol": symbol,
        }

        data = self._make_request(params)
        return {
            "annual": data.get("annualEarnings", []),
            "quarterly": data.get("quarterlyEarnings", []),
        }

    # Technical Indicators

    def get_sma(self, symbol: str, interval: str = "daily",
                time_period: int = 20, series_type: str = "close") -> List[dict]:
        """Get Simple Moving Average."""
        params = {
            "function": "SMA",
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": series_type,
        }

        data = self._make_request(params)
        sma_data = data.get("Technical Analysis: SMA", {})

        return [
            {"date": date, "sma": float(values["SMA"])}
            for date, values in sorted(sma_data.items())
        ]

    def get_rsi(self, symbol: str, interval: str = "daily",
                time_period: int = 14, series_type: str = "close") -> List[dict]:
        """Get Relative Strength Index."""
        params = {
            "function": "RSI",
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": series_type,
        }

        data = self._make_request(params)
        rsi_data = data.get("Technical Analysis: RSI", {})

        return [
            {"date": date, "rsi": float(values["RSI"])}
            for date, values in sorted(rsi_data.items())
        ]

    def get_macd(self, symbol: str, interval: str = "daily",
                 series_type: str = "close") -> List[dict]:
        """Get MACD indicator."""
        params = {
            "function": "MACD",
            "symbol": symbol,
            "interval": interval,
            "series_type": series_type,
        }

        data = self._make_request(params)
        macd_data = data.get("Technical Analysis: MACD", {})

        return [
            {
                "date": date,
                "macd": float(values["MACD"]),
                "signal": float(values["MACD_Signal"]),
                "histogram": float(values["MACD_Hist"]),
            }
            for date, values in sorted(macd_data.items())
        ]

    def get_bbands(self, symbol: str, interval: str = "daily",
                   time_period: int = 20, series_type: str = "close") -> List[dict]:
        """Get Bollinger Bands."""
        params = {
            "function": "BBANDS",
            "symbol": symbol,
            "interval": interval,
            "time_period": time_period,
            "series_type": series_type,
        }

        data = self._make_request(params)
        bb_data = data.get("Technical Analysis: BBANDS", {})

        return [
            {
                "date": date,
                "upper": float(values["Real Upper Band"]),
                "middle": float(values["Real Middle Band"]),
                "lower": float(values["Real Lower Band"]),
            }
            for date, values in sorted(bb_data.items())
        ]

    def search_symbols(self, query: str) -> List[dict]:
        """Search for symbols by keywords."""
        params = {
            "function": "SYMBOL_SEARCH",
            "keywords": query,
        }

        data = self._make_request(params)
        matches = data.get("bestMatches", [])

        return [
            {
                "symbol": m.get("1. symbol"),
                "name": m.get("2. name"),
                "type": m.get("3. type"),
                "region": m.get("4. region"),
                "currency": m.get("8. currency"),
            }
            for m in matches
        ]

    @property
    def requests_remaining(self) -> str:
        """Estimate remaining requests (25/day for free tier)."""
        return f"~{max(0, 25 - self._request_count)} requests remaining today"

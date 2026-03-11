"""
Yahoo Finance Provider - FREE, No API Key Required

Best for: US Stocks, ETFs, Indices, Basic Crypto
Rate Limit: ~2000 requests/hour
Data: OHLCV, Dividends, Splits, Financials

This is the RECOMMENDED provider for most use cases.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from dataclasses import dataclass


@dataclass
class StockInfo:
    """Stock information container."""
    symbol: str
    name: str
    sector: str
    industry: str
    market_cap: float
    pe_ratio: float
    dividend_yield: float
    fifty_two_week_high: float
    fifty_two_week_low: float
    avg_volume: float


class YahooFinanceProvider:
    """
    Yahoo Finance data provider.

    FREE - No API key required!

    Usage:
        provider = YahooFinanceProvider()

        # Get historical data
        data = provider.get_historical("AAPL", "2023-01-01", "2024-01-01")

        # Get real-time quote
        quote = provider.get_quote("AAPL")

        # Get multiple stocks
        data = provider.get_multiple(["AAPL", "GOOGL", "MSFT"], "2023-01-01")
    """

    def __init__(self):
        """Initialize Yahoo Finance provider."""
        self._yf = None
        self._check_dependency()

    def _check_dependency(self):
        """Check if yfinance is installed."""
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError:
            raise ImportError(
                "yfinance not installed. Install with: pip install yfinance"
            )

    def get_historical(
        self,
        symbol: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime] = None,
        interval: str = "1d",
    ) -> List[dict]:
        """
        Get historical OHLCV data.

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            start_date: Start date (YYYY-MM-DD or datetime)
            end_date: End date (defaults to today)
            interval: Data interval - 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo

        Returns:
            List of OHLCV dictionaries
        """
        if end_date is None:
            end_date = datetime.now()

        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        ticker = self._yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval)

        if df.empty:
            return []

        records = []
        for idx, row in df.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d") if interval in ["1d", "5d", "1wk", "1mo"]
                        else idx.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "dividends": float(row.get("Dividends", 0)),
                "stock_splits": float(row.get("Stock Splits", 0)),
            })

        return records

    def get_intraday(
        self,
        symbol: str,
        period: str = "1d",
        interval: str = "5m",
    ) -> List[dict]:
        """
        Get intraday data.

        Args:
            symbol: Stock ticker
            period: How far back - 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            interval: Data interval - 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h

        Returns:
            List of OHLCV dictionaries with timestamps
        """
        ticker = self._yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            return []

        records = []
        for idx, row in df.iterrows():
            records.append({
                "datetime": idx.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        return records

    def get_quote(self, symbol: str) -> dict:
        """
        Get real-time quote for a symbol.

        Args:
            symbol: Stock ticker

        Returns:
            Dictionary with current quote data
        """
        ticker = self._yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "change": info.get("regularMarketChange", 0),
            "change_percent": info.get("regularMarketChangePercent", 0),
            "volume": info.get("regularMarketVolume", 0),
            "avg_volume": info.get("averageVolume", 0),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
            "open": info.get("regularMarketOpen", 0),
            "high": info.get("regularMarketDayHigh", 0),
            "low": info.get("regularMarketDayLow", 0),
            "previous_close": info.get("regularMarketPreviousClose", 0),
        }

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
            end_date: End date (defaults to today)
            interval: Data interval

        Returns:
            Dictionary of symbol -> OHLCV list
        """
        result = {}

        for symbol in symbols:
            try:
                data = self.get_historical(symbol, start_date, end_date, interval)
                if data:
                    result[symbol] = data
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")

            # Small delay to avoid rate limiting
            time.sleep(0.1)

        return result

    def get_stock_info(self, symbol: str) -> StockInfo:
        """
        Get detailed stock information.

        Args:
            symbol: Stock ticker

        Returns:
            StockInfo object
        """
        ticker = self._yf.Ticker(symbol)
        info = ticker.info

        return StockInfo(
            symbol=symbol,
            name=info.get("longName", info.get("shortName", symbol)),
            sector=info.get("sector", "N/A"),
            industry=info.get("industry", "N/A"),
            market_cap=info.get("marketCap", 0),
            pe_ratio=info.get("trailingPE", 0),
            dividend_yield=info.get("dividendYield", 0) or 0,
            fifty_two_week_high=info.get("fiftyTwoWeekHigh", 0),
            fifty_two_week_low=info.get("fiftyTwoWeekLow", 0),
            avg_volume=info.get("averageVolume", 0),
        )

    def get_financials(self, symbol: str) -> dict:
        """
        Get financial statements.

        Args:
            symbol: Stock ticker

        Returns:
            Dictionary with income statement, balance sheet, cash flow
        """
        ticker = self._yf.Ticker(symbol)

        result = {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
        }

        # Income Statement
        try:
            income = ticker.financials
            if income is not None and not income.empty:
                result["income_statement"] = income.to_dict()
        except:
            pass

        # Balance Sheet
        try:
            balance = ticker.balance_sheet
            if balance is not None and not balance.empty:
                result["balance_sheet"] = balance.to_dict()
        except:
            pass

        # Cash Flow
        try:
            cash = ticker.cashflow
            if cash is not None and not cash.empty:
                result["cash_flow"] = cash.to_dict()
        except:
            pass

        return result

    def get_recommendations(self, symbol: str) -> List[dict]:
        """
        Get analyst recommendations.

        Args:
            symbol: Stock ticker

        Returns:
            List of recommendation dictionaries
        """
        ticker = self._yf.Ticker(symbol)

        try:
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                return recs.tail(10).to_dict("records")
        except:
            pass

        return []

    def search_symbols(self, query: str) -> List[dict]:
        """
        Search for symbols by name or ticker.

        Args:
            query: Search query

        Returns:
            List of matching symbols
        """
        # yfinance doesn't have native search, use Ticker lookup
        try:
            ticker = self._yf.Ticker(query.upper())
            info = ticker.info
            if info.get("symbol"):
                return [{
                    "symbol": info.get("symbol"),
                    "name": info.get("longName", info.get("shortName", "")),
                    "type": info.get("quoteType", ""),
                    "exchange": info.get("exchange", ""),
                }]
        except:
            pass

        return []


# Popular US Stock Lists
US_STOCKS = {
    "mega_cap": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B"],
    "tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC", "CRM"],
    "finance": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V"],
    "healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY", "LLY"],
    "consumer": ["WMT", "HD", "PG", "KO", "PEP", "COST", "MCD", "NKE", "SBUX", "TGT"],
    "industrial": ["CAT", "BA", "HON", "UPS", "RTX", "GE", "MMM", "DE", "LMT", "UNP"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "KMI"],
    "sp500_top20": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JNJ",
        "V", "XOM", "JPM", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PFE"
    ],
    "nasdaq100_top20": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "COST", "PEP",
        "ADBE", "CSCO", "NFLX", "CMCSA", "AMD", "INTC", "QCOM", "TXN", "INTU", "AMGN"
    ],
    "etfs": ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO", "BND", "GLD"],
}


def get_stock_list(category: str) -> List[str]:
    """Get a predefined list of stocks by category."""
    return US_STOCKS.get(category, [])

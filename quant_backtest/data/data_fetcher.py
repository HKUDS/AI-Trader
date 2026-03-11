"""
Data fetching module - FREE data sources only.

Supports:
- Yahoo Finance (yfinance) - Free, no API key needed
- Local JSON/CSV files
- Existing AI-Trader data
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from pathlib import Path
import json


class DataFetcher:
    """
    Fetch market data from free sources.

    Usage:
        ```python
        fetcher = DataFetcher()

        # Fetch from Yahoo Finance (FREE)
        data = fetcher.fetch_yahoo(["AAPL", "GOOGL"], "2023-01-01", "2024-01-01")

        # Load from local files
        data = fetcher.load_json("path/to/data.json")
        data = fetcher.load_csv("path/to/data.csv")

        # Load existing AI-Trader data
        data = fetcher.load_ai_trader_data()
        ```
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the data fetcher.

        Args:
            cache_dir: Directory for caching fetched data
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_yahoo(
        self,
        symbols: Union[str, List[str]],
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        interval: str = "1d",
    ) -> Dict[str, List[dict]]:
        """
        Fetch data from Yahoo Finance (FREE, no API key needed).

        Args:
            symbols: Single symbol or list of symbols
            start_date: Start date (YYYY-MM-DD or datetime)
            end_date: End date (YYYY-MM-DD or datetime)
            interval: Data interval (1d, 1wk, 1mo)

        Returns:
            Dictionary of symbol -> list of OHLCV dictionaries
        """
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError(
                "yfinance not installed. Install with: pip install yfinance"
            )

        if isinstance(symbols, str):
            symbols = [symbols]

        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        data = {}

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start_date, end=end_date, interval=interval)

                if df.empty:
                    print(f"Warning: No data for {symbol}")
                    continue

                records = []
                for idx, row in df.iterrows():
                    records.append({
                        "date": idx.strftime("%Y-%m-%d"),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row["Volume"]),
                    })

                data[symbol] = records

            except Exception as e:
                print(f"Error fetching {symbol}: {e}")

        return data

    def load_json(self, filepath: str) -> Dict[str, List[dict]]:
        """
        Load data from JSON file.

        Expected format:
        {
            "AAPL": [
                {"date": "2024-01-01", "open": 150, "high": 152, ...},
                ...
            ],
            ...
        }

        Or for single symbol file:
        [
            {"date": "2024-01-01", "open": 150, ...},
            ...
        ]
        """
        with open(filepath, "r") as f:
            raw_data = json.load(f)

        # Handle single symbol format
        if isinstance(raw_data, list):
            symbol = Path(filepath).stem.replace("daily_prices_", "")
            return {symbol: raw_data}

        return raw_data

    def load_csv(
        self,
        filepath: str,
        symbol: Optional[str] = None,
        date_col: str = "date",
    ) -> Dict[str, List[dict]]:
        """
        Load data from CSV file.

        Args:
            filepath: Path to CSV file
            symbol: Symbol name (defaults to filename)
            date_col: Name of date column
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas not installed. Install with: pip install pandas"
            )

        if symbol is None:
            symbol = Path(filepath).stem

        df = pd.read_csv(filepath)

        # Normalize column names
        df.columns = df.columns.str.lower()

        records = []
        for _, row in df.iterrows():
            records.append({
                "date": str(row.get(date_col, row.get("date", ""))),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
            })

        return {symbol: records}

    def load_ai_trader_data(
        self,
        data_dir: Optional[str] = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, List[dict]]:
        """
        Load existing AI-Trader price data.

        Args:
            data_dir: Data directory (defaults to AI-Trader/data)
            symbols: Specific symbols to load (None = all)
        """
        if data_dir is None:
            # Find AI-Trader data directory
            possible_paths = [
                Path(__file__).parent.parent.parent / "data",
                Path.cwd() / "data",
                Path.home() / "AI-Trader" / "data",
            ]

            for path in possible_paths:
                if path.exists():
                    data_dir = path
                    break

        if data_dir is None:
            raise ValueError("Could not find AI-Trader data directory")

        data_path = Path(data_dir)
        data = {}

        # Load daily price files
        for json_file in data_path.glob("daily_prices_*.json"):
            symbol = json_file.stem.replace("daily_prices_", "")

            if symbols and symbol not in symbols:
                continue

            try:
                with open(json_file, "r") as f:
                    records = json.load(f)
                    data[symbol] = records
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        return data

    def load_merged_data(
        self,
        filepath: Optional[str] = None,
    ) -> Dict[str, List[dict]]:
        """
        Load merged JSONL data (AI-Trader format).

        Args:
            filepath: Path to merged.jsonl file
        """
        if filepath is None:
            filepath = Path(__file__).parent.parent.parent / "data" / "merged.jsonl"

        data = {}

        with open(filepath, "r") as f:
            for line in f:
                record = json.loads(line.strip())
                symbol = record.get("symbol", "UNKNOWN")

                if symbol not in data:
                    data[symbol] = []

                data[symbol].append({
                    "date": record.get("date", ""),
                    "open": float(record.get("open", 0)),
                    "high": float(record.get("high", 0)),
                    "low": float(record.get("low", 0)),
                    "close": float(record.get("close", 0)),
                    "volume": float(record.get("volume", 0)),
                })

        return data

    def get_available_symbols(self, data_dir: Optional[str] = None) -> List[str]:
        """Get list of symbols available in AI-Trader data."""
        try:
            data = self.load_ai_trader_data(data_dir)
            return sorted(list(data.keys()))
        except Exception:
            return []


# Popular stock symbols for quick reference
POPULAR_SYMBOLS = {
    "tech": ["AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "TSLA"],
    "finance": ["JPM", "BAC", "GS", "MS", "C", "WFC"],
    "healthcare": ["JNJ", "PFE", "UNH", "MRK", "ABBV"],
    "consumer": ["WMT", "KO", "PEP", "PG", "HD"],
    "energy": ["XOM", "CVX", "COP", "SLB"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "etf": ["SPY", "QQQ", "IWM", "DIA", "VTI"],
}


def get_symbols_by_sector(sector: str) -> List[str]:
    """Get symbols for a specific sector."""
    return POPULAR_SYMBOLS.get(sector.lower(), [])

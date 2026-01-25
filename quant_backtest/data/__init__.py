"""
Data module for fetching and managing market data.

All data sources are FREE with no API keys required:
- Yahoo Finance (via yfinance)
- Local JSON/CSV files
- Sample data generators
"""

from .data_fetcher import DataFetcher
from .sample_data import generate_sample_data, SAMPLE_SYMBOLS

__all__ = [
    "DataFetcher",
    "generate_sample_data",
    "SAMPLE_SYMBOLS",
]

"""
Price data caching module for improved performance.

This module provides an in-memory cache for price data to avoid
repeated scanning of the merged.jsonl file, which is O(n) per query.
"""

import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from tools.logging_config import get_logger_for_module

logger = get_logger_for_module(__name__)


class PriceDataCache:
    """
    In-memory cache for price data from merged.jsonl.

    This cache loads all price data once and provides O(1) lookups
    instead of O(n) file scanning for each query.
    """

    def __init__(self, merged_path: Optional[Path] = None):
        """
        Initialize the price cache.

        Args:
            merged_path: Optional path to merged.jsonl file.
                        If None, uses default location.
        """
        self._cache: Dict[str, Dict[str, Dict[str, any]]] = {}
        self._loaded = False
        self._load_timestamp: Optional[datetime] = None

        if merged_path is None:
            base_dir = Path(__file__).resolve().parents[1]
            self.merged_path = base_dir / "data" / "merged.jsonl"
        else:
            self.merged_path = Path(merged_path)

    def load(self, force_reload: bool = False) -> None:
        """
        Load price data from merged.jsonl into memory.

        Args:
            force_reload: If True, reload even if already loaded
        """
        if self._loaded and not force_reload:
            logger.debug("Price cache already loaded, skipping")
            return

        if not self.merged_path.exists():
            logger.warning(f"Price data file not found: {self.merged_path}")
            return

        logger.info(f"Loading price data from {self.merged_path}")
        start_time = datetime.now()

        self._cache.clear()
        line_count = 0

        try:
            with self.merged_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        doc = json.loads(line)
                        meta = doc.get("Meta Data", {})
                        symbol = meta.get("2. Symbol")

                        if not symbol:
                            continue

                        series = doc.get("Time Series (Daily)", {})
                        if not isinstance(series, dict):
                            continue

                        # Store in cache: {symbol: {date: ohlcv_data}}
                        self._cache[symbol] = series
                        line_count += 1

                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse line: {e}")
                        continue

            self._loaded = True
            self._load_timestamp = datetime.now()
            load_duration = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"Loaded {line_count} symbols in {load_duration:.2f}s. "
                f"Cache size: {len(self._cache)} symbols"
            )

        except Exception as e:
            logger.error(f"Failed to load price data: {e}")
            raise

    def get_price(
        self,
        symbol: str,
        date: str,
        price_field: str = "1. buy price"
    ) -> Optional[float]:
        """
        Get price for a specific symbol and date.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            date: Date string in YYYY-MM-DD format
            price_field: Which price field to return (default: open/buy price)

        Returns:
            Price as float, or None if not found
        """
        if not self._loaded:
            self.load()

        symbol_data = self._cache.get(symbol)
        if not symbol_data:
            return None

        day_data = symbol_data.get(date)
        if not day_data:
            return None

        price_str = day_data.get(price_field)
        if price_str is None:
            return None

        try:
            return float(price_str)
        except (ValueError, TypeError):
            return None

    def get_ohlcv(
        self,
        symbol: str,
        date: str
    ) -> Optional[Dict[str, Optional[float]]]:
        """
        Get full OHLCV data for a symbol and date.

        Args:
            symbol: Stock symbol
            date: Date string in YYYY-MM-DD format

        Returns:
            Dict with open, high, low, close, volume, or None
        """
        if not self._loaded:
            self.load()

        symbol_data = self._cache.get(symbol)
        if not symbol_data:
            return None

        day_data = symbol_data.get(date)
        if not day_data:
            return None

        try:
            return {
                "open": float(day_data.get("1. buy price")) if day_data.get("1. buy price") else None,
                "high": float(day_data.get("2. high")) if day_data.get("2. high") else None,
                "low": float(day_data.get("3. low")) if day_data.get("3. low") else None,
                "close": float(day_data.get("4. sell price")) if day_data.get("4. sell price") else None,
                "volume": int(day_data.get("5. volume")) if day_data.get("5. volume") else None,
            }
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse OHLCV for {symbol} on {date}: {e}")
            return None

    def get_symbols(self) -> list[str]:
        """
        Get list of all symbols in the cache.

        Returns:
            List of symbol strings
        """
        if not self._loaded:
            self.load()

        return list(self._cache.keys())

    def get_dates_for_symbol(self, symbol: str) -> list[str]:
        """
        Get all available dates for a specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            List of date strings in YYYY-MM-DD format
        """
        if not self._loaded:
            self.load()

        symbol_data = self._cache.get(symbol)
        if not symbol_data:
            return []

        return sorted(symbol_data.keys(), reverse=True)

    def is_loaded(self) -> bool:
        """Check if cache has been loaded."""
        return self._loaded

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._loaded = False
        self._load_timestamp = None
        logger.info("Price cache cleared")

    def get_stats(self) -> Dict[str, any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        if not self._loaded:
            return {"loaded": False}

        total_entries = sum(len(dates) for dates in self._cache.values())

        return {
            "loaded": self._loaded,
            "load_timestamp": self._load_timestamp.isoformat() if self._load_timestamp else None,
            "symbols_count": len(self._cache),
            "total_price_entries": total_entries,
            "avg_dates_per_symbol": total_entries / len(self._cache) if self._cache else 0
        }


# Global cache instance (singleton pattern)
_global_cache: Optional[PriceDataCache] = None


def get_global_cache() -> PriceDataCache:
    """
    Get the global price cache instance.

    Returns:
        Global PriceDataCache instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = PriceDataCache()
        _global_cache.load()

    return _global_cache


def clear_global_cache() -> None:
    """Clear the global cache instance."""
    global _global_cache

    if _global_cache is not None:
        _global_cache.clear()
        _global_cache = None

from pathlib import Path
import json
from datetime import datetime
from typing import Dict, Any
from fastmcp import FastMCP
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.general_tools import get_config_value

mcp = FastMCP("LocalPrices")


def _workspace_data_path(filename: str) -> Path:
    base_dir = Path(__file__).resolve().parents[1]
    return base_dir / "data" / filename


def _validate_date(date_str: str) -> None:
    """Validate date format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must be in YYYY-MM-DD format") from exc


def _validate_no_look_ahead(requested_date: str) -> None:
    """
    Validate that requested date is not in the future compared to TODAY_DATE.
    This prevents look-ahead bias in backtesting.

    Args:
        requested_date: Date string in YYYY-MM-DD format to validate

    Raises:
        ValueError: If requested_date is after TODAY_DATE
    """
    today_date = get_config_value("TODAY_DATE")
    if today_date is None:
        # If TODAY_DATE is not set, skip validation (for testing purposes)
        return

    try:
        requested_dt = datetime.strptime(requested_date, "%Y-%m-%d")
        today_dt = datetime.strptime(today_date, "%Y-%m-%d")

        if requested_dt > today_dt:
            raise ValueError(
                f"Look-ahead bias detected: Cannot access data from {requested_date} "
                f"when current trading date is {today_date}. "
                f"Requested date is {(requested_dt - today_dt).days} days in the future."
            )
    except ValueError as e:
        if "Look-ahead bias" in str(e):
            raise
        # If date parsing fails, let _validate_date handle it
        pass


@mcp.tool()
def get_price_local(symbol: str, date: str) -> Dict[str, Any]:
    """Read OHLCV data for specified stock and date. Get historical information for specified stock.

    Args:
        symbol: Stock symbol, e.g. 'IBM' or '600243.SHH'.
        date: Date in 'YYYY-MM-DD' format.

    Returns:
        Dictionary containing symbol, date and ohlcv data.
    """
    filename = "merged.jsonl"
    try:
        _validate_date(date)
        _validate_no_look_ahead(date)
    except ValueError as e:
        return {"error": str(e), "symbol": symbol, "date": date}

    data_path = _workspace_data_path(filename)
    if not data_path.exists():
        return {"error": f"Data file not found: {data_path}", "symbol": symbol, "date": date}

    with data_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            meta = doc.get("Meta Data", {})
            if meta.get("2. Symbol") != symbol:
                continue
            series = doc.get("Time Series (Daily)", {})
            day = series.get(date)
            if day is None:
                sample_dates = sorted(series.keys(), reverse=True)[:5]
                return {
                    "error": f"Data not found for date {date}. Please verify the date exists in data. Sample available dates: {sample_dates}",
                    "symbol": symbol,
                    "date": date
                }
            return {
                "symbol": symbol,
                "date": date,
                "ohlcv": {
                    "open": day.get("1. buy price"),
                    "high": day.get("2. high"),
                    "low": day.get("3. low"), 
                    "close": day.get("4. sell price"),
                    "volume": day.get("5. volume"),
                },
            }

    return {"error": f"No records found for stock {symbol} in local data", "symbol": symbol, "date": date}



def get_price_local_function(symbol: str, date: str, filename: str = "merged.jsonl") -> Dict[str, Any]:
    """Read OHLCV data for specified stock and date from local JSONL data.

    Args:
        symbol: Stock symbol, e.g. 'IBM' or '600243.SHH'.
        date: Date in 'YYYY-MM-DD' format.
        filename: Data filename, defaults to 'merged.jsonl' (located in data/ under project root).

    Returns:
        Dictionary containing symbol, date and ohlcv data.
    """
    try:
        _validate_date(date)
        _validate_no_look_ahead(date)
    except ValueError as e:
        return {"error": str(e), "symbol": symbol, "date": date}

    data_path = _workspace_data_path(filename)
    if not data_path.exists():
        return {"error": f"Data file not found: {data_path}", "symbol": symbol, "date": date}

    with data_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            meta = doc.get("Meta Data", {})
            if meta.get("2. Symbol") != symbol:
                continue
            series = doc.get("Time Series (Daily)", {})
            day = series.get(date)
            if day is None:
                sample_dates = sorted(series.keys(), reverse=True)[:5]
                return {
                    "error": f"Data not found for date {date}. Please verify the date exists in data. Sample available dates: {sample_dates}",
                    "symbol": symbol,
                    "date": date
                }
            return {
                "symbol": symbol,
                "date": date,
                "ohlcv": {
                    "buy price": day.get("1. buy price"),
                    "high": day.get("2. high"),
                    "low": day.get("3. low"),
                    "sell price": day.get("4. sell price"),
                    "volume": day.get("5. volume"),
                },
            }

    return {"error": f"No records found for stock {symbol} in local data", "symbol": symbol, "date": date}

if __name__ == "__main__":
    # print("a test case")
    # print(get_price_local_function("AAPL", "2025-10-16"))
    port = int(os.getenv("GETPRICE_HTTP_PORT", "8003"))
    mcp.run(transport="streamable-http", port=port)


import os
import sys
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from typing import Dict, List, Optional, Any
import fcntl
from pathlib import Path
# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import json

from tools.general_tools import get_config_value

mcp = FastMCP("TradeLimitTools")




@mcp.tool()
def place_limit_buy_order(symbol: str, amount: int, limit_price: float) -> Dict[str, Any]:
    """
    Place limit buy order function

    This function records a limit buy order for later settlement, including the following steps:
    1. Get signature and today's date
    2. Validate order parameters (amount, limit_price, lot size for CN market)
    3. Generate unique timestamp for order
    4. Record order to pending orders file for later settlement
    5. Return order confirmation without market data leakage

    Args:
        symbol: Stock symbol, such as "AAPL", "MSFT", etc.
        amount: Buy quantity, must be a positive integer, indicating how many shares to buy
                For Chinese A-shares (symbols ending with .SH or .SZ), must be multiples of 100
        limit_price: Maximum price you're willing to pay per share

    Returns:
        Dict[str, Any]:
          - Success: Returns {"status": "OrderPlaced", "message": "..."} dictionary
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = place_limit_buy_order("AAPL", 10, 150.0)
        >>> print(result)  # {"status": "OrderPlaced", "message": "Limit order for 10 AAPL @ 150.0 has been placed and is pending settlement."}
        >>> result = place_limit_buy_order("600519.SH", 100, 1500.0)  # Chinese A-shares must be multiples of 100
        >>> print(result)  # {"status": "OrderPlaced", "message": "Limit order for 100 600519.SH @ 1500.0 has been placed and is pending settlement."}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    # Auto-detect market type based on symbol format
    if symbol.endswith((".SH", ".SZ")):
        market = "cn"
    else:
        market = "us"

    # Amount validation for stocks
    try:
        amount = int(amount)  # Convert to int for stocks
    except ValueError:
        return {
            "error": f"Invalid amount format. Amount must be an integer for stock trading. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to buy {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # Limit price validation
    try:
        limit_price = float(limit_price)
    except ValueError:
        return {
            "error": f"Invalid limit_price format. Must be a number. You provided: {limit_price}",
            "symbol": symbol,
            "date": today_date,
        }

    if limit_price <= 0:
        return {
            "error": f"Limit price must be positive. You tried to set limit price {limit_price}.",
            "symbol": symbol,
            "limit_price": limit_price,
            "date": today_date,
        }

    # 🇨🇳 Chinese A-shares trading rule: Must trade in lots of 100 shares (一手 = 100股)
    if market == "cn" and amount % 100 != 0:
        return {
            "error": f"Chinese A-shares must be traded in multiples of 100 shares (1 lot = 100 shares). You tried to buy {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": f"Please use {(amount // 100) * 100} or {((amount // 100) + 1) * 100} shares instead.",
        }

    # Step 2: Generate unique timestamp for order
    import time
    order_timestamp = time.time()

    # Step 3: Define pending orders file path and create directory if needed
    log_path = get_config_value("LOG_PATH", "./data/agent_data")

    # Handle different path formats (same as other files)
    if os.path.isabs(log_path):
        # Absolute path (like temp directory) - use directly
        pending_dir = Path(log_path) / signature / "pending_orders"
    else:
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        pending_dir = Path(project_root) / "data" / log_path / signature / "pending_orders"

    os.makedirs(pending_dir, exist_ok=True)
    pending_file_path = pending_dir / f"{today_date}.jsonl"

    # Step 4: Record order to pending file
    order_data = {
        "timestamp": order_timestamp,
        "action": "buy",
        "symbol": symbol,
        "amount": amount,
        "limit_price": limit_price,
        "market": market,
    }

    try:
        with open(pending_file_path, "a") as f:
            f.write(json.dumps(order_data) + "\n")
    except Exception as e:
        return {
            "error": f"Failed to record order: {e}",
            "symbol": symbol,
            "date": today_date,
        }

    # Step 5: Check if pending orders exist and set IF_TRADE flag accordingly
    try:
        if pending_file_path.exists() and pending_file_path.stat().st_size > 0:
            from tools.general_tools import write_config_value
            write_config_value("IF_TRADE", True)
            print("IF_TRADE", get_config_value("IF_TRADE"))
    except Exception as e:
        # Don't fail the order if IF_TRADE setting fails
        print(f"Warning: Could not set IF_TRADE flag: {e}")

    # Step 6: Return order confirmation without market data leakage
    return {
        "status": "OrderPlaced",
        "message": f"Limit order for {amount} {symbol} @ {limit_price} has been placed and is pending settlement.",
        "symbol": symbol,
        "amount": amount,
        "limit_price": limit_price,
        "date": today_date,
    }




@mcp.tool()
def place_limit_sell_order(symbol: str, amount: int, limit_price: float) -> Dict[str, Any]:
    """
    Place limit sell order function

    This function records a limit sell order for later settlement, including the following steps:
    1. Get signature and today's date
    2. Validate order parameters (amount, limit_price, lot size for CN market)
    3. Generate unique timestamp for order
    4. Record order to pending orders file for later settlement
    5. Return order confirmation without market data leakage

    Args:
        symbol: Stock symbol, such as "AAPL", "MSFT", etc.
        amount: Sell quantity, must be a positive integer, indicating how many shares to sell
                For Chinese A-shares (symbols ending with .SH or .SZ), must be multiples of 100
        limit_price: Minimum price you're willing to accept per share

    Returns:
        Dict[str, Any]:
          - Success: Returns {"status": "OrderPlaced", "message": "..."} dictionary
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = place_limit_sell_order("AAPL", 10, 150.0)
        >>> print(result)  # {"status": "OrderPlaced", "message": "Limit order for 10 AAPL @ 150.0 has been placed and is pending settlement."}
        >>> result = place_limit_sell_order("600519.SH", 100, 1500.0)  # Chinese A-shares must be multiples of 100
        >>> print(result)  # {"status": "OrderPlaced", "message": "Limit order for 100 600519.SH @ 1500.0 has been placed and is pending settlement."}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    # Auto-detect market type based on symbol format
    if symbol.endswith((".SH", ".SZ")):
        market = "cn"
    else:
        market = "us"

    # Amount validation for stocks
    try:
        amount = int(amount)  # Convert to int for stocks
    except ValueError:
        return {
            "error": f"Invalid amount format. Amount must be an integer for stock trading. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to sell {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # Limit price validation
    try:
        limit_price = float(limit_price)
    except ValueError:
        return {
            "error": f"Invalid limit_price format. Must be a number. You provided: {limit_price}",
            "symbol": symbol,
            "date": today_date,
        }

    if limit_price <= 0:
        return {
            "error": f"Limit price must be positive. You tried to set limit price {limit_price}.",
            "symbol": symbol,
            "limit_price": limit_price,
            "date": today_date,
        }

    # 🇨🇳 Chinese A-shares trading rule: Must trade in lots of 100 shares (一手 = 100股)
    if market == "cn" and amount % 100 != 0:
        return {
            "error": f"Chinese A-shares must be traded in multiples of 100 shares (1 lot = 100 shares). You tried to sell {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": f"Please use {(amount // 100) * 100} or {((amount // 100) + 1) * 100} shares instead.",
        }

    # Step 2: Generate unique timestamp for order
    import time
    order_timestamp = time.time()

    # Step 3: Define pending orders file path and create directory if needed
    log_path = get_config_value("LOG_PATH", "./data/agent_data")

    # Handle different path formats (same as other files)
    if os.path.isabs(log_path):
        # Absolute path (like temp directory) - use directly
        pending_dir = Path(log_path) / signature / "pending_orders"
    else:
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        pending_dir = Path(project_root) / "data" / log_path / signature / "pending_orders"

    os.makedirs(pending_dir, exist_ok=True)
    pending_file_path = pending_dir / f"{today_date}.jsonl"

    # Step 4: Record order to pending file
    order_data = {
        "timestamp": order_timestamp,
        "action": "sell",
        "symbol": symbol,
        "amount": amount,
        "limit_price": limit_price,
        "market": market,
    }

    try:
        with open(pending_file_path, "a") as f:
            f.write(json.dumps(order_data) + "\n")
    except Exception as e:
        return {
            "error": f"Failed to record order: {e}",
            "symbol": symbol,
            "date": today_date,
        }

    # Step 5: Check if pending orders exist and set IF_TRADE flag accordingly
    try:
        if pending_file_path.exists() and pending_file_path.stat().st_size > 0:
            from tools.general_tools import write_config_value
            write_config_value("IF_TRADE", True)
            print("IF_TRADE", get_config_value("IF_TRADE"))
    except Exception as e:
        # Don't fail the order if IF_TRADE setting fails
        print(f"Warning: Could not set IF_TRADE flag: {e}")

    # Step 6: Return order confirmation without market data leakage
    return {
        "status": "OrderPlaced",
        "message": f"Limit order for {amount} {symbol} @ {limit_price} has been placed and is pending settlement.",
        "symbol": symbol,
        "amount": amount,
        "limit_price": limit_price,
        "date": today_date,
    }


if __name__ == "__main__":
    # new_result = buy("AAPL", 1, 150.0)
    # print(new_result)
    # new_result = sell("AAPL", 1, 150.0)
    # print(new_result)
    port = int(os.getenv("TRADE_LIMIT_HTTP_PORT", "8006"))  # Using port 8006 for A-share testing as specified in SOP
    mcp.run(transport="streamable-http", port=port)
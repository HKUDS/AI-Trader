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

from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import (get_latest_position, get_open_prices,
                               get_yesterday_date,
                               get_yesterday_open_and_close_price,
                               get_yesterday_profit)

mcp = FastMCP("CryptoTradeTools")

def _position_lock(signature: str):
    """Context manager for file-based lock to serialize position updates per signature."""
    class _Lock:
        def __init__(self, name: str):
            base_dir = Path(project_root) / "data" / "agent_data" / name
            base_dir.mkdir(parents=True, exist_ok=True)
            self.lock_path = base_dir / ".position.lock"
            # Ensure lock file exists
            self._fh = open(self.lock_path, "a+")
        def __enter__(self):
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            return self
        def __exit__(self, exc_type, exc, tb):
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
    return _Lock(signature)



@mcp.tool()
def buy_crypto(symbol: str, amount: float) -> Dict[str, Any]:
    """
    Buy cryptocurrency function

    This function simulates cryptocurrency buying operations, including the following steps:
    1. Get current position and operation ID
    2. Get cryptocurrency opening price for the day
    3. Validate buy conditions (sufficient cash)
    4. Update position (increase crypto quantity, decrease cash)
    5. Record transaction to position.jsonl file

    Args:
        symbol: Cryptocurrency symbol, such as "BTC-USDT", "ETH-USDT", etc.
        amount: Buy quantity, must be a positive float, indicating how many units to buy

    Returns:
        Dict[str, Any]:
          - Success: Returns new position dictionary (containing crypto quantity and cash balance)
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = buy_crypto("BTC-USDT", 0.05)
        >>> print(result)  # {"BTC-USDT": 0.05, "ETH-USDT": 1.2, "CASH": 5000.0, ...}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    # Fixed market type for crypto
    market = "crypto"

    # Amount validation for Crypto
    try:
        amount = float(amount)  # Convert to float to allow decimals
    except ValueError:
        return {
            "error": f"Invalid amount format. Amount must be a number. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to buy {amount} units.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # Step 2: Get current latest position and operation ID
    # get_latest_position returns two values: position dictionary and current maximum operation ID
    # This ID is used to ensure each operation has a unique identifier
    # Acquire lock for atomic read-modify-write on positions
    with _position_lock(signature):
        try:
            current_position, current_action_id = get_latest_position(today_date, signature)
        except Exception as e:
            print(e)
            print(today_date, signature)
            return {"error": f"Failed to load latest position: {e}", "symbol": symbol, "date": today_date}
        # Step 3: Get cryptocurrency opening price for the day
        # Use get_open_prices function to get the opening price of specified crypto for the day
        # If crypto symbol does not exist or price data is missing, KeyError exception will be raised
        try:
            this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
        except KeyError:
            # Crypto symbol does not exist or price data is missing, return error message
            return {
                "error": f"Symbol {symbol} not found! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        # Step 4: Validate buy conditions
        # Calculate cash required for purchase: crypto price × buy quantity
        try:
            cash_left = current_position["CASH"] - this_symbol_price * amount
        except Exception as e:
            print(current_position, "CASH", this_symbol_price, amount)

        # Check if cash balance is sufficient for purchase
        if cash_left < 0:
            # Insufficient cash, return error message
            return {
                "error": "Insufficient cash! This action will not be allowed.",
                "required_cash": round(this_symbol_price * amount, 4),
                "cash_available": round(current_position.get("CASH", 0), 4),
                "symbol": symbol,
                "date": today_date,
            }
        else:
            # Step 5: Execute buy operation, update position
            # Create a copy of current position to avoid directly modifying original data
            new_position = current_position.copy()

            # Decrease cash balance with 4 decimal precision
            new_position["CASH"] = round(cash_left, 4)

            # Increase crypto position quantity with 4 decimal precision
            new_position[symbol] = round(new_position[symbol] + amount, 4)

            # Step 6: Record transaction to position.jsonl file
            # Build file path: {project_root}/data/{log_path}/{signature}/position/position.jsonl
            # Use append mode ("a") to write new transaction record
            # Each operation ID increments by 1, ensuring uniqueness of operation sequence
            log_path = get_config_value("LOG_PATH", "./data/agent_data")
            if log_path.startswith("./data/"):
                log_path = log_path[7:]  # Remove "./data/" prefix
            position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")
            with open(position_file_path, "a") as f:
                # Write JSON format transaction record, containing date, operation ID, transaction details and updated position
                print(
                    f"Writing to position.jsonl: {json.dumps({'date': today_date, 'id': current_action_id + 1, 'this_action':{'action':'buy_crypto','symbol':symbol,'amount':amount},'positions': new_position})}"
                )
                f.write(
                    json.dumps(
                        {
                            "date": today_date,
                            "id": current_action_id + 1,
                            "this_action": {"action": "buy_crypto", "symbol": symbol, "amount": amount},
                            "positions": new_position,
                        }
                    )
                    + "\n"
                )
            # Step 7: Return updated position
            write_config_value("IF_TRADE", True)
            print("IF_TRADE", get_config_value("IF_TRADE"))
        
    return new_position


@mcp.tool()
def sell_crypto(symbol: str, amount: float) -> Dict[str, Any]:
    """
    Sell cryptocurrency function

    This function simulates cryptocurrency selling operations, including the following steps:
    1. Get current position and operation ID
    2. Get cryptocurrency opening price for the day
    3. Validate sell conditions (position exists, sufficient quantity)
    4. Update position (decrease crypto quantity, increase cash)
    5. Record transaction to position.jsonl file

    Args:
        symbol: Cryptocurrency symbol, such as "BTC-USDT", "ETH-USDT", etc.
        amount: Sell quantity, must be a positive float, indicating how many units to sell

    Returns:
        Dict[str, Any]:
          - Success: Returns new position dictionary (containing crypto quantity and cash balance)
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = sell_crypto("BTC-USDT", 0.05)
        >>> print(result)  # {"BTC-USDT": 0.0, "ETH-USDT": 1.2, "CASH": 15000.0, ...}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    # Fixed market type for crypto
    market = "crypto"

    # Amount validation for Crypto
    try:
        amount = float(amount)  # Convert to float to allow decimals
    except ValueError:
        return {
            "error": f"Invalid amount format. Amount must be a number. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to sell {amount} units.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # Step 2: Get current latest position and operation ID
    # get_latest_position returns two values: position dictionary and current maximum operation ID
    # This ID is used to ensure each operation has a unique identifier
    with _position_lock(signature):
        try:
            current_position, current_action_id = get_latest_position(today_date, signature)
        except Exception as e:
            print(e)
            print(today_date, signature)
            return {"error": f"Failed to load latest position: {e}",
                    "symbol": symbol,
                    "date": today_date}
        # Step 3: Get cryptocurrency opening price for the day
        # Use get_open_prices function to get the opening price of specified crypto for the day
        # If crypto symbol does not exist or price data is missing, KeyError exception will be raised
        try:
            this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
        except KeyError:
            # Crypto symbol does not exist or price data is missing, return error message
            return {
                "error": f"Symbol {symbol} not found! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        # Step 4: Validate sell conditions
        # Check if holding this crypto
        if symbol not in current_position:
            return {
                "error": f"No position for {symbol}! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        # Check if position quantity is sufficient for selling
        if current_position[symbol] < amount:
            return {
                "error": "Insufficient crypto! This action will not be allowed.",
                "have": current_position.get(symbol, 0),
                "want_to_sell": amount,
                "symbol": symbol,
                "date": today_date,
            }

        # Step 5: Execute sell operation, update position
        # Create a copy of current position to avoid directly modifying original data
        new_position = current_position.copy()

        # Decrease crypto position quantity with 4 decimal precision
        new_position[symbol] = round(new_position[symbol] - amount, 4)

        # Increase cash balance: sell price × sell quantity with 4 decimal precision
        # Use get method to ensure CASH field exists, default to 0 if not present
        new_position["CASH"] = round(new_position.get("CASH", 0) + this_symbol_price * amount, 4)

        # Step 6: Record transaction to position.jsonl file
        # Build file path: {project_root}/data/{log_path}/{signature}/position/position.jsonl
        # Use append mode ("a") to write new transaction record
        # Each operation ID increments by 1, ensuring uniqueness of operation sequence
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")
        with open(position_file_path, "a") as f:
            # Write JSON format transaction record, containing date, operation ID and updated position
            print(
                f"Writing to position.jsonl: {json.dumps({'date': today_date, 'id': current_action_id + 1, 'this_action':{'action':'sell_crypto','symbol':symbol,'amount':amount},'positions': new_position})}"
            )
            f.write(
                json.dumps(
                    {
                        "date": today_date,
                        "id": current_action_id + 1,
                        "this_action": {"action": "sell_crypto", "symbol": symbol, "amount": amount},
                        "positions": new_position,
                    }
                )
                + "\n"
            )

        # Step 7: Return updated position
        write_config_value("IF_TRADE", True)
    
    return new_position


if __name__ == "__main__":
    # new_result = buy_crypto("BTC-USDT", 0.05)
    # print(new_result)
    # new_result = sell_crypto("BTC-USDT", 0.05)
    # print(new_result)
    port = int(os.getenv("CRYPTO_HTTP_PORT", "8014"))
    mcp.run(transport="streamable-http", port=port)
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, timedelta

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from tools.position_utils import get_position_lock, get_latest_position
from tools.price_tools import get_high_low_prices, get_yesterday_date, get_market_type
from tools.general_tools import get_config_value


def run_daily_settlement(today_date: str, signature: str) -> None:
    """
    Run daily settlement for pending orders.

    This function processes all pending orders for the given date and executes them
    according to the T+0 and T+1 trading rules. It updates positions and records
    the settlement results.

    Args:
        today_date: Trading date in YYYY-MM-DD format
        signature: Model signature for data path

    Returns:
        None
    """
    # Step 1: (Atomic operation start)
    # Must use the position lock to ensure atomic read-modify-write operations
    with get_position_lock(signature):

        # Step 2: Load T-1 day position (T day start position)
        yesterday_date = get_yesterday_date(today_date, market=get_market_type())
        start_position, last_action_id = get_latest_position(yesterday_date, signature)
        settled_position = start_position.copy()

        # Step 2.5: Check if settlement has already been run for today's date
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix

        try:
            today_position, today_last_id = get_latest_position(today_date, signature)
            # Look for any settlement record for today
            position_file = Path(project_root) / "data" / log_path / signature / "position" / "position.jsonl"

            with position_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("date") == today_date and record.get("this_action", {}).get("action") == "daily_settlement":
                            print(f"⚠️ Settlement already completed for {today_date}, skipping")
                            return
                    except Exception:
                        continue
        except Exception as e:
            # No position for today yet or file doesn't exist, continue with settlement
            pass

        # Step 3: Load T day pending orders

        pending_dir = Path(project_root) / "data" / log_path / signature / "pending_orders"
        pending_file_path = pending_dir / f"{today_date}.jsonl"

        if not pending_file_path.exists():
            # No orders for T day, save position record anyway
            _save_position_record(today_date, signature, last_action_id + 1, [], settled_position)
            return

        # Load all pending orders
        pending_orders = []
        try:
            with open(pending_file_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        pending_orders.append(json.loads(line))
                    except Exception:
                        continue
        except Exception as e:
            print(f"Error reading pending orders: {e}")
            return

        if not pending_orders:
            # No orders to process, save position record
            _save_position_record(today_date, signature, last_action_id + 1, [], settled_position)
            return

        # Step 4: Sort orders by timestamp (T+0 critical)
        # Must sort by timestamp/ID to ensure T+0 "buy before sell" rule
        sorted_orders = sorted(pending_orders, key=lambda x: x['timestamp'])

        # Step 5: Get T day real prices (only get them here)
        # Since all orders in a single agent are from the same market,
        # we can use the market from the first order
        market = sorted_orders[0]['market'] if sorted_orders else 'us'
        all_symbols = list(set([o['symbol'] for o in sorted_orders]))
        market_data = get_high_low_prices(today_date, all_symbols, market=market)

        # Step 6: Initialize
        shares_bought_today_cn = defaultdict(int)  # T+1 tracking
        executed_trades_log = []  # Record all T day execution results

        # Step 7: Iterate and settle orders (by sort order)
        for order in sorted_orders:
            symbol = order['symbol']
            action = order['action']
            amount = order['amount']
            limit_price = order['limit_price']
            market = order['market']

            # Skip if no market data available
            if symbol not in market_data or market_data[symbol] is None:
                executed_trades_log.append({
                    "timestamp": order['timestamp'],
                    "action": action,
                    "symbol": symbol,
                    "amount": amount,
                    "limit_price": limit_price,
                    "status": "Failed-NoMarketData",
                    "message": f"No market data available for {symbol}"
                })
                continue

            day_low = market_data[symbol].get('low')
            day_high = market_data[symbol].get('high')

            if day_low is None or day_high is None:
                executed_trades_log.append({
                    "timestamp": order['timestamp'],
                    "action": action,
                    "symbol": symbol,
                    "amount": amount,
                    "limit_price": limit_price,
                    "status": "Failed-NoPriceData",
                    "message": f"No price data available for {symbol}"
                })
                continue

            # Step 7.1: Check price (Buy)
            if action == 'buy':
                if limit_price >= day_low:
                    # Step 7.2: Check cash
                    cost = limit_price * amount
                    if settled_position.get('CASH', 0) >= cost:
                        # Execute buy
                        settled_position['CASH'] -= cost
                        settled_position[symbol] = settled_position.get(symbol, 0) + amount
                        if market == 'cn':
                            shares_bought_today_cn[symbol] += amount
                        executed_trades_log.append({
                            "timestamp": order['timestamp'],
                            "action": action,
                            "symbol": symbol,
                            "amount": amount,
                            "limit_price": limit_price,
                            "filled_price": limit_price,  # Simplified: fill at limit price
                            "status": "Filled",
                            "message": f"Buy order filled at {limit_price}"
                        })
                    else:
                        executed_trades_log.append({
                            "timestamp": order['timestamp'],
                            "action": action,
                            "symbol": symbol,
                            "amount": amount,
                            "limit_price": limit_price,
                            "status": "Failed-Cash",
                            "message": f"Insufficient cash: need {cost}, have {settled_position.get('CASH', 0)}"
                        })
                else:
                    executed_trades_log.append({
                        "timestamp": order['timestamp'],
                        "action": action,
                        "symbol": symbol,
                        "amount": amount,
                        "limit_price": limit_price,
                        "day_low_price": day_low,
                        "status": "OrderNotFilled-Price",
                        "message": f"Limit price {limit_price} below day low {day_low}"
                    })

            # Step 7.3: Check price (Sell)
            elif action == 'sell':
                if limit_price <= day_high:
                    # Step 7.4: Check position (T+0 vs T+1)
                    total_shares = settled_position.get(symbol, 0)

                    if market == 'cn':
                        # T+1 rule: cannot sell shares bought today
                        sellable = total_shares - shares_bought_today_cn.get(symbol, 0)
                    else:  # T+0
                        sellable = total_shares

                    if sellable >= amount:
                        # Execute sell
                        revenue = limit_price * amount
                        settled_position[symbol] -= amount
                        settled_position['CASH'] = settled_position.get('CASH', 0) + revenue
                        executed_trades_log.append({
                            "timestamp": order['timestamp'],
                            "action": action,
                            "symbol": symbol,
                            "amount": amount,
                            "limit_price": limit_price,
                            "filled_price": limit_price,  # Simplified: fill at limit price
                            "status": "Filled",
                            "message": f"Sell order filled at {limit_price}"
                        })
                    else:
                        reason = "T+1 restriction" if market == 'cn' else "Insufficient shares"
                        executed_trades_log.append({
                            "timestamp": order['timestamp'],
                            "action": action,
                            "symbol": symbol,
                            "amount": amount,
                            "limit_price": limit_price,
                            "total_shares": total_shares,
                            "sellable_shares": sellable,
                            "status": "Failed-Shares/T+1",
                            "message": f"{reason}: have {total_shares}, sellable {sellable}, want {amount}"
                        })
                else:
                    executed_trades_log.append({
                        "timestamp": order['timestamp'],
                        "action": action,
                        "symbol": symbol,
                        "amount": amount,
                        "limit_price": limit_price,
                        "day_high_price": day_high,
                        "status": "OrderNotFilled-Price",
                        "message": f"Limit price {limit_price} above day high {day_high}"
                    })

        # Step 8: Write T day final position (single write)
        _save_position_record(today_date, signature, last_action_id + 1, executed_trades_log, settled_position)

    # Step 9: (Atomic operation end)

    # Step 10: Clean up pending orders for the day
    # try:
    #     if pending_file_path.exists():
    #         os.remove(pending_file_path)
    # except Exception as e:
    #     print(f"Error removing pending orders file: {e}")


def _save_position_record(today_date: str, signature: str, action_id: int,
                         trades_log: List[Dict[str, Any]], positions: Dict[str, float]) -> None:
    """
    Save position record to position.jsonl file.

    Args:
        today_date: Trading date
        signature: Model signature
        action_id: Action ID for this record
        trades_log: List of executed trades
        positions: Final positions after settlement
    """
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]  # Remove "./data/" prefix

    position_dir = Path(project_root) / "data" / log_path / signature / "position"
    position_dir.mkdir(parents=True, exist_ok=True)
    position_file_path = position_dir / "position.jsonl"

    log_entry = {
        "date": today_date,
        "id": action_id,
        "this_action": {
            "action": "daily_settlement",
            "trades": trades_log  # Detailed record of all T day results
        },
        "positions": positions  # T day final position
    }

    try:
        with open(position_file_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Error saving position record: {e}")
"""
Forex Trade MCP Tools for MT4/MT5 and web trading platforms.

Provides buy/sell/close/price/account tools that connect to a live
trading account via configurable backend.

Backends:
  - mt5_native: MetaTrader5 Python package (Windows, lowest latency)
  - metaapi: MetaApi cloud SDK (any OS, ~100ms latency)
  - browser: Playwright automation of FundedNext web trader (any OS)
  - simulation: Local simulation for testing (no real execution)

Usage:
  python agent_tools/tool_forex_trade.py

  This starts the MCP service on FOREX_HTTP_PORT (default 8006).
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value, write_config_value

mcp = FastMCP("ForexTradeTools")

# ── MT4/MT5 Backend Adapter ──────────────────────────────────────────

# Pip sizes for common forex pairs
# Most pairs: 1 pip = 0.0001 (4th decimal)
# JPY pairs: 1 pip = 0.01 (2nd decimal)
PIP_SIZES = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "NZDUSD": 0.0001, "USDCHF": 0.0001, "USDCAD": 0.0001,
    "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01,
    "AUDJPY": 0.01, "NZDJPY": 0.01, "EURGBP": 0.0001,
    "EURCHF": 0.0001, "GBPCHF": 0.0001, "AUDNZD": 0.0001,
}

# Pip values per standard lot (approximate, in USD)
PIP_VALUES = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
    "NZDUSD": 10.0, "USDCHF": 10.0, "USDCAD": 10.0,
    "USDJPY": 6.67, "EURGBP": 12.50, "EURJPY": 6.67,
    "EURCHF": 10.0, "GBPJPY": 6.67, "GBPCHF": 10.0,
    "AUDJPY": 6.67, "NZDJPY": 6.67, "AUDNZD": 6.50,
}


def _get_backend():
    """Get the configured MT4/MT5 backend type."""
    return os.getenv("FOREX_BACKEND", "simulation")


def _init_mt5():
    """
    Initialize MT5 connection, optionally pointing to a specific terminal.

    Set MT5_PATH in .env to the terminal64.exe path if running multiple
    MT5 instances (e.g., one for IC Markets, one for FundedNext).

    Example:
        MT5_PATH=C:\\Program Files\\MetaTrader 5 IC\\terminal64.exe
    """
    import MetaTrader5 as mt5
    mt5_path = os.getenv("MT5_PATH")
    if mt5_path:
        return mt5.initialize(mt5_path)
    return mt5.initialize()


def _get_position_file():
    """Get the position file path for the current agent."""
    signature = get_config_value("SIGNATURE")
    log_path = get_config_value("LOG_PATH", "./data/agent_data_forex")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]
    return os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")


def _get_latest_position():
    """Read the latest position from the JSONL file."""
    position_file = _get_position_file()
    if not os.path.exists(position_file):
        return None, 0

    last_line = None
    with open(position_file, "r") as f:
        for line in f:
            if line.strip():
                last_line = line

    if last_line is None:
        return None, 0

    data = json.loads(last_line)
    return data.get("positions", {}), data.get("id", 0)


def _write_position(date: str, action_id: int, action: Dict, positions: Dict):
    """Append a position record to the JSONL file."""
    position_file = _get_position_file()
    os.makedirs(os.path.dirname(position_file), exist_ok=True)
    with open(position_file, "a") as f:
        record = {
            "date": date,
            "id": action_id,
            "this_action": action,
            "positions": positions,
            "timestamp": datetime.utcnow().isoformat(),
        }
        f.write(json.dumps(record) + "\n")


# ── MCP Tools ────────────────────────────────────────────────────────

@mcp.tool()
def get_forex_price(symbol: str) -> Dict[str, Any]:
    """
    Get current bid/ask/spread for a forex pair.

    Args:
        symbol: Forex pair (e.g., "EURUSD", "GBPUSD")

    Returns:
        Dict with bid, ask, spread (in pips), and timestamp.
    """
    backend = _get_backend()

    if backend == "mt5_native":
        try:
            import MetaTrader5 as mt5
            if not _init_mt5():
                return {"error": "MT5 not initialized. Check MT5 is running and MT5_PATH is correct."}
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"error": f"Symbol {symbol} not found in MT5"}
            pip_size = PIP_SIZES.get(symbol, 0.0001)
            spread_pips = round((tick.ask - tick.bid) / pip_size, 1)
            return {
                "symbol": symbol,
                "bid": round(tick.bid, 5),
                "ask": round(tick.ask, 5),
                "spread_pips": spread_pips,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except ImportError:
            return {"error": "MetaTrader5 package not installed. pip install MetaTrader5"}

    elif backend == "metaapi":
        # MetaApi integration placeholder
        return {
            "error": "MetaApi backend not yet configured. Set METAAPI_TOKEN and METAAPI_ACCOUNT_ID in .env",
            "symbol": symbol,
        }

    else:
        # Simulation mode - return realistic prices
        simulated_prices = {
            "EURUSD": (1.0850, 1.0852), "GBPUSD": (1.2640, 1.2643),
            "USDJPY": (149.50, 149.53), "USDCHF": (0.8830, 0.8833),
            "AUDUSD": (0.6520, 0.6523), "NZDUSD": (0.6080, 0.6083),
            "USDCAD": (1.3560, 1.3563),
        }
        bid, ask = simulated_prices.get(symbol, (1.0000, 1.0003))
        pip_size = PIP_SIZES.get(symbol, 0.0001)
        spread_pips = round((ask - bid) / pip_size, 1)
        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread_pips": spread_pips,
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "SIMULATION",
        }


@mcp.tool()
def calculate_lot_size(
    balance: float,
    risk_percent: float,
    stop_loss_pips: float,
    symbol: str = "EURUSD",
    take_profit_pips: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate correct lot size based on account balance, risk %, and SL distance.

    The stop-loss should be placed at market-structure invalidation first,
    then this tool calculates the lot size to risk the correct dollar amount.
    Never force a fixed SL distance - let the market dictate the SL, then
    size the position accordingly.

    Args:
        balance: Current account balance in USD
        risk_percent: Percentage of balance to risk (e.g., 0.5 for 0.5%)
        stop_loss_pips: Stop loss distance in pips (based on market structure)
        symbol: Forex pair (default: EURUSD)
        take_profit_pips: Take profit distance in pips (optional, for R:R calc)

    Returns:
        Dict with calculated lot size, risk amount, R:R ratio, and pip value.

    Example:
        balance=$50000, risk_percent=0.5, stop_loss_pips=15, symbol=EURUSD
        -> risk_amount=$250, lot_size=1.67, R:R depends on TP distance
    """
    risk_amount = balance * (risk_percent / 100)
    pip_value_needed = risk_amount / stop_loss_pips
    pip_value_per_lot = PIP_VALUES.get(symbol, 10.0)
    lot_size = pip_value_needed / pip_value_per_lot

    # Round to nearest 0.01 lot (standard mini lot increment)
    lot_size = max(0.01, round(lot_size, 2))

    # Recalculate actual risk with rounded lot size
    actual_risk = lot_size * pip_value_per_lot * stop_loss_pips

    # Calculate R:R if TP provided
    rr_ratio = round(take_profit_pips / stop_loss_pips, 2) if take_profit_pips > 0 else None
    potential_profit = lot_size * pip_value_per_lot * take_profit_pips if take_profit_pips > 0 else None

    result = {
        "symbol": symbol,
        "balance": round(balance, 2),
        "risk_percent": risk_percent,
        "risk_amount_target": round(risk_amount, 2),
        "stop_loss_pips": stop_loss_pips,
        "pip_value_per_lot": pip_value_per_lot,
        "calculated_lot_size": lot_size,
        "actual_risk_usd": round(actual_risk, 2),
    }

    if rr_ratio is not None:
        result["take_profit_pips"] = take_profit_pips
        result["risk_reward_ratio"] = rr_ratio
        result["potential_profit_usd"] = round(potential_profit, 2)

    return result


@mcp.tool()
def buy_forex(
    symbol: str,
    lots: float,
    stop_loss_pips: float = 20.0,
    take_profit_pips: float = 20.0,
) -> Dict[str, Any]:
    """
    Open a BUY (long) position on a forex pair.

    Args:
        symbol: Forex pair (e.g., "EURUSD")
        lots: Position size in lots (0.01 = micro lot)
        stop_loss_pips: Stop loss distance in pips (default: 20)
        take_profit_pips: Take profit distance in pips (default: 20)

    Returns:
        Dict with order result including ticket number, entry price, SL, TP.
    """
    if lots <= 0:
        return {"error": f"Lot size must be positive. Got: {lots}"}

    if stop_loss_pips <= 0:
        return {"error": "Stop loss must be set. Trading without SL is forbidden."}

    backend = _get_backend()
    today_date = get_config_value("TODAY_DATE") or datetime.utcnow().strftime("%Y-%m-%d")
    signature = get_config_value("SIGNATURE")

    if backend == "mt5_native":
        try:
            import MetaTrader5 as mt5
            if not _init_mt5():
                return {"error": "MT5 not initialized. Check MT5 is running and MT5_PATH is correct."}
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"error": f"Symbol {symbol} not found"}

            pip_size = PIP_SIZES.get(symbol, 0.0001)
            sl_price = tick.ask - (stop_loss_pips * pip_size)
            tp_price = tick.ask + (take_profit_pips * pip_size)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lots,
                "type": mt5.ORDER_TYPE_BUY,
                "price": tick.ask,
                "sl": round(sl_price, 5),
                "tp": round(tp_price, 5),
                "magic": 234000,
                "comment": f"AI-Trader {signature}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"error": f"Order failed: {result.comment}", "retcode": result.retcode}

            # Log to position file
            positions, action_id = _get_latest_position()
            if positions:
                positions[symbol] = positions.get(symbol, 0) + lots
            _write_position(today_date, action_id + 1,
                          {"action": "buy_forex", "symbol": symbol, "lots": lots,
                           "price": tick.ask, "sl": sl_price, "tp": tp_price,
                           "ticket": result.order},
                          positions or {})

            write_config_value("IF_TRADE", True)
            return {
                "status": "filled",
                "ticket": result.order,
                "symbol": symbol,
                "direction": "BUY",
                "lots": lots,
                "entry_price": tick.ask,
                "stop_loss": round(sl_price, 5),
                "take_profit": round(tp_price, 5),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except ImportError:
            return {"error": "MetaTrader5 package not installed"}

    else:
        # Simulation mode
        price_data = get_forex_price(symbol)
        if "error" in price_data:
            return price_data

        ask = price_data["ask"]
        pip_size = PIP_SIZES.get(symbol, 0.0001)
        sl_price = round(ask - (stop_loss_pips * pip_size), 5)
        tp_price = round(ask + (take_profit_pips * pip_size), 5)

        # Log to position file
        positions, action_id = _get_latest_position()
        if positions:
            positions[symbol] = positions.get(symbol, 0) + lots
            pip_value = PIP_VALUES.get(symbol, 10.0)
            # Don't deduct cash in simulation (margin trading)
        _write_position(today_date, action_id + 1,
                      {"action": "buy_forex", "symbol": symbol, "lots": lots,
                       "price": ask, "sl": sl_price, "tp": tp_price},
                      positions or {})

        write_config_value("IF_TRADE", True)
        return {
            "status": "filled",
            "ticket": f"SIM-{action_id + 1}",
            "symbol": symbol,
            "direction": "BUY",
            "lots": lots,
            "entry_price": ask,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "SIMULATION",
        }


@mcp.tool()
def sell_forex(
    symbol: str,
    lots: float,
    stop_loss_pips: float = 20.0,
    take_profit_pips: float = 20.0,
) -> Dict[str, Any]:
    """
    Open a SELL (short) position on a forex pair.

    Args:
        symbol: Forex pair (e.g., "EURUSD")
        lots: Position size in lots (0.01 = micro lot)
        stop_loss_pips: Stop loss distance in pips (default: 20)
        take_profit_pips: Take profit distance in pips (default: 20)

    Returns:
        Dict with order result including ticket number, entry price, SL, TP.
    """
    if lots <= 0:
        return {"error": f"Lot size must be positive. Got: {lots}"}

    if stop_loss_pips <= 0:
        return {"error": "Stop loss must be set. Trading without SL is forbidden."}

    backend = _get_backend()
    today_date = get_config_value("TODAY_DATE") or datetime.utcnow().strftime("%Y-%m-%d")
    signature = get_config_value("SIGNATURE")

    if backend == "mt5_native":
        try:
            import MetaTrader5 as mt5
            if not _init_mt5():
                return {"error": "MT5 not initialized. Check MT5 is running and MT5_PATH is correct."}
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"error": f"Symbol {symbol} not found"}

            pip_size = PIP_SIZES.get(symbol, 0.0001)
            sl_price = tick.bid + (stop_loss_pips * pip_size)
            tp_price = tick.bid - (take_profit_pips * pip_size)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lots,
                "type": mt5.ORDER_TYPE_SELL,
                "price": tick.bid,
                "sl": round(sl_price, 5),
                "tp": round(tp_price, 5),
                "magic": 234000,
                "comment": f"AI-Trader {signature}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"error": f"Order failed: {result.comment}", "retcode": result.retcode}

            positions, action_id = _get_latest_position()
            if positions:
                positions[symbol] = positions.get(symbol, 0) - lots
            _write_position(today_date, action_id + 1,
                          {"action": "sell_forex", "symbol": symbol, "lots": lots,
                           "price": tick.bid, "sl": sl_price, "tp": tp_price,
                           "ticket": result.order},
                          positions or {})

            write_config_value("IF_TRADE", True)
            return {
                "status": "filled",
                "ticket": result.order,
                "symbol": symbol,
                "direction": "SELL",
                "lots": lots,
                "entry_price": tick.bid,
                "stop_loss": round(sl_price, 5),
                "take_profit": round(tp_price, 5),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except ImportError:
            return {"error": "MetaTrader5 package not installed"}

    else:
        # Simulation mode
        price_data = get_forex_price(symbol)
        if "error" in price_data:
            return price_data

        bid = price_data["bid"]
        pip_size = PIP_SIZES.get(symbol, 0.0001)
        sl_price = round(bid + (stop_loss_pips * pip_size), 5)
        tp_price = round(bid - (take_profit_pips * pip_size), 5)

        positions, action_id = _get_latest_position()
        if positions:
            positions[symbol] = positions.get(symbol, 0) - lots
        _write_position(today_date, action_id + 1,
                      {"action": "sell_forex", "symbol": symbol, "lots": lots,
                       "price": bid, "sl": sl_price, "tp": tp_price},
                      positions or {})

        write_config_value("IF_TRADE", True)
        return {
            "status": "filled",
            "ticket": f"SIM-{action_id + 1}",
            "symbol": symbol,
            "direction": "SELL",
            "lots": lots,
            "entry_price": bid,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "SIMULATION",
        }


@mcp.tool()
def close_forex_position(ticket: str) -> Dict[str, Any]:
    """
    Close an open forex position by ticket number.

    Args:
        ticket: The order ticket number to close.

    Returns:
        Dict with close result.
    """
    backend = _get_backend()

    if backend == "mt5_native":
        try:
            import MetaTrader5 as mt5
            if not _init_mt5():
                return {"error": "MT5 not initialized. Check MT5 is running and MT5_PATH is correct."}

            position = mt5.positions_get(ticket=int(ticket))
            if not position:
                return {"error": f"Position {ticket} not found"}

            pos = position[0]
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(pos.symbol)
            price = tick.bid if pos.type == 0 else tick.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "magic": 234000,
                "comment": "AI-Trader close",
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"error": f"Close failed: {result.comment}"}

            return {
                "status": "closed",
                "ticket": ticket,
                "symbol": pos.symbol,
                "profit": pos.profit,
                "close_price": price,
            }
        except ImportError:
            return {"error": "MetaTrader5 package not installed"}

    else:
        return {
            "status": "closed",
            "ticket": ticket,
            "mode": "SIMULATION",
            "note": "Position closed in simulation",
        }


@mcp.tool()
def get_account_summary() -> Dict[str, Any]:
    """
    Get MT4/MT5 account balance, equity, margin, and free margin.

    Returns:
        Dict with account financial information.
    """
    backend = _get_backend()

    if backend == "mt5_native":
        try:
            import MetaTrader5 as mt5
            if not _init_mt5():
                return {"error": "MT5 not initialized. Check MT5 is running and MT5_PATH is correct."}

            info = mt5.account_info()
            if info is None:
                return {"error": "Failed to get account info"}

            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "free_margin": info.margin_free,
                "margin_level": info.margin_level,
                "profit": info.profit,
                "leverage": f"{info.leverage}:1",
                "currency": info.currency,
            }
        except ImportError:
            return {"error": "MetaTrader5 package not installed"}

    elif backend == "browser":
        # Browser backend: read from FundedNext web trader via Playwright
        return {
            "error": "Browser backend not yet configured. "
                     "Set FUNDEDNEXT_EMAIL and FUNDEDNEXT_PASSWORD in .env",
        }

    else:
        # Simulation: read from position file
        positions, action_id = _get_latest_position()
        balance = 50000.0
        if positions:
            balance = positions.get("CASH", 50000.0)
        return {
            "balance": balance,
            "equity": balance,
            "margin": 0.0,
            "free_margin": balance,
            "margin_level": 0.0,
            "profit": 0.0,
            "leverage": "100:1",
            "currency": "USD",
            "mode": "SIMULATION",
        }


@mcp.tool()
def get_open_trades() -> Dict[str, Any]:
    """
    List all currently open forex positions.

    Returns:
        Dict with list of open positions or empty list.
    """
    backend = _get_backend()

    if backend == "mt5_native":
        try:
            import MetaTrader5 as mt5
            if not _init_mt5():
                return {"error": "MT5 not initialized. Check MT5 is running and MT5_PATH is correct."}

            positions = mt5.positions_get()
            if positions is None or len(positions) == 0:
                return {"open_positions": [], "count": 0}

            trades = []
            for pos in positions:
                trades.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "direction": "BUY" if pos.type == 0 else "SELL",
                    "lots": pos.volume,
                    "entry_price": pos.price_open,
                    "current_price": pos.price_current,
                    "stop_loss": pos.sl,
                    "take_profit": pos.tp,
                    "profit": pos.profit,
                    "pips": round(
                        abs(pos.price_current - pos.price_open) / PIP_SIZES.get(pos.symbol, 0.0001),
                        1
                    ),
                })

            return {"open_positions": trades, "count": len(trades)}
        except ImportError:
            return {"error": "MetaTrader5 package not installed"}

    else:
        return {
            "open_positions": [],
            "count": 0,
            "mode": "SIMULATION",
        }


if __name__ == "__main__":
    port = int(os.getenv("FOREX_HTTP_PORT", "8006"))
    print(f"Starting Forex Trade MCP service on port {port}")
    mcp.run(transport="streamable-http", port=port)

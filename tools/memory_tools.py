"""
Memory management tools for trading agents.
Provides context accumulation across trading sessions while maintaining backtest integrity.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict


def get_trading_history(
    signature: str,
    current_date: str,
    lookback_days: int = 5,
    base_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get recent trading history for context.

    Args:
        signature: Model signature/name
        current_date: Current trading date (YYYY-MM-DD)
        lookback_days: Number of previous trading days to retrieve
        base_path: Base path to agent data (defaults to ./data/agent_data)

    Returns:
        List of trading records, each containing:
        - date: Trading date
        - positions: Portfolio positions
        - action: Trade action taken
        - reasoning: Agent's reasoning (if available from logs)
    """
    if base_path is None:
        project_root = Path(__file__).resolve().parents[1]
        base_path = project_root / "data" / "agent_data"
    else:
        base_path = Path(base_path)

    position_file = base_path / signature / "position" / "position.jsonl"

    if not position_file.exists():
        return []

    # Get dates to search
    current_dt = datetime.strptime(current_date, "%Y-%m-%d")
    target_dates = []
    check_dt = current_dt - timedelta(days=1)

    # Collect lookback_days worth of trading days (skip weekends)
    while len(target_dates) < lookback_days:
        # Skip weekends
        if check_dt.weekday() < 5:
            target_dates.append(check_dt.strftime("%Y-%m-%d"))
        check_dt -= timedelta(days=1)

        # Safety check - don't go back more than 30 calendar days
        if (current_dt - check_dt).days > 30:
            break

    target_dates_set = set(target_dates)

    # Read position history
    history = []
    daily_records = defaultdict(list)

    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                record_date = record.get("date")

                if record_date in target_dates_set:
                    daily_records[record_date].append(record)
            except Exception:
                continue

    # For each date, get the last action (highest ID)
    for date in sorted(target_dates, reverse=True):
        if date in daily_records:
            # Get record with max ID for that day
            day_records = daily_records[date]
            last_record = max(day_records, key=lambda x: x.get("id", 0))

            history.append({
                "date": date,
                "positions": last_record.get("positions", {}),
                "action": last_record.get("this_action", {}),
            })

    return history


def get_recent_logs_summary(
    signature: str,
    current_date: str,
    lookback_days: int = 3,
    base_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get summaries of recent trading session logs.

    Args:
        signature: Model signature/name
        current_date: Current trading date (YYYY-MM-DD)
        lookback_days: Number of previous days to retrieve
        base_path: Base path to agent data

    Returns:
        List of log summaries with date and key decisions
    """
    if base_path is None:
        project_root = Path(__file__).resolve().parents[1]
        base_path = project_root / "data" / "agent_data"
    else:
        base_path = Path(base_path)

    log_base = base_path / signature / "log"

    if not log_base.exists():
        return []

    # Get target dates
    current_dt = datetime.strptime(current_date, "%Y-%m-%d")
    target_dates = []
    check_dt = current_dt - timedelta(days=1)

    while len(target_dates) < lookback_days:
        if check_dt.weekday() < 5:
            target_dates.append(check_dt.strftime("%Y-%m-%d"))
        check_dt -= timedelta(days=1)

        if (current_dt - check_dt).days > 30:
            break

    summaries = []

    for date in sorted(target_dates, reverse=True):
        log_file = log_base / date / "log.jsonl"

        if not log_file.exists():
            continue

        # Extract key reasoning from logs
        assistant_messages = []

        with log_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    log_entry = json.loads(line)
                    messages = log_entry.get("new_messages", [])

                    if isinstance(messages, dict):
                        messages = [messages]

                    for msg in messages:
                        if msg.get("role") == "assistant":
                            content = msg.get("content", "")
                            # Only keep substantial reasoning (not just tool calls)
                            if len(content) > 50:
                                assistant_messages.append(content)
                except Exception:
                    continue

        if assistant_messages:
            # Get first reasoning message (initial analysis)
            summaries.append({
                "date": date,
                "reasoning_summary": assistant_messages[0][:500] if assistant_messages else ""
            })

    return summaries


def calculate_portfolio_metrics(
    positions: Dict[str, float],
    current_prices: Dict[str, float]
) -> Dict[str, Any]:
    """
    Calculate current portfolio metrics.

    Args:
        positions: Current positions {symbol: shares, CASH: cash}
        current_prices: Current prices {symbol_price: price}

    Returns:
        Dict with portfolio metrics:
        - total_value: Total portfolio value
        - cash_allocation: % in cash
        - position_count: Number of holdings
        - top_holdings: List of top 5 positions by value
        - concentration: % of portfolio in top holding
    """
    cash = positions.get("CASH", 0.0)
    holdings_value = 0.0
    position_values = {}

    for symbol, shares in positions.items():
        if symbol == "CASH" or shares == 0:
            continue

        price_key = f"{symbol}_price"
        price = current_prices.get(price_key)

        if price is not None:
            value = shares * price
            holdings_value += value
            position_values[symbol] = value

    total_value = cash + holdings_value

    # Sort positions by value
    sorted_positions = sorted(
        position_values.items(),
        key=lambda x: x[1],
        reverse=True
    )

    metrics = {
        "total_value": round(total_value, 2),
        "cash": round(cash, 2),
        "holdings_value": round(holdings_value, 2),
        "cash_allocation_pct": round(cash / total_value * 100, 2) if total_value > 0 else 0,
        "position_count": len([v for v in position_values.values() if v > 0]),
        "top_holdings": [
            {
                "symbol": sym,
                "value": round(val, 2),
                "pct": round(val / total_value * 100, 2) if total_value > 0 else 0
            }
            for sym, val in sorted_positions[:5]
        ],
        "concentration_pct": round(sorted_positions[0][1] / total_value * 100, 2) if sorted_positions and total_value > 0 else 0
    }

    return metrics


def calculate_performance_stats(
    signature: str,
    current_date: str,
    initial_cash: float = 10000.0,
    base_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate performance statistics from inception.

    Args:
        signature: Model signature
        current_date: Current date
        initial_cash: Initial portfolio value
        base_path: Base path to agent data

    Returns:
        Dict with performance stats:
        - total_return_pct: Total return %
        - num_trades: Total number of trades
        - winning_days: Days with positive return
        - losing_days: Days with negative return
    """
    if base_path is None:
        project_root = Path(__file__).resolve().parents[1]
        base_path = project_root / "data" / "agent_data"
    else:
        base_path = Path(base_path)

    position_file = base_path / signature / "position" / "position.jsonl"

    if not position_file.exists():
        return {
            "total_return_pct": 0.0,
            "num_trades": 0,
            "winning_days": 0,
            "losing_days": 0
        }

    # Read all positions
    all_positions = []
    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                all_positions.append(record)
            except Exception:
                continue

    if not all_positions:
        return {
            "total_return_pct": 0.0,
            "num_trades": 0,
            "winning_days": 0,
            "losing_days": 0
        }

    # Count trades (exclude no_trade actions)
    num_trades = sum(
        1 for p in all_positions
        if p.get("this_action", {}).get("action") not in ["no_trade", None, ""]
    )

    # Get latest position value (simplified - would need current prices for accuracy)
    latest_record = max(all_positions, key=lambda x: (x.get("date", ""), x.get("id", 0)))
    current_cash = latest_record.get("positions", {}).get("CASH", initial_cash)

    # Simple return calculation (actual calculation would need to value holdings)
    total_return_pct = ((current_cash - initial_cash) / initial_cash) * 100

    return {
        "total_return_pct": round(total_return_pct, 2),
        "num_trades": num_trades,
        "days_traded": len(set(p.get("date") for p in all_positions)),
    }


def build_memory_context(
    signature: str,
    current_date: str,
    current_positions: Dict[str, float],
    current_prices: Dict[str, float],
    lookback_days: int = 5,
    initial_cash: float = 10000.0
) -> str:
    """
    Build comprehensive memory context for the agent.

    Args:
        signature: Model signature
        current_date: Current trading date
        current_positions: Current portfolio positions
        current_prices: Current market prices
        lookback_days: Days of history to include
        initial_cash: Initial portfolio value

    Returns:
        Formatted string with memory context
    """
    # Get trading history
    history = get_trading_history(signature, current_date, lookback_days)

    # Get recent reasoning
    log_summaries = get_recent_logs_summary(signature, current_date, min(3, lookback_days))

    # Calculate portfolio metrics
    portfolio_metrics = calculate_portfolio_metrics(current_positions, current_prices)

    # Calculate performance stats
    performance = calculate_performance_stats(signature, current_date, initial_cash)

    # Build context string
    context_parts = []

    # Performance summary
    context_parts.append("=== PORTFOLIO PERFORMANCE ===")
    context_parts.append(f"Total Return: {performance['total_return_pct']}%")
    context_parts.append(f"Total Trades: {performance['num_trades']}")
    context_parts.append(f"Days Traded: {performance['days_traded']}")
    context_parts.append("")

    # Current portfolio state
    context_parts.append("=== CURRENT PORTFOLIO ===")
    context_parts.append(f"Total Value: ${portfolio_metrics['total_value']:,.2f}")
    context_parts.append(f"Cash: ${portfolio_metrics['cash']:,.2f} ({portfolio_metrics['cash_allocation_pct']}%)")
    context_parts.append(f"Holdings Value: ${portfolio_metrics['holdings_value']:,.2f}")
    context_parts.append(f"Number of Positions: {portfolio_metrics['position_count']}")

    if portfolio_metrics['top_holdings']:
        context_parts.append("\nTop Holdings:")
        for holding in portfolio_metrics['top_holdings']:
            context_parts.append(f"  - {holding['symbol']}: ${holding['value']:,.2f} ({holding['pct']}%)")
    context_parts.append("")

    # Recent trading history
    if history:
        context_parts.append("=== RECENT TRADING HISTORY ===")
        for record in history[:5]:  # Last 5 days
            action = record['action']
            action_type = action.get('action', 'no_trade')

            if action_type == 'buy':
                context_parts.append(f"{record['date']}: BOUGHT {action.get('amount')} shares of {action.get('symbol')}")
            elif action_type == 'sell':
                context_parts.append(f"{record['date']}: SOLD {action.get('amount')} shares of {action.get('symbol')}")
            else:
                context_parts.append(f"{record['date']}: No trades")
        context_parts.append("")

    # Recent reasoning (only most recent)
    if log_summaries:
        context_parts.append("=== RECENT ANALYSIS ===")
        latest_summary = log_summaries[0]
        context_parts.append(f"Previous session ({latest_summary['date']}):")
        context_parts.append(latest_summary['reasoning_summary'])
        context_parts.append("")

    return "\n".join(context_parts)


if __name__ == "__main__":
    # Test the memory system
    from tools.general_tools import get_config_value

    signature = get_config_value("SIGNATURE") or "claude-3.7-sonnet"
    today_date = get_config_value("TODAY_DATE") or "2025-10-15"

    context = build_memory_context(
        signature=signature,
        current_date=today_date,
        current_positions={"AAPL": 10, "MSFT": 5, "CASH": 5000.0},
        current_prices={"AAPL_price": 180.0, "MSFT_price": 380.0},
        lookback_days=5
    )

    print(context)

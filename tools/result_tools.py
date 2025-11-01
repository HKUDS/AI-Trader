import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add project root directory to Python path to allow running this file from subdirectories
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.general_tools import get_config_value
from tools.price_tools import (all_nasdaq_100_symbols, get_latest_position,
                               get_open_prices, get_today_init_position,
                               get_yesterday_date,
                               get_yesterday_open_and_close_price)


def get_currency_symbol(market: str = "us") -> str:
    """Get currency symbol based on market type"""
    return "¥" if market == "cn" else "$"


def calculate_portfolio_value(
    positions: Dict[str, float], prices: Dict[str, Optional[float]], cash: float = 0.0
) -> float:
    """
    Calculate total portfolio value

    Args:
        positions: Position dictionary in format {symbol: shares}
        prices: Price dictionary in format {symbol_price: price}
        cash: Cash balance

    Returns:
        Total portfolio value
    """
    total_value = cash

    for symbol, shares in positions.items():
        if symbol == "CASH":
            continue
        price_key = f"{symbol}_price"
        price = prices.get(price_key)
        if price is not None and shares > 0:
            total_value += shares * price

    return total_value


def get_available_date_range(signature: str) -> Tuple[str, str]:
    """
    Get available data date range

    Args:
        signature: Model name
    
    Returns:
        Tuple of (earliest date, latest date) in YYYY-MM-DD format
    """
    from tools.general_tools import get_config_value

    base_dir = Path(__file__).resolve().parents[1]

    # Get log_path from config, default to "agent_data" for backward compatibility
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]  # Remove "./data/" prefix

    position_file = base_dir / "data" / log_path / signature / "position" / "position.jsonl"

    if not position_file.exists():
        return "", ""

    dates = []

    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                date = doc.get("date")
                if date:
                    dates.append(date)
            except Exception:
                continue

    if not dates:
        return "", ""

    dates.sort()
    return dates[0], dates[-1]


def get_daily_portfolio_values(
    modelname: str, start_date: Optional[str] = None, end_date: Optional[str] = None, market: str = "us"
) -> Dict[str, float]:
    """
    Get daily portfolio values

    Args:
        signature: Model name
        start_date: Start date in YYYY-MM-DD format, uses earliest date if None
        end_date: End date in YYYY-MM-DD format, uses latest date if None
        market: Market type, "us" for US stocks or "cn" for A-shares

    Returns:
        Dictionary of daily portfolio values in format {date: portfolio_value}
    """
    from tools.general_tools import get_config_value
    from tools.price_tools import (all_nasdaq_100_symbols, all_sse_50_symbols,
                                   get_merged_file_path)

    base_dir = Path(__file__).resolve().parents[1]

    # Get log_path from config, default to "agent_data" for backward compatibility
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]  # Remove "./data/" prefix

    position_file = base_dir / "data" / log_path / signature / "position" / "position.jsonl"
    merged_file = get_merged_file_path(market)

    if not position_file.exists() or not merged_file.exists():
        return {}

    # Get available date range if not specified
    if start_date is None or end_date is None:
        earliest_date, latest_date = get_available_date_range(signature)
        if not earliest_date or not latest_date:
            return {}

        if start_date is None:
            start_date = earliest_date
        if end_date is None:
            end_date = latest_date

    # Read position data
    position_data = []
    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                position_data.append(doc)
            except Exception:
                continue

    # Read price data
    price_data = {}
    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                meta = doc.get("Meta Data", {})
                symbol = meta.get("2. Symbol")
                if symbol:
                    # 查找所有以 "Time Series" 开头的键
                    series = None
                    for key, value in doc.items():
                        if key.startswith("Time Series"):
                            series = value
                            break
                    price_data[symbol] = series if series else {}
            except Exception:
                continue

    # Select stock symbols based on market
    stock_symbols = all_sse_50_symbols if market == "cn" else all_nasdaq_100_symbols

    # Calculate daily portfolio values
    daily_values = {}

    # Group position data by date
    positions_by_date = {}
    for record in position_data:
        date = record.get("date")
        if date:
            if date not in positions_by_date:
                positions_by_date[date] = []
            positions_by_date[date].append(record)

    # For each date, sort records by id and take latest position
    for date, records in positions_by_date.items():
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        # Sort by id and take latest position
        latest_record = max(records, key=lambda x: x.get("id", 0))
        positions = latest_record.get("positions", {})

        # Get daily prices
        daily_prices = {}
        for symbol in stock_symbols:
            if symbol in price_data:
                symbol_prices = price_data[symbol]
                if date in symbol_prices:
                    price_info = symbol_prices[date]
                    buy_price = price_info.get("1. buy price")
                    sell_price = price_info.get("4. sell price")
                    # Use closing (sell) price to calculate value
                    if sell_price is not None:
                        daily_prices[f"{symbol}_price"] = float(sell_price)

        # Calculate portfolio value
        cash = positions.get("CASH", 0.0)
        portfolio_value = calculate_portfolio_value(positions, daily_prices, cash)
        daily_values[date] = portfolio_value

    return daily_values


def calculate_daily_returns(portfolio_values: Dict[str, float]) -> List[float]:
    """
    Calculate daily returns

    Args:
        portfolio_values: Daily portfolio value dictionary

    Returns:
        List of daily returns
    """
    if len(portfolio_values) < 2:
        return []

    # Sort by date
    sorted_dates = sorted(portfolio_values.keys())
    returns = []

    for i in range(1, len(sorted_dates)):
        prev_date = sorted_dates[i - 1]
        curr_date = sorted_dates[i]

        prev_value = portfolio_values[prev_date]
        curr_value = portfolio_values[curr_date]

        if prev_value > 0:
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(daily_return)

    return returns


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe ratio

    Args:
        returns: List of returns
        risk_free_rate: Risk-free rate (annualized)

    Returns:
        Sharpe ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)

    # Calculate annualized return and volatility
    mean_return = np.mean(returns_array)
    std_return = np.std(returns_array, ddof=1)

    # Assume 252 trading days per year
    annualized_return = mean_return * 252
    annualized_volatility = std_return * np.sqrt(252)

    if annualized_volatility == 0:
        return 0.0

    # Calculate Sharpe ratio
    sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility

    return sharpe_ratio


def calculate_max_drawdown(portfolio_values: Dict[str, float]) -> Tuple[float, str, str]:
    """
    Calculate maximum drawdown

    Args:
        portfolio_values: Daily portfolio value dictionary

    Returns:
        Tuple of (maximum drawdown percentage, drawdown start date, drawdown end date)
    """
    if not portfolio_values:
        return 0.0, "", ""

    # Sort by date
    sorted_dates = sorted(portfolio_values.keys())
    values = [portfolio_values[date] for date in sorted_dates]

    max_drawdown = 0.0
    peak_value = values[0]
    peak_date = sorted_dates[0]
    drawdown_start_date = ""
    drawdown_end_date = ""

    for i, (date, value) in enumerate(zip(sorted_dates, values)):
        if value > peak_value:
            peak_value = value
            peak_date = date

        drawdown = (peak_value - value) / peak_value
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            drawdown_start_date = peak_date
            drawdown_end_date = date

    return max_drawdown, drawdown_start_date, drawdown_end_date


def calculate_cumulative_return(portfolio_values: Dict[str, float]) -> float:
    """
    Calculate cumulative return

    Args:
        portfolio_values: Daily portfolio value dictionary

    Returns:
        Cumulative return
    """
    if not portfolio_values:
        return 0.0

    # Sort by date
    sorted_dates = sorted(portfolio_values.keys())
    initial_value = portfolio_values[sorted_dates[0]]
    final_value = portfolio_values[sorted_dates[-1]]

    if initial_value == 0:
        return 0.0

    cumulative_return = (final_value - initial_value) / initial_value
    return cumulative_return


def calculate_annualized_return(portfolio_values: Dict[str, float]) -> float:
    """
    Calculate annualized return

    Args:
        portfolio_values: Daily portfolio value dictionary

    Returns:
        Annualized return
    """
    if not portfolio_values:
        return 0.0

    # Sort by date
    sorted_dates = sorted(portfolio_values.keys())
    initial_value = portfolio_values[sorted_dates[0]]
    final_value = portfolio_values[sorted_dates[-1]]

    if initial_value == 0:
        return 0.0

    # Calculate investment days
    start_date = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    end_date = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")
    days = (end_date - start_date).days

    if days == 0:
        return 0.0

    # Calculate annualized return
    total_return = (final_value - initial_value) / initial_value
    annualized_return = (1 + total_return) ** (365 / days) - 1

    return annualized_return


def calculate_volatility(returns: List[float]) -> float:
    """
    Calculate annualized volatility

    Args:
        returns: List of returns

    Returns:
        Annualized volatility
    """
    if not returns or len(returns) < 2:
        return 0.0

    returns_array = np.array(returns)
    daily_volatility = np.std(returns_array, ddof=1)

    # Annualize volatility (assuming 252 trading days)
    annualized_volatility = daily_volatility * np.sqrt(252)

    return annualized_volatility


def calculate_win_rate(returns: List[float]) -> float:
    """
    Calculate win rate

    Args:
        returns: List of returns

    Returns:
        Win rate (percentage of positive return days)
    """
    if not returns:
        return 0.0

    positive_days = sum(1 for r in returns if r > 0)
    total_days = len(returns)

    return positive_days / total_days


def calculate_profit_loss_ratio(returns: List[float]) -> float:
    """
    Calculate profit/loss ratio

    Args:
        returns: List of returns

    Returns:
        Profit/loss ratio (average profit / average loss)
    """
    if not returns:
        return 0.0

    positive_returns = [r for r in returns if r > 0]
    negative_returns = [r for r in returns if r < 0]

    if not positive_returns or not negative_returns:
        return 0.0

    avg_profit = np.mean(positive_returns)
    avg_loss = abs(np.mean(negative_returns))

    if avg_loss == 0:
        return 0.0

    return avg_profit / avg_loss


def calculate_all_metrics(
    modelname: str, start_date: Optional[str] = None, end_date: Optional[str] = None, market: str = "us"
) -> Dict[str, any]:
    """
    Calculate all performance metrics

    Args:
        signature: Model name
        start_date: Start date in YYYY-MM-DD format, uses earliest date if None
        end_date: End date in YYYY-MM-DD format, uses latest date if None
        market: Market type, "us" for US stocks or "cn" for A-shares

    Returns:
        Dictionary containing all metrics
    """
    # Get available date range if not specified
    if start_date is None or end_date is None:
        earliest_date, latest_date = get_available_date_range(signature)
        if not earliest_date or not latest_date:
            return {
                "error": "Unable to get available data date range",
                "portfolio_values": {},
                "daily_returns": [],
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_start": "",
                "max_drawdown_end": "",
                "cumulative_return": 0.0,
                "annualized_return": 0.0,
                "volatility": 0.0,
                "win_rate": 0.0,
                "profit_loss_ratio": 0.0,
                "total_trading_days": 0,
                "start_date": "",
                "end_date": "",
            }

        if start_date is None:
            start_date = earliest_date
        if end_date is None:
            end_date = latest_date

    # 获取每日投资组合价值
    portfolio_values = get_daily_portfolio_values(modelname, start_date, end_date, market)

    if not portfolio_values:
        return {
            "error": "Unable to get portfolio data",
            "portfolio_values": {},
            "daily_returns": [],
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_start": "",
            "max_drawdown_end": "",
            "cumulative_return": 0.0,
            "annualized_return": 0.0,
            "volatility": 0.0,
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "total_trading_days": 0,
            "start_date": "",
            "end_date": "",
        }

    # Calculate daily returns
    daily_returns = calculate_daily_returns(portfolio_values)

    # Calculate various metrics
    sharpe_ratio = calculate_sharpe_ratio(daily_returns)
    max_drawdown, drawdown_start, drawdown_end = calculate_max_drawdown(portfolio_values)
    cumulative_return = calculate_cumulative_return(portfolio_values)
    annualized_return = calculate_annualized_return(portfolio_values)
    volatility = calculate_volatility(daily_returns)
    win_rate = calculate_win_rate(daily_returns)
    profit_loss_ratio = calculate_profit_loss_ratio(daily_returns)

    # Get date range
    sorted_dates = sorted(portfolio_values.keys())
    start_date_actual = sorted_dates[0] if sorted_dates else ""
    end_date_actual = sorted_dates[-1] if sorted_dates else ""

    return {
        "portfolio_values": portfolio_values,
        "daily_returns": daily_returns,
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown": round(max_drawdown, 4),
        "max_drawdown_start": drawdown_start,
        "max_drawdown_end": drawdown_end,
        "cumulative_return": round(cumulative_return, 4),
        "annualized_return": round(annualized_return, 4),
        "volatility": round(volatility, 4),
        "win_rate": round(win_rate, 4),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "total_trading_days": len(portfolio_values),
        "start_date": start_date_actual,
        "end_date": end_date_actual,
    }


def print_performance_report(metrics: Dict[str, any], market: str = "us") -> None:
    """
    Print performance report

    Args:
        metrics: Dictionary containing all metrics
        market: Market type ("us" or "cn")
    """
    currency_symbol = get_currency_symbol(market)

    print("=" * 60)
    print("Portfolio Performance Report")
    print("=" * 60)

    if "error" in metrics:
        print(f"Error: {metrics['error']}")
        return

    print(f"Analysis Period: {metrics['start_date']} to {metrics['end_date']}")
    print(f"Trading Days: {metrics['total_trading_days']}")
    print()

    print("Return Metrics:")
    print(f"  Cumulative Return: {metrics['cumulative_return']:.2%}")
    print(f"  Annualized Return: {metrics['annualized_return']:.2%}")
    print(f"  Annualized Volatility: {metrics['volatility']:.2%}")
    print()

    print("Risk Metrics:")
    print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.4f}")
    print(f"  Maximum Drawdown: {metrics['max_drawdown']:.2%}")
    if metrics["max_drawdown_start"] and metrics["max_drawdown_end"]:
        print(f"  Drawdown Period: {metrics['max_drawdown_start']} to {metrics['max_drawdown_end']}")
    print()

    print("Trading Statistics:")
    print(f"  Win Rate: {metrics['win_rate']:.2%}")
    print(f"  Profit/Loss Ratio: {metrics['profit_loss_ratio']:.4f}")
    print()

    # Show portfolio value changes
    portfolio_values = metrics["portfolio_values"]
    if portfolio_values:
        sorted_dates = sorted(portfolio_values.keys())
        initial_value = portfolio_values[sorted_dates[0]]
        final_value = portfolio_values[sorted_dates[-1]]

        print("Portfolio Value:")
        print(f"  Initial Value: {currency_symbol}{initial_value:,.2f}")
        print(f"  Final Value: {currency_symbol}{final_value:,.2f}")
        print(f"  Value Change: {currency_symbol}{final_value - initial_value:,.2f}")


def get_next_id(filepath: Path) -> int:
    """
    Get next ID number

    Args:
        filepath: JSONL file path

    Returns:
        Next ID number
    """
    if not filepath.exists():
        return 0

    max_id = -1
    with filepath.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                current_id = data.get("id", -1)
                if current_id > max_id:
                    max_id = current_id
            except Exception:
                continue

    return max_id + 1


def save_metrics_to_jsonl(metrics: Dict[str, any], signature: str, output_dir: Optional[str] = None) -> str:
    """
    Incrementally save metrics to JSONL format

    Args:
        metrics: Dictionary containing all metrics
        signature: Model name
        output_dir: Output directory, defaults to data/agent_data/{signature}/metrics/
    
    Returns:
        Path to saved file
    """
    from tools.general_tools import get_config_value

    base_dir = Path(__file__).resolve().parents[1]

    if output_dir is None:
        # Get log_path from config, default to "agent_data" for backward compatibility
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        output_dir = base_dir / "data" / log_path / signature / "metrics"
    else:
        output_dir = Path(output_dir)

    # Create directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use fixed filename
    filename = "performance_metrics.jsonl"
    filepath = output_dir / filename

    # Get next ID number
    next_id = get_next_id(filepath)

    # Prepare data to save
    save_data = {
        "id": next_id,
        "timestamp": datetime.now().isoformat(),
        "model_name": signature,
        "analysis_period": {
            "start_date": metrics.get("start_date", ""),
            "end_date": metrics.get("end_date", ""),
            "total_trading_days": metrics.get("total_trading_days", 0),
        },
        "performance_metrics": {
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "max_drawdown_period": {
                "start_date": metrics.get("max_drawdown_start", ""),
                "end_date": metrics.get("max_drawdown_end", ""),
            },
            "cumulative_return": metrics.get("cumulative_return", 0.0),
            "annualized_return": metrics.get("annualized_return", 0.0),
            "volatility": metrics.get("volatility", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "profit_loss_ratio": metrics.get("profit_loss_ratio", 0.0),
        },
        "portfolio_summary": {},
    }

    # Add portfolio value summary
    portfolio_values = metrics.get("portfolio_values", {})
    if portfolio_values:
        sorted_dates = sorted(portfolio_values.keys())
        initial_value = portfolio_values[sorted_dates[0]]
        final_value = portfolio_values[sorted_dates[-1]]

        save_data["portfolio_summary"] = {
            "initial_value": initial_value,
            "final_value": final_value,
            "value_change": final_value - initial_value,
            "value_change_percent": ((final_value - initial_value) / initial_value) if initial_value > 0 else 0.0,
        }

    # Incrementally save to JSONL file (append mode)
    with filepath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(save_data, ensure_ascii=False) + "\n")

    return str(filepath)


def get_latest_metrics(signature: str, output_dir: Optional[str] = None) -> Optional[Dict[str, any]]:
    """
    Get latest performance metrics record

    Args:
        signature: Model name
        output_dir: Output directory, defaults to data/agent_data/{signature}/metrics/
    
    Returns:
        Latest metrics record, or None if no records exist
    """
    from tools.general_tools import get_config_value

    base_dir = Path(__file__).resolve().parents[1]

    if output_dir is None:
        # Get log_path from config, default to "agent_data" for backward compatibility
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        output_dir = base_dir / "data" / log_path / signature / "metrics"
    else:
        output_dir = Path(output_dir)

    filepath = output_dir / "performance_metrics.jsonl"

    if not filepath.exists():
        return None

    latest_record = None
    max_id = -1

    with filepath.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                current_id = data.get("id", -1)
                if current_id > max_id:
                    max_id = current_id
                    latest_record = data
            except Exception:
                continue

    return latest_record


def get_metrics_history(
    modelname: str, output_dir: Optional[str] = None, limit: Optional[int] = None
) -> List[Dict[str, any]]:
    """
    Get performance metrics history

    Args:
        signature: Model name
        output_dir: Output directory, defaults to data/agent_data/{signature}/metrics/
        limit: Limit number of records returned, None returns all records

    Returns:
        List of metrics records, sorted by ID
    """
    from tools.general_tools import get_config_value

    base_dir = Path(__file__).resolve().parents[1]

    if output_dir is None:
        # Get log_path from config, default to "agent_data" for backward compatibility
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        output_dir = base_dir / "data" / log_path / signature / "metrics"
    else:
        output_dir = Path(output_dir)

    filepath = output_dir / "performance_metrics.jsonl"

    if not filepath.exists():
        return []

    records = []

    with filepath.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                records.append(data)
            except Exception:
                continue

    # Sort by ID
    records.sort(key=lambda x: x.get("id", 0))

    # Return latest records if limit specified
    if limit is not None and limit > 0:
        records = records[-limit:]

    return records


def print_metrics_summary(signature: str, output_dir: Optional[str] = None) -> None:
    """
    Print performance metrics summary

    Args:
        signature: Model name
        output_dir: Output directory
    """
    print(f"📊 Model '{signature}' Performance Metrics Summary")
    print("=" * 60)

    # Get history records
    history = get_metrics_history(signature, output_dir)
    
    if not history:
        print("❌ No history records found")
        return

    print(f"📈 Total Records: {len(history)}")

    # Show latest record
    latest = history[-1]
    print(f"🕒 Latest Record (ID: {latest['id']}):")
    print(f"   Time: {latest['timestamp']}")
    print(f"   Analysis Period: {latest['analysis_period']['start_date']} to {latest['analysis_period']['end_date']}")
    print(f"   Trading Days: {latest['analysis_period']['total_trading_days']}")

    metrics = latest["performance_metrics"]
    print(f"   Sharpe Ratio: {metrics['sharpe_ratio']}")
    print(f"   Maximum Drawdown: {metrics['max_drawdown']:.2%}")
    print(f"   Cumulative Return: {metrics['cumulative_return']:.2%}")
    print(f"   Annualized Return: {metrics['annualized_return']:.2%}")

    # Show trends (if multiple records exist)
    if len(history) > 1:
        print(f"\n📊 Trend Analysis (Last {min(5, len(history))} Records):")

        recent_records = history[-5:] if len(history) >= 5 else history

        print("ID  | Time                | Cum Ret   | Ann Ret   | Sharpe")
        print("-" * 70)

        for record in recent_records:
            metrics = record["performance_metrics"]
            print(
                f"{record['id']:2d} | {metrics['cumulative_return']:8.2%} | {metrics['annualized_return']:8.2%} | {metrics['sharpe_ratio']:8.4f}"
            )


def calculate_and_save_metrics(
    modelname: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_dir: Optional[str] = None,
    print_report: bool = True,
    market: str = "us",
) -> Dict[str, any]:
    """
    Entry function to calculate all metrics and save in JSONL format

    Args:
        signature: Model name (SIGNATURE)
        start_date: Start date in YYYY-MM-DD format, uses earliest date if None
        end_date: End date in YYYY-MM-DD format, uses latest date if None
        output_dir: Output directory, defaults to data/agent_data/{signature}/metrics/
        print_report: Whether to print report
        market: Market type ("us" or "cn")

    Returns:
        Dictionary containing all metrics and saved file path
    """
    print(f"Analyzing model: {signature}")
    
    # Show date range to be used if not specified
    if start_date is None or end_date is None:
        earliest_date, latest_date = get_available_date_range(signature)
        if earliest_date and latest_date:
            if start_date is None:
                start_date = earliest_date
                print(f"Using default start date: {start_date}")
            if end_date is None:
                end_date = latest_date
                print(f"Using default end date: {end_date}")
        else:
            print("❌ Unable to get available data date range")

    # Calculate all metrics
    metrics = calculate_all_metrics(signature, start_date, end_date, market)

    if "error" in metrics:
        print(f"Error: {metrics['error']}")
        return metrics

    # Save in JSONL format
    try:
        saved_file = save_metrics_to_jsonl(metrics, signature, output_dir)
        print(f"Metrics saved to: {saved_file}")
        metrics["saved_file"] = saved_file

        # Get ID of just saved record
        latest_record = get_latest_metrics(signature, output_dir)
        if latest_record:
            metrics["record_id"] = latest_record["id"]
            print(f"Record ID: {latest_record['id']}")
    except Exception as e:
        print(f"Error saving file: {e}")
        metrics["save_error"] = str(e)

    # Print report
    if print_report:
        print_performance_report(metrics, market=market)

    return metrics


if __name__ == "__main__":
    # Test code
    # 测试代码
    signature = get_config_value("SIGNATURE")
    if signature is None:
        print("错误: 未设置 SIGNATURE 环境变量")
        print("请设置环境变量 SIGNATURE，例如: export SIGNATURE=claude-3.7-sonnet")
        sys.exit(1)

    # Get market type from config, default to "us"
    market = get_config_value("MARKET", "us")

    # 使用入口函数计算和保存指标
    result = calculate_and_save_metrics(signature, market=market)
#     result = calculate_and_save_metrics(signature)

#!/usr/bin/env python3
"""
Calculate trading performance metrics from position data.

Metrics:
- CR (Cumulative Return): Total return percentage
- SR (Sortino Ratio): Risk-adjusted return using downside deviation
- Vol (Volatility): Annualized standard deviation of returns
- MDD (Maximum Drawdown): Largest peak-to-trough decline
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import argparse


def load_position_data(position_file):
    """Load position data from JSONL file."""
    positions = []
    with open(position_file, 'r') as f:
        for line in f:
            positions.append(json.loads(line))
    return positions


def load_price_data(price_file):
    """Load price data from JSON file."""
    with open(price_file, 'r') as f:
        data = json.load(f)
    return data


def get_price_at_date(price_data, symbol, date_str, is_crypto=False):
    """
    Get the price for a symbol at a specific date/datetime.

    Args:
        price_data: Dict of symbol -> price data
        symbol: Stock/crypto symbol
        date_str: Date string in format 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
        is_crypto: Whether this is crypto data (uses 'sell price' field)

    Returns:
        Price as float, or None if not found
    """
    if symbol not in price_data:
        return None

    symbol_data = price_data[symbol]

    # Determine the time series key (could be hourly, daily, etc.)
    time_series_key = None
    for key in ['Time Series (60min)', 'Time Series (Daily)', 'Time Series (Hourly)']:
        if key in symbol_data:
            time_series_key = key
            break

    if not time_series_key:
        return None

    time_series = symbol_data[time_series_key]

    # For hourly data, try exact timestamp match first
    if 'min' in time_series_key or 'Hourly' in time_series_key:
        if date_str in time_series:
            price_str = time_series[date_str].get('4. sell price' if is_crypto else '4. close',
                                                    time_series[date_str].get('4. close'))
            return float(price_str) if price_str else None

        # Try to find the closest previous timestamp
        available_dates = sorted([d for d in time_series.keys() if d <= date_str], reverse=True)
        if available_dates:
            closest_date = available_dates[0]
            price_str = time_series[closest_date].get('4. sell price' if is_crypto else '4. close',
                                                        time_series[closest_date].get('4. close'))
            return float(price_str) if price_str else None
    else:
        # For daily data, extract just the date part
        date_only = date_str.split(' ')[0]

        # Try exact match first
        if date_only in time_series:
            price_str = time_series[date_only].get('4. sell price' if is_crypto else '4. close',
                                                     time_series[date_only].get('4. close'))
            return float(price_str) if price_str else None

        # Try to find the closest previous date
        available_dates = sorted([d for d in time_series.keys() if d <= date_only], reverse=True)
        if available_dates:
            closest_date = available_dates[0]
            price_str = time_series[closest_date].get('4. sell price' if is_crypto else '4. close',
                                                        time_series[closest_date].get('4. close'))
            return float(price_str) if price_str else None

    return None


def load_all_price_files(data_dir, is_crypto=False, is_astock=False):
    """Load all price files from a directory."""
    price_data = {}

    if is_crypto:
        # For crypto, data_dir should already point to the crypto folder
        price_dir = Path(data_dir) / 'coin'
    elif is_astock:
        # A-stock data is in A_stock_data subdirectory
        price_dir = Path(data_dir) / 'A_stock_data'
        if not price_dir.exists():
            # Fallback to parent directory
            price_dir = Path(data_dir)
    else:
        price_dir = Path(data_dir)

    for price_file in price_dir.glob('daily_prices_*.json'):
        # Extract symbol and normalize it
        symbol = price_file.stem.replace('daily_prices_', '')

        # For A-stock, remove the extra 'H' suffix (e.g., .SHH -> .SH)
        if is_astock and symbol.endswith('HH'):
            symbol = symbol[:-1]  # Remove one 'H'

        try:
            with open(price_file, 'r') as f:
                data = json.load(f)
                price_data[symbol] = data

                # Also store with original symbol for compatibility
                original_symbol = price_file.stem.replace('daily_prices_', '')
                if original_symbol != symbol:
                    price_data[original_symbol] = data

                # For crypto, also store with USDT suffix for compatibility
                if is_crypto:
                    usdt_symbol = f"{symbol}-USDT"
                    price_data[usdt_symbol] = data

        except Exception as e:
            print(f"Warning: Could not load {price_file}: {e}")

    return price_data


def calculate_portfolio_values(positions, price_data, is_crypto=False, verbose=True):
    """
    Calculate portfolio value at each timestamp.

    Returns:
        DataFrame with columns: date, cash, stock_value, total_value
    """
    portfolio_values = []
    missing_prices = set()

    for entry in positions:
        date = entry['date']
        pos = entry['positions']

        cash = pos.get('CASH', 0)
        stock_value = 0

        # Calculate value of all stock holdings
        for symbol, amount in pos.items():
            if symbol == 'CASH' or amount == 0:
                continue

            price = get_price_at_date(price_data, symbol, date, is_crypto)
            if price is not None:
                stock_value += amount * price
            else:
                if verbose and (symbol, date) not in missing_prices:
                    print(f"Warning: No price found for {symbol} on {date}")
                    missing_prices.add((symbol, date))

        total_value = cash + stock_value

        portfolio_values.append({
            'date': date,
            'cash': cash,
            'stock_value': stock_value,
            'total_value': total_value
        })

    df = pd.DataFrame(portfolio_values)
    df['date'] = pd.to_datetime(df['date'])

    if not verbose and missing_prices:
        print(f"Warning: {len(missing_prices)} missing price entries (use --verbose to see details)")

    return df


def calculate_metrics(portfolio_df, periods_per_year=252, risk_free_rate=0.0):
    """
    Calculate performance metrics.

    Args:
        portfolio_df: DataFrame with total_value column
        periods_per_year: Number of trading periods per year (252 for daily, ~252*6.5 for hourly)
        risk_free_rate: Annual risk-free rate (default 0.0)

    Returns:
        Dict with metrics
    """
    values = portfolio_df['total_value'].values

    # Calculate returns
    returns = np.diff(values) / values[:-1]

    # Cumulative Return
    cr = (values[-1] - values[0]) / values[0]

    # Annualized Return
    num_periods = len(returns)
    years = num_periods / periods_per_year
    annualized_return = (1 + cr) ** (1 / years) - 1 if years > 0 else 0

    # Volatility (annualized)
    vol = np.std(returns) * np.sqrt(periods_per_year) if len(returns) > 1 else 0

    # Sharpe Ratio
    excess_return = np.mean(returns) - (risk_free_rate / periods_per_year)
    sharpe = (excess_return / np.std(returns) * np.sqrt(periods_per_year)) if np.std(returns) > 0 else 0

    # Sortino Ratio
    negative_returns = returns[returns < 0]
    if len(negative_returns) > 0:
        downside_std = np.std(negative_returns)
        sortino = excess_return / downside_std * np.sqrt(periods_per_year) if downside_std > 0 else 0
    else:
        sortino = float('inf') if np.mean(returns) > 0 else 0

    # Maximum Drawdown
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    mdd = np.min(drawdown)

    # Calmar Ratio (Annualized Return / Abs(MDD))
    calmar = annualized_return / abs(mdd) if mdd != 0 else 0

    # Win Rate and Average Win/Loss
    winning_periods = returns > 0
    win_rate = np.mean(winning_periods) if len(returns) > 0 else 0
    avg_win = np.mean(returns[winning_periods]) if np.any(winning_periods) else 0
    avg_loss = np.mean(returns[~winning_periods]) if np.any(~winning_periods) else 0

    # Calculate number of trades (excluding no_trade actions)
    num_trades = 0
    for i in range(1, len(portfolio_df)):
        if portfolio_df.iloc[i]['total_value'] != portfolio_df.iloc[i-1]['total_value']:
            num_trades += 1

    return {
        'CR': cr,
        'Annualized Return': annualized_return,
        'SR': sortino,
        'Sharpe Ratio': sharpe,
        'Vol': vol,
        'MDD': mdd,
        'Calmar Ratio': calmar,
        'Win Rate': win_rate,
        'Average Win': avg_win,
        'Average Loss': avg_loss,
        'Initial Value': values[0],
        'Final Value': values[-1],
        'Total Positions': len(portfolio_df),
        'Number of Trades': num_trades,
        'Date Range': f"{portfolio_df['date'].iloc[0]} to {portfolio_df['date'].iloc[-1]}"
    }


def detect_market_type(positions):
    """
    Detect if this is crypto or stock trading based on symbols.

    Returns:
        'crypto' or 'stock'
    """
    # Get all symbols from first few positions
    symbols = set()
    for entry in positions[:10]:
        for symbol in entry['positions'].keys():
            if symbol != 'CASH':
                symbols.add(symbol)

    # Common crypto symbols
    crypto_symbols = {'BTC', 'ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'LINK', 'LTC', 'SUI', 'XRP'}

    if symbols & crypto_symbols:
        return 'crypto'
    return 'stock'


def main():
    parser = argparse.ArgumentParser(description='Calculate trading performance metrics')
    parser.add_argument('position_file', help='Path to position.jsonl file')
    parser.add_argument('--data-dir', default='data', help='Directory containing price data')
    parser.add_argument('--is-crypto', action='store_true', help='Force crypto mode')
    parser.add_argument('--is-astock', action='store_true', help='Force A-stock mode')
    parser.add_argument('--is-hourly', action='store_true', help='Use hourly trading periods (affects annualization)')
    parser.add_argument('--verbose', action='store_true', help='Show all warning messages')
    parser.add_argument('--risk-free-rate', type=float, default=0.0, help='Annual risk-free rate (default: 0.0)')

    args = parser.parse_args()

    # Load position data
    print(f"Loading position data from {args.position_file}...")
    positions = load_position_data(args.position_file)
    print(f"Loaded {len(positions)} position entries")

    # Detect market type
    is_crypto = args.is_crypto or detect_market_type(positions) == 'crypto'
    is_astock = args.is_astock or 'astock' in str(args.position_file).lower()

    if is_astock:
        market_type = 'A-Stock'
    elif is_crypto:
        market_type = 'crypto'
    else:
        market_type = 'stock'

    print(f"Detected market type: {market_type}")

    # Load price data
    print(f"Loading price data from {args.data_dir}...")
    price_data = load_all_price_files(args.data_dir, is_crypto, is_astock)
    print(f"Loaded price data for {len(price_data)} symbols")

    if len(price_data) == 0:
        print("ERROR: No price data loaded! Check your --data-dir path.")
        print(f"Looking in: {args.data_dir}")
        if is_astock:
            print("For A-stock, try: --data-dir data/A_stock")
        return

    # Calculate portfolio values
    print("Calculating portfolio values...")
    portfolio_df = calculate_portfolio_values(positions, price_data, is_crypto, args.verbose)

    # Determine periods per year based on data frequency and market type
    if args.is_hourly:
        # Approximately 252 trading days * 6.5 hours per day
        periods_per_year = 252 * 6.5
    elif is_crypto:
        # Crypto markets trade 365 days a year
        periods_per_year = 365
    else:
        # Traditional stock markets: 252 trading days per year
        periods_per_year = 252

    # Calculate metrics
    print("Calculating metrics...")
    metrics = calculate_metrics(portfolio_df, periods_per_year, args.risk_free_rate)

    # Print results
    print("\n" + "="*60)
    print("PERFORMANCE METRICS")
    print("="*60)
    print(f"Date Range:        {metrics['Date Range']}")
    print(f"Initial Value:     ${metrics['Initial Value']:,.2f}")
    print(f"Final Value:       ${metrics['Final Value']:,.2f}")
    print(f"Total Positions:   {metrics['Total Positions']}")
    print(f"Number of Trades:  {metrics['Number of Trades']}")
    print("-"*60)
    print("PRIMARY METRICS:")
    print(f"  CR (Cumulative Return):    {metrics['CR']*100:>8.2f}%")
    print(f"  SR (Sortino Ratio):        {metrics['SR']:>8.2f}")
    print(f"  Vol (Volatility):          {metrics['Vol']*100:>8.2f}%")
    print(f"  MDD (Maximum Drawdown):    {metrics['MDD']*100:>8.2f}%")
    print("-"*60)
    print("ADDITIONAL METRICS:")
    print(f"  Annualized Return:         {metrics['Annualized Return']*100:>8.2f}%")
    print(f"  Sharpe Ratio:              {metrics['Sharpe Ratio']:>8.2f}")
    print(f"  Calmar Ratio:              {metrics['Calmar Ratio']:>8.2f}")
    print(f"  Win Rate:                  {metrics['Win Rate']*100:>8.2f}%")
    print(f"  Average Win:               {metrics['Average Win']*100:>8.2f}%")
    print(f"  Average Loss:              {metrics['Average Loss']*100:>8.2f}%")
    print("="*60)

    # Save detailed results
    output_file = Path(args.position_file).parent / 'performance_metrics.json'
    with open(output_file, 'w') as f:
        # Convert to serializable format
        output_metrics = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v
                         for k, v in metrics.items()}
        json.dump(output_metrics, f, indent=2)
    print(f"\nDetailed metrics saved to {output_file}")

    # Save portfolio values
    portfolio_csv = Path(args.position_file).parent / 'portfolio_values.csv'
    portfolio_df.to_csv(portfolio_csv, index=False)
    print(f"Portfolio values saved to {portfolio_csv}")


if __name__ == '__main__':
    main()

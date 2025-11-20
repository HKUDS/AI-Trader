#!/usr/bin/env python3
"""
Visualize trading metrics over time for all agents in both markets.
Creates two figures (US and A-Stock), each with 4 horizontal subplots for CR, SR, Vol, MDD.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
import argparse

# Set seaborn style for beautiful plots
sns.set_theme(style="whitegrid", palette="husl")
sns.set_context("notebook", font_scale=1.1)

# Agent display names and colors
AGENT_MAPPING = {
    'deepseek-chat-v3.1': 'DeepSeek-v3.1',
    'MiniMax-M2': 'MiniMax-M2',
    'claude-3.7-sonnet': 'Claude-3.7-Sonnet',
    'gpt-5': 'GPT-5',
    'qwen3-max': 'Qwen3-Max',
    'gemini-2.5-flash': 'Gemini-2.5-Flash'
}

# Custom color palette for agents
AGENT_COLORS = {
    'DeepSeek-v3.1': '#FF6B6B',      # Red
    'MiniMax-M2': '#4ECDC4',         # Teal
    'Claude-3.7-Sonnet': '#45B7D1',  # Blue
    'GPT-5': '#96CEB4',              # Green
    'Qwen3-Max': '#FFEAA7',          # Yellow
    'Gemini-2.5-Flash': '#DFE6E9'    # Gray
}


def load_portfolio_data(agent_dir):
    """Load portfolio values for an agent."""
    portfolio_file = agent_dir / 'position' / 'portfolio_values.csv'

    if not portfolio_file.exists():
        return None

    df = pd.read_csv(portfolio_file)
    df['date'] = pd.to_datetime(df['date'])
    return df


def calculate_rolling_metrics(df, is_hourly=True):
    """Calculate rolling metrics from portfolio values."""
    # Calculate returns
    df['returns'] = df['total_value'].pct_change()

    # CR: Cumulative Return
    initial_value = df['total_value'].iloc[0]
    df['CR'] = (df['total_value'] - initial_value) / initial_value * 100

    # SR: Sortino Ratio (expanding window)
    periods_per_year = 252 * 6.5 if is_hourly else 252
    sortino_ratios = []

    # Use minimum periods to avoid unstable early calculations
    # For daily: 3 days is enough, for hourly: 10 hours
    min_periods = 10 if is_hourly else 3

    for i in range(len(df)):
        if i < min_periods:
            sortino_ratios.append(np.nan)
            continue

        returns_so_far = df['returns'].iloc[1:i+1].dropna()

        if len(returns_so_far) < min_periods:
            sortino_ratios.append(np.nan)
            continue

        # Calculate downside deviation
        negative_returns = returns_so_far[returns_so_far < 0]

        if len(negative_returns) > 0:
            downside_std = negative_returns.std()
            # Use a minimum threshold for downside std to avoid extreme spikes
            min_downside_std = 0.0001
            downside_std = max(downside_std, min_downside_std)

            sortino = (returns_so_far.mean() / downside_std) * np.sqrt(periods_per_year)
            # Cap to reasonable range
            sortino = np.clip(sortino, -20, 20)
        else:
            # No negative returns yet
            mean_return = returns_so_far.mean()
            if mean_return > 0:
                sortino = 20  # Cap at upper limit
            else:
                sortino = 0

        sortino_ratios.append(sortino)

    df['SR'] = sortino_ratios

    # Vol: Expanding Volatility
    volatilities = []
    for i in range(len(df)):
        if i < 2:
            volatilities.append(np.nan)
            continue

        returns_so_far = df['returns'].iloc[1:i+1].dropna()

        if len(returns_so_far) < 2:
            volatilities.append(np.nan)
            continue

        vol = returns_so_far.std() * np.sqrt(periods_per_year) * 100
        volatilities.append(vol)

    df['Vol'] = volatilities

    # MDD: Maximum Drawdown
    cumulative = (1 + df['returns'].fillna(0)).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max * 100
    df['MDD'] = drawdown

    return df


def load_baseline_data(baseline_file, is_hourly=True, date_range=None):
    """Load and calculate baseline metrics."""
    with open(baseline_file, 'r') as f:
        data = json.load(f)

    # Find time series key
    time_series_key = None
    for key in ['Time Series (60min)', 'Time Series (Daily)', 'Time Series (Hourly)']:
        if key in data:
            time_series_key = key
            break

    if not time_series_key:
        return None

    time_series = data[time_series_key]

    # Extract dates and prices
    all_dates = sorted(time_series.keys())

    # Filter by date range
    if date_range:
        start_date, end_date = date_range
        if is_hourly:
            dates = [d for d in all_dates if start_date <= d <= end_date]
        else:
            dates = [d for d in all_dates if start_date <= d <= end_date]
    else:
        dates = all_dates

    if len(dates) < 2:
        return None

    # Create DataFrame
    prices = [float(time_series[d].get('4. close', time_series[d].get('4. sell price', 0))) for d in dates]
    df = pd.DataFrame({
        'date': pd.to_datetime(dates),
        'price': prices
    })

    # Normalize to portfolio value starting at 10000 (US) or 100000 (A-Stock)
    initial_value = 10000 if is_hourly else 100000
    df['total_value'] = df['price'] / df['price'].iloc[0] * initial_value

    # Calculate metrics
    df = calculate_rolling_metrics(df, is_hourly=is_hourly)

    return df


def get_agent_date_range(agent_data_dir):
    """Extract date range from first available agent."""
    for agent_dir in agent_data_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        portfolio_file = agent_dir / 'position' / 'portfolio_values.csv'
        if portfolio_file.exists():
            df = pd.read_csv(portfolio_file)
            if len(df) > 0:
                # Extract date part
                start_date = df['date'].iloc[0].split(' ')[0]
                end_date = df['date'].iloc[-1].split(' ')[0]
                return (start_date, end_date)

    return None


def plot_single_metric(agent_data, baseline_data, market_name, metric_key, ylabel, title, output_file):
    """Create a single plot for one metric with larger fonts for better readability."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot each agent
    for agent_name, df in agent_data.items():
        display_name = AGENT_MAPPING.get(agent_name, agent_name)
        color = AGENT_COLORS.get(display_name, None)

        # Skip NaN values for cleaner plots
        plot_df = df[['date', metric_key]].dropna()

        ax.plot(plot_df['date'], plot_df[metric_key],
               label=display_name, linewidth=3.0, alpha=0.8, color=color)

    # Plot baseline if available
    if baseline_data is not None:
        plot_df = baseline_data[['date', metric_key]].dropna()
        ax.plot(plot_df['date'], plot_df[metric_key],
               label='Baseline', linewidth=3.5, linestyle='--',
               color='black', alpha=0.7)

    # Styling with larger fonts for separate plots
    ax.set_xlabel('Time', fontsize=20, fontweight='bold')
    ax.set_ylabel(ylabel, fontsize=20, fontweight='bold')
    ax.set_title(f'{market_name} - {title}', fontsize=22, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=14, framealpha=0.7)

    # Increase tick label sizes
    ax.tick_params(axis='x', rotation=45, labelsize=18)
    ax.tick_params(axis='y', labelsize=18)

    # Add horizontal line at y=0 for reference
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=1.0, alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_file, format='pdf', bbox_inches='tight')
    print(f"✅ Saved: {output_file}")
    plt.close()


def plot_separate_metrics(agent_data, baseline_data, market_name, output_dir, is_hourly=True):
    """Create 4 separate plots for each metric."""
    metrics = [
        ('CR', 'Cumulative Return (%)', 'Cumulative Return (CR)'),
        ('SR', 'Sortino Ratio', 'Sortino Ratio (SR)'),
        ('Vol', 'Volatility (%)', 'Volatility (Vol)'),
        ('MDD', 'Maximum Drawdown (%)', 'Maximum Drawdown (MDD)')
    ]

    market_suffix = market_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')

    for metric_key, ylabel, title in metrics:
        filename = f"{market_suffix}_{metric_key.lower()}_metrics.pdf"
        output_file = output_dir / filename
        plot_single_metric(agent_data, baseline_data, market_name, metric_key, ylabel, title, output_file)


def plot_market_metrics(agent_data, baseline_data, market_name, output_file, is_hourly=True):
    """Create 4 horizontal subplots for a market."""
    fig, axes = plt.subplots(1, 4, figsize=(24, 5))

    metrics = [
        ('CR', 'Cumulative Return (%)', 'CR ↑'),
        ('SR', 'Sortino Ratio', 'SR ↑'),
        ('Vol', 'Volatility (%)', 'Vol ↓'),
        ('MDD', 'Maximum Drawdown (%)', 'MDD ↓')
    ]

    for idx, (metric_key, ylabel, title) in enumerate(metrics):
        ax = axes[idx]

        # Plot each agent
        for agent_name, df in agent_data.items():
            display_name = AGENT_MAPPING.get(agent_name, agent_name)
            color = AGENT_COLORS.get(display_name, None)

            # Skip NaN values for cleaner plots
            plot_df = df[['date', metric_key]].dropna()

            ax.plot(plot_df['date'], plot_df[metric_key],
                   label=display_name, linewidth=2, alpha=0.8, color=color)

        # Plot baseline if available
        if baseline_data is not None:
            plot_df = baseline_data[['date', metric_key]].dropna()
            ax.plot(plot_df['date'], plot_df[metric_key],
                   label='Baseline', linewidth=2.5, linestyle='--',
                   color='black', alpha=0.7)

        # Styling
        ax.set_xlabel('Time', fontsize=11, fontweight='bold')
        ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', fontsize=8, framealpha=0.9)

        # Rotate x-axis labels for better readability
        ax.tick_params(axis='x', rotation=45)

        # Add horizontal line at y=0 for reference
        ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_file, format='pdf', bbox_inches='tight')
    print(f"✅ Saved: {output_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Visualize trading metrics over time')
    parser.add_argument('--skip-us', action='store_true', help='Skip US market plots')
    parser.add_argument('--skip-astock', action='store_true', help='Skip A-Stock market plots')
    parser.add_argument('--skip-crypto', action='store_true', help='Skip Crypto market plots')
    parser.add_argument('--separate-plots', action='store_true', help='Save each metric as a separate plot instead of combined 4-subplot figure')
    parser.add_argument('--output-dir', default='plots', help='Output directory for plots')

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    # Process US Market
    if not args.skip_us:
        print("=" * 70)
        print("PROCESSING U.S. MARKET VISUALIZATIONS")
        print("=" * 70)

        us_data_dir = Path('data/agent_data')
        agent_data = {}

        for agent_dir in sorted(us_data_dir.iterdir()):
            if not agent_dir.is_dir():
                continue

            agent_name = agent_dir.name

            if agent_name not in AGENT_MAPPING:
                continue

            print(f"📊 Loading {agent_name}...")
            df = load_portfolio_data(agent_dir)

            if df is not None:
                df = calculate_rolling_metrics(df, is_hourly=True)
                agent_data[agent_name] = df
                print(f"✅ {agent_name}: {len(df)} time points")

        # Load baseline
        print("📊 Loading QQQ baseline...")
        qqq_file = Path('data/daily_prices_QQQ.json')
        baseline_data = None

        if qqq_file.exists():
            date_range = get_agent_date_range(us_data_dir)
            baseline_data = load_baseline_data(qqq_file, is_hourly=True, date_range=date_range)
            if baseline_data is not None:
                print(f"✅ QQQ Baseline: {len(baseline_data)} time points")

        # Create plot
        if agent_data:
            if args.separate_plots:
                plot_separate_metrics(agent_data, baseline_data, 'U.S. Market (NASDAQ-100)',
                                    output_dir, is_hourly=True)
            else:
                output_file = output_dir / 'us_market_metrics.pdf'
                plot_market_metrics(agent_data, baseline_data, 'U.S. Market (NASDAQ-100)',
                                  output_file, is_hourly=True)

    # Process A-Stock Market
    if not args.skip_astock:
        print("\n" + "=" * 70)
        print("PROCESSING A-SHARE MARKET VISUALIZATIONS")
        print("=" * 70)

        astock_data_dir = Path('data/agent_data_astock')
        agent_data = {}

        for agent_dir in sorted(astock_data_dir.iterdir()):
            if not agent_dir.is_dir():
                continue

            agent_name = agent_dir.name

            if agent_name not in AGENT_MAPPING:
                continue

            print(f"📊 Loading {agent_name}...")
            df = load_portfolio_data(agent_dir)

            if df is not None:
                df = calculate_rolling_metrics(df, is_hourly=False)
                agent_data[agent_name] = df
                print(f"✅ {agent_name}: {len(df)} time points")

        # Load baseline
        print("📊 Loading SSE-50 baseline...")
        sse_file = Path('data/A_stock/index_daily_sse_50.json')
        baseline_data = None

        if sse_file.exists():
            date_range = get_agent_date_range(astock_data_dir)
            # Override start date to Sep 30 for A-Stock
            if date_range:
                date_range = ('2025-09-30', date_range[1])
            baseline_data = load_baseline_data(sse_file, is_hourly=False, date_range=date_range)
            if baseline_data is not None:
                print(f"✅ SSE-50 Baseline: {len(baseline_data)} time points")

        # Create plot
        if agent_data:
            if args.separate_plots:
                plot_separate_metrics(agent_data, baseline_data, 'A-Share Market (SSE-50)',
                                    output_dir, is_hourly=False)
            else:
                output_file = output_dir / 'astock_market_metrics.pdf'
                plot_market_metrics(agent_data, baseline_data, 'A-Share Market (SSE-50)',
                                  output_file, is_hourly=False)

    # Process Crypto Market
    if not args.skip_crypto:
        print("\n" + "=" * 70)
        print("PROCESSING CRYPTO MARKET VISUALIZATIONS")
        print("=" * 70)

        crypto_data_dir = Path('data/agent_data_crypto')
        agent_data = {}

        for agent_dir in sorted(crypto_data_dir.iterdir()):
            if not agent_dir.is_dir():
                continue

            agent_name = agent_dir.name

            if agent_name not in AGENT_MAPPING:
                continue

            print(f"📊 Loading {agent_name}...")
            df = load_portfolio_data(agent_dir)

            if df is not None:
                df = calculate_rolling_metrics(df, is_hourly=False)  # Daily trading for crypto
                agent_data[agent_name] = df
                print(f"✅ {agent_name}: {len(df)} time points")

        # Load baseline (using crypto index if available)
        print("📊 Loading Crypto baseline...")
        crypto_index_file = Path('data/crypto/CD5_crypto_index.json')
        baseline_data = None

        if crypto_index_file.exists():
            date_range = get_agent_date_range(crypto_data_dir)
            baseline_data = load_baseline_data(crypto_index_file, is_hourly=False, date_range=date_range)
            if baseline_data is not None:
                print(f"✅ Crypto Index Baseline: {len(baseline_data)} time points")

        # Create plot
        if agent_data:
            if args.separate_plots:
                plot_separate_metrics(agent_data, baseline_data, 'Crypto Market',
                                    output_dir, is_hourly=False)
            else:
                output_file = output_dir / 'crypto_market_metrics.pdf'
                plot_market_metrics(agent_data, baseline_data, 'Crypto Market',
                                  output_file, is_hourly=False)

    print("\n" + "=" * 70)
    print(f"✅ All plots saved to: {output_dir}/")
    print("=" * 70)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Quant Backtest - Command Line Interface

Run backtests from the command line without the web UI.

Usage:
    python -m quant_backtest.cli --strategy "SMA Crossover" --symbols AAPL GOOGL
    python -m quant_backtest.cli --help

Examples:
    # Basic backtest with sample data
    python -m quant_backtest.cli

    # Custom strategy and symbols
    python -m quant_backtest.cli --strategy "RSI" --symbols AAPL MSFT --cash 50000

    # Save results to file
    python -m quant_backtest.cli --output results.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Quant Backtest - Free Algorithmic Trading Backtester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run with defaults
  %(prog)s --strategy "RSI" --symbols AAPL    # Use RSI strategy on AAPL
  %(prog)s --cash 50000 --output results.json # Custom cash, save results
        """,
    )

    parser.add_argument(
        "--strategy", "-s",
        type=str,
        default="SMA Crossover",
        help="Strategy to use (default: SMA Crossover)",
    )

    parser.add_argument(
        "--symbols", "-y",
        type=str,
        nargs="+",
        default=["AAPL", "GOOGL", "MSFT"],
        help="Symbols to trade (default: AAPL GOOGL MSFT)",
    )

    parser.add_argument(
        "--start", "-b",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD), defaults to 1 year ago",
    )

    parser.add_argument(
        "--end", "-e",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD), defaults to today",
    )

    parser.add_argument(
        "--cash", "-c",
        type=float,
        default=100000.0,
        help="Initial cash (default: 100000)",
    )

    parser.add_argument(
        "--commission",
        type=float,
        default=0.001,
        help="Commission rate as decimal (default: 0.001 = 0.1%%)",
    )

    parser.add_argument(
        "--data-source", "-d",
        type=str,
        choices=["sample", "yahoo", "ai_trader"],
        default="sample",
        help="Data source (default: sample)",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file for results (JSON)",
    )

    parser.add_argument(
        "--list-strategies",
        action="store_true",
        help="List available strategies and exit",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )

    return parser.parse_args()


def main():
    """Main CLI entry point."""
    args = parse_args()

    # Import here to avoid slow startup for --help
    from quant_backtest.core import BacktestEngine, BacktestConfig
    from quant_backtest.strategies import STRATEGY_REGISTRY, list_strategies
    from quant_backtest.data import generate_sample_data, DataFetcher

    # List strategies and exit
    if args.list_strategies:
        print("\nAvailable Strategies:")
        print("-" * 40)
        for name in list_strategies():
            strategy_class = STRATEGY_REGISTRY[name]
            params = strategy_class.get_parameter_info()
            print(f"\n  {name}")
            for param, info in params.items():
                print(f"    --{param}: {info.get('description', '')} (default: {info.get('default', 'N/A')})")
        return

    # Parse dates
    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = datetime.now() - timedelta(days=365)

    if args.end:
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
    else:
        end_date = datetime.now()

    print("\n" + "=" * 60)
    print("QUANT BACKTEST - Free Algorithmic Trading Platform")
    print("=" * 60)

    print(f"\nStrategy: {args.strategy}")
    print(f"Symbols: {', '.join(args.symbols)}")
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Initial Cash: ${args.cash:,.2f}")
    print(f"Data Source: {args.data_source}")

    # Load data
    print("\nLoading data...")
    if args.data_source == "sample":
        data = generate_sample_data(
            symbols=args.symbols,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            seed=42,
        )
    elif args.data_source == "yahoo":
        fetcher = DataFetcher()
        data = fetcher.fetch_yahoo(
            args.symbols,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
    else:  # ai_trader
        fetcher = DataFetcher()
        data = fetcher.load_ai_trader_data(symbols=args.symbols)

    if not data:
        print("Error: No data loaded!")
        return

    print(f"Loaded data for {len(data)} symbols")

    # Create strategy
    strategy_class = STRATEGY_REGISTRY.get(args.strategy)
    if not strategy_class:
        print(f"Error: Unknown strategy '{args.strategy}'")
        print(f"Available: {', '.join(list_strategies())}")
        return

    strategy = strategy_class(symbols=args.symbols)

    # Create engine
    config = BacktestConfig(
        initial_cash=args.cash,
        commission_rate=args.commission,
    )
    engine = BacktestEngine(config=config)
    engine.load_data(data)
    engine.set_strategy(strategy)

    # Run backtest
    print("\nRunning backtest...")

    def progress(current, total):
        if args.verbose:
            pct = (current / total) * 100
            print(f"\r  Progress: {pct:.1f}%", end="", flush=True)

    results = engine.run(
        start_date=start_date,
        end_date=end_date,
        progress_callback=progress if args.verbose else None,
    )

    if args.verbose:
        print()  # New line after progress

    # Print results
    results.metrics.print_summary()

    # Save to file
    if args.output:
        output_path = Path(args.output)
        results.save(str(output_path))
        print(f"\nResults saved to: {output_path}")

    print("\n" + "=" * 60)
    print("Backtest complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

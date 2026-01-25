#!/usr/bin/env python3
"""
Basic Backtest Example

This example demonstrates the core functionality of the quant-backtest platform.
Run with: python -m quant_backtest.examples.basic_backtest
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_backtest import BacktestEngine
from quant_backtest.strategies import (
    SMACrossoverStrategy,
    RSIStrategy,
    MACDStrategy,
)
from quant_backtest.data import generate_sample_data


def main():
    print("=" * 60)
    print("QUANT BACKTEST - Basic Example")
    print("=" * 60)

    # 1. Generate sample data (no API needed!)
    print("\n[1] Generating sample market data...")
    data = generate_sample_data(
        symbols=["AAPL", "GOOGL", "MSFT", "NVDA"],
        start_date="2023-01-01",
        end_date="2024-01-01",
        seed=42,  # For reproducible results
    )
    print(f"    Generated data for {len(data)} symbols")

    # 2. Create backtest engine
    print("\n[2] Creating backtest engine...")
    engine = BacktestEngine(
        initial_cash=100000,
        commission_rate=0.001,  # 0.1%
        slippage_rate=0.0005,   # 0.05%
    )

    # 3. Load data
    print("\n[3] Loading data into engine...")
    engine.load_data(data)

    # 4. Create strategy
    print("\n[4] Setting up SMA Crossover strategy...")
    strategy = SMACrossoverStrategy(
        fast_period=10,
        slow_period=30,
        position_size=20.0,  # 20% of portfolio per trade
    )
    engine.set_strategy(strategy)

    # 5. Run backtest
    print("\n[5] Running backtest...")
    results = engine.run()

    # 6. Display results
    results.metrics.print_summary()

    # 7. Show some trades
    trades = results.get_trades()
    if trades:
        print("\nSample Trades (first 5):")
        print("-" * 60)
        for trade in trades[:5]:
            print(f"  {trade['timestamp'][:10]} | {trade['side'].upper():4} | "
                  f"{trade['symbol']:5} | {trade['filled_quantity']:8.2f} @ ${trade['filled_price']:.2f}")

    # 8. Compare strategies
    print("\n" + "=" * 60)
    print("STRATEGY COMPARISON")
    print("=" * 60)

    strategies = [
        ("SMA Crossover", SMACrossoverStrategy(fast_period=10, slow_period=30)),
        ("RSI", RSIStrategy(rsi_period=14, oversold=30, overbought=70)),
        ("MACD", MACDStrategy(fast_period=12, slow_period=26, signal_period=9)),
    ]

    results_comparison = []

    for name, strategy in strategies:
        engine = BacktestEngine(initial_cash=100000)
        engine.load_data(data)
        engine.set_strategy(strategy)
        results = engine.run()

        results_comparison.append({
            "Strategy": name,
            "Return": f"{results.metrics.total_return:.2f}%",
            "Sharpe": f"{results.metrics.sharpe_ratio:.3f}",
            "MaxDD": f"{results.metrics.max_drawdown:.2f}%",
            "Trades": results.metrics.total_trades,
        })

    # Print comparison table
    print(f"\n{'Strategy':<15} {'Return':>10} {'Sharpe':>10} {'Max DD':>10} {'Trades':>8}")
    print("-" * 60)
    for r in results_comparison:
        print(f"{r['Strategy']:<15} {r['Return']:>10} {r['Sharpe']:>10} {r['MaxDD']:>10} {r['Trades']:>8}")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

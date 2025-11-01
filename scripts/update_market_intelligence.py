#!/usr/bin/env python3
"""
Update Market Intelligence Script

Runs the Market Intelligence Agent to curate and update market narratives.
Can be run periodically (e.g., weekly) or before major trading runs.

Usage:
    python scripts/update_market_intelligence.py --date 2025-10-15
    python scripts/update_market_intelligence.py --date-range 2025-10-01 2025-10-21
"""

import argparse
import anyio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from agent.market_intelligence_agent import MarketIntelligenceAgent
from tools.general_tools import write_config_value
from tools.market_intelligence import MarketIntelligence, seed_initial_intelligence


async def update_intelligence_for_date(date: str):
    """
    Update market intelligence for a specific date.

    Args:
        date: Date in YYYY-MM-DD format
    """
    print(f"\n{'='*60}")
    print(f"Updating Market Intelligence for {date}")
    print('='*60)

    # Set date
    write_config_value("TODAY_DATE", date)

    # Create and run agent
    agent = MarketIntelligenceAgent()
    await agent.initialize()
    await agent.update_intelligence(date)

    # Show updated intelligence
    intel = MarketIntelligence()
    summary = intel.get_intelligence_summary(date, lookback_days=7)

    print(f"\n📊 Intelligence Summary:")
    print(f"   Total items (last 7 days): {summary['total_items']}")
    for category, count in summary['by_category'].items():
        if count > 0:
            print(f"   - {category}: {count} updates")


async def update_intelligence_range(start_date: str, end_date: str, frequency: int = 7):
    """
    Update market intelligence for a date range.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        frequency: Update frequency in days (default: 7 = weekly)
    """
    print(f"Updating intelligence from {start_date} to {end_date}")
    print(f"Frequency: Every {frequency} days")

    current_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    update_count = 0

    while current_dt <= end_dt:
        # Update on trading days (weekdays) at specified frequency
        if current_dt.weekday() < 5:  # Monday-Friday
            if update_count % frequency == 0:
                current_date = current_dt.strftime("%Y-%m-%d")
                await update_intelligence_for_date(current_date)

            update_count += 1

        current_dt += timedelta(days=1)

    print(f"\n✅ Intelligence updates complete!")
    print(f"   Updated {update_count // frequency} times from {start_date} to {end_date}")


async def seed_intelligence(date: str):
    """Seed initial intelligence for a date"""
    print(f"📰 Seeding initial intelligence for {date}")

    intel = MarketIntelligence()
    seed_initial_intelligence(intel, date)

    print("✅ Initial intelligence seeded")

    # Show what was seeded
    context = intel.build_intelligence_context(date)
    print("\n" + context)


async def show_intelligence(date: str):
    """Display current intelligence for a date"""
    intel = MarketIntelligence()

    print(f"\n{'='*60}")
    print(f"Market Intelligence for {date}")
    print('='*60)

    context = intel.build_intelligence_context(date, lookback_days=30)
    print(context)

    summary = intel.get_intelligence_summary(date, lookback_days=30)
    print(f"\n📊 Summary:")
    print(f"   Total items (last 30 days): {summary['total_items']}")
    for category, count in summary['by_category'].items():
        if count > 0:
            print(f"   - {category}: {count} updates")


def main():
    parser = argparse.ArgumentParser(
        description="Update market intelligence database"
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update intelligence')
    update_parser.add_argument(
        '--date',
        type=str,
        help='Single date to update (YYYY-MM-DD)'
    )
    update_parser.add_argument(
        '--date-range',
        nargs=2,
        metavar=('START', 'END'),
        help='Date range to update (YYYY-MM-DD YYYY-MM-DD)'
    )
    update_parser.add_argument(
        '--frequency',
        type=int,
        default=7,
        help='Update frequency in days (default: 7 = weekly)'
    )

    # Seed command
    seed_parser = subparsers.add_parser('seed', help='Seed initial intelligence')
    seed_parser.add_argument(
        'date',
        type=str,
        help='Date to seed intelligence for (YYYY-MM-DD)'
    )

    # Show command
    show_parser = subparsers.add_parser('show', help='Show current intelligence')
    show_parser.add_argument(
        'date',
        type=str,
        help='Date to show intelligence for (YYYY-MM-DD)'
    )

    args = parser.parse_args()

    if args.command == 'update':
        if args.date:
            anyio.run(update_intelligence_for_date, args.date)
        elif args.date_range:
            anyio.run(
                update_intelligence_range,
                args.date_range[0],
                args.date_range[1],
                args.frequency
            )
        else:
            print("Error: Specify --date or --date-range")
            parser.print_help()

    elif args.command == 'seed':
        anyio.run(seed_intelligence, args.date)

    elif args.command == 'show':
        anyio.run(show_intelligence, args.date)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Pre-compute Frontend Cache
Generates a static JSON file with all calculated metrics for faster frontend loading.
Run this script after updating trading data to regenerate the cache.

Usage:
    python scripts/precompute_frontend_cache.py

Output:
    docs/data/us_cache.json - Pre-computed data for US market
    docs/data/cn_cache.json - Pre-computed data for A-share market
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
import yaml


def get_data_version_hash(market_config):
    """
    Generate a version hash based on position files' modification times.
    This allows the frontend to detect when data has changed.
    """
    hash_obj = hashlib.md5()

    # Get agent data directory
    data_dir = market_config.get('data_dir', 'agent_data')
    base_path = Path(__file__).parent.parent / 'docs' / 'data' / data_dir

    # Collect all position file timestamps
    position_files = sorted(base_path.glob('*/position/position.jsonl'))

    timestamps = []
    for position_file in position_files:
        if position_file.exists():
            mtime = position_file.stat().st_mtime
            timestamps.append(f"{position_file.name}:{mtime}")

    # Create hash from all timestamps
    hash_input = '|'.join(timestamps)
    hash_obj.update(hash_input.encode('utf-8'))

    return hash_obj.hexdigest()[:12]  # Short hash


def load_config():
    """Load the YAML configuration file."""
    config_path = Path(__file__).parent.parent / 'docs' / 'config.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_position_data(agent_folder, market_config):
    """Load position data for a specific agent."""
    data_dir = market_config.get('data_dir', 'agent_data')
    position_file = Path(__file__).parent.parent / 'docs' / 'data' / data_dir / agent_folder / 'position' / 'position.jsonl'

    if not position_file.exists():
        return []

    positions = []
    with open(position_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    positions.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse line in {agent_folder}: {e}")

    return positions


def load_price_data_us(symbol):
    """Load price data for a US stock."""
    # Try hourly data first
    price_file = Path(__file__).parent.parent / 'docs' / 'data' / f'Ahourly_prices_{symbol}.json'

    if not price_file.exists():
        # Fall back to daily data
        price_file = Path(__file__).parent.parent / 'docs' / 'data' / f'daily_prices_{symbol}.json'

    if not price_file.exists():
        return None

    try:
        with open(price_file, 'r') as f:
            data = json.load(f)
            # Support both hourly (60min) and daily data formats
            return data.get('Time Series (60min)') or data.get('Time Series (Daily)')
    except Exception as e:
        print(f"Warning: Failed to load price data for {symbol}: {e}")
        return None


def load_price_data_cn(market_config=None):
    """Load all A-share price data from merged.jsonl or merged_hourly.jsonl."""
    # Determine which file to load based on market config
    if market_config and market_config.get('price_data_file'):
        price_data_file = market_config['price_data_file']
    else:
        price_data_file = 'A_stock/merged.jsonl'

    merged_file = Path(__file__).parent.parent / 'docs' / 'data' / price_data_file

    if not merged_file.exists():
        return {}

    # Determine which time series key to use
    time_granularity = market_config.get('time_granularity', 'daily') if market_config else 'daily'
    time_series_key = 'Time Series (60min)' if time_granularity == 'hourly' else 'Time Series (Daily)'

    price_cache = {}
    with open(merged_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                symbol = data['Meta Data']['2. Symbol']
                # Try the configured time series key, fall back to Daily if not found
                price_cache[symbol] = data.get(time_series_key) or data.get('Time Series (Daily)')
            except Exception as e:
                print(f"Warning: Failed to parse A-share price data: {e}")

    return price_cache


def get_closing_price(symbol, date, price_data, market='us'):
    """Get closing price for a symbol on a specific date."""
    if market == 'us':
        prices = price_data.get(symbol)
        if not prices:
            return None

        # Try exact match first
        if date in prices:
            return float(prices[date].get('4. close') or prices[date].get('4. sell price', 0))

        return None

    else:  # cn market
        prices = price_data.get(symbol)
        if not prices:
            return None

        # Try exact match first (for hourly data)
        if date in prices:
            price_value = prices[date].get('4. close') or prices[date].get('4. sell price', 0)
            if price_value and price_value != 'N/A':
                return float(price_value)

        # Extract date only for daily data matching
        date_only = date.split(' ')[0]

        if date_only in prices:
            price_value = prices[date_only].get('4. close') or prices[date_only].get('4. sell price', 0)
            if price_value and price_value != 'N/A':
                return float(price_value)

        # Try to find the REQUESTED timestamp or closest earlier timestamp on same date
        date_prefix = date_only
        matching_keys = [k for k in prices.keys() if k.startswith(date_prefix)]

        if matching_keys:
            # For hourly timestamps, find the exact or closest earlier time
            if ':' in date:  # Hourly timestamp requested
                # Try to find exact or closest earlier match
                matching_keys = [k for k in matching_keys if k <= date]
                if matching_keys:
                    closest_key = sorted(matching_keys)[-1]
                    price_value = prices[closest_key].get('4. close') or prices[closest_key].get('4. sell price', 0)
                    if price_value and price_value != 'N/A':
                        return float(price_value)
            else:  # Daily date requested
                # Use last available time on that day
                last_key = sorted(matching_keys)[-1]
                price_value = prices[last_key].get('4. close') or prices[last_key].get('4. sell price', 0)
                if price_value and price_value != 'N/A':
                    return float(price_value)

        return None


def calculate_asset_value(position, date, price_data, market='us'):
    """Calculate total asset value for a position on a given date."""
    total_value = position['positions'].get('CASH', 0)
    has_missing_price = False

    # Get all stock symbols (exclude CASH)
    symbols = [s for s in position['positions'].keys() if s != 'CASH']

    for symbol in symbols:
        shares = position['positions'][symbol]
        if shares > 0:
            price = get_closing_price(symbol, date, price_data, market)
            if price and price > 0:
                total_value += shares * price
            else:
                has_missing_price = True

    # For A-shares: return None if any price is missing
    if market == 'cn' and has_missing_price:
        return None

    return total_value


def process_agent_data_us(agent_config, market_config):
    """Process agent data for US market."""
    agent_folder = agent_config['folder']
    print(f"  Processing {agent_folder}...")

    # Load positions
    positions = load_position_data(agent_folder, market_config)
    if not positions:
        print(f"    No positions found for {agent_folder}")
        return None

    # Load all required price data
    price_data = {}
    all_symbols = set()
    for pos in positions:
        all_symbols.update([s for s in pos['positions'].keys() if s != 'CASH'])

    for symbol in all_symbols:
        price_data[symbol] = load_price_data_us(symbol)

    # Group positions by timestamp and take only the last position for each timestamp
    positions_by_timestamp = {}
    for position in positions:
        timestamp = position['date']
        if timestamp not in positions_by_timestamp or position['id'] > positions_by_timestamp[timestamp]['id']:
            positions_by_timestamp[timestamp] = position

    # Convert to array and sort
    unique_positions = sorted(positions_by_timestamp.values(), key=lambda x: (x['date'], x['id']))

    # Calculate asset history
    asset_history = []
    for position in unique_positions:
        timestamp = position['date']
        asset_value = calculate_asset_value(position, timestamp, price_data, 'us')
        asset_history.append({
            'date': timestamp,
            'value': asset_value,
            'id': position['id'],
            'action': position.get('this_action')
        })

    if not asset_history:
        print(f"    No valid asset history for {agent_folder}")
        return None

    result = {
        'name': agent_folder,
        'positions': positions,
        'assetHistory': asset_history,
        'initialValue': asset_history[0]['value'] if asset_history else 10000,
        'currentValue': asset_history[-1]['value'] if asset_history else 0,
        'return': ((asset_history[-1]['value'] - asset_history[0]['value']) / asset_history[0]['value'] * 100) if asset_history else 0
    }

    print(f"    ✓ {len(positions)} positions, {len(asset_history)} data points")
    return result


def process_agent_data_cn(agent_config, market_config, price_cache):
    """Process agent data for A-share market."""
    agent_folder = agent_config['folder']
    print(f"  Processing {agent_folder}...")

    # Load positions
    positions = load_position_data(agent_folder, market_config)
    if not positions:
        print(f"    No positions found for {agent_folder}")
        return None

    # Detect if data is hourly or daily
    first_date = positions[0]['date'] if positions else ''
    is_hourly_data = ':' in first_date

    # Check if we should preserve hourly timestamps or aggregate to daily
    preserve_hourly = market_config.get('time_granularity') == 'hourly' and is_hourly_data

    # Group positions appropriately
    positions_by_key = {}
    for position in positions:
        if preserve_hourly:
            # For hourly market: keep full timestamp as key
            key = position['date']
        elif is_hourly_data:
            # For daily market with hourly data: aggregate by date
            key = position['date'].split(' ')[0]
        else:
            # For daily data: use date as-is
            key = position['date']

        # For date-based aggregation, skip weekends
        if not preserve_hourly:
            date_str = key if not is_hourly_data else key.split(' ')[0]
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            if date_obj.weekday() in [5, 6]:  # Saturday or Sunday
                continue

        # Keep the position with the highest ID for each key
        if key not in positions_by_key or position['id'] > positions_by_key[key]['id']:
            positions_by_key[key] = {
                **position,
                'dateKey': key,
                'originalDate': position['date']
            }

    # Convert to array and sort
    unique_positions = sorted(positions_by_key.values(), key=lambda x: x['dateKey'])

    if not unique_positions:
        print(f"    No unique positions for {agent_folder}")
        return None

    # For hourly data, just return all positions without date filling
    if preserve_hourly:
        asset_history = []
        for position in unique_positions:
            asset_value = calculate_asset_value(position, position['dateKey'], price_cache, 'cn')
            if asset_value is not None:
                asset_history.append({
                    'date': position['dateKey'],
                    'value': asset_value,
                    'id': position['id'],
                    'action': position.get('this_action')
                })

        if not asset_history:
            print(f"    No valid asset history for {agent_folder}")
            return None

        result = {
            'name': agent_folder,
            'positions': [{'date': p['dateKey'], 'id': p['id'], 'positions': p['positions']} for p in unique_positions],
            'assetHistory': asset_history,
            'initialValue': asset_history[0]['value'] if asset_history else 10000,
            'currentValue': asset_history[-1]['value'] if asset_history else 0,
            'return': ((asset_history[-1]['value'] - asset_history[0]['value']) / asset_history[0]['value'] * 100) if asset_history else 0
        }

        print(f"    ✓ {len(result['positions'])} positions, {len(asset_history)} data points (hourly)")
        return result

    # For daily aggregated data: fill gaps and calculate values
    # Get date range
    start_date = datetime.strptime(unique_positions[0]['dateKey'], '%Y-%m-%d')
    end_date = datetime.strptime(unique_positions[-1]['dateKey'], '%Y-%m-%d')

    # Create position map for quick lookup
    position_map = {pos['dateKey']: pos for pos in unique_positions}

    # Fill all dates in range (skip weekends)
    asset_history = []
    current_position = None
    current_date = start_date

    while current_date <= end_date:
        # Skip weekends
        if current_date.weekday() not in [5, 6]:
            date_str = current_date.strftime('%Y-%m-%d')

            # Use position for this date if exists, otherwise use last known position
            if date_str in position_map:
                current_position = position_map[date_str]

            if current_position:
                # Calculate asset value
                asset_value = calculate_asset_value(current_position, date_str, price_cache, 'cn')

                if asset_value is not None:
                    asset_history.append({
                        'date': date_str,
                        'value': asset_value,
                        'id': current_position['id'],
                        'action': position_map.get(date_str, {}).get('this_action')
                    })

        # Move to next day
        from datetime import timedelta
        current_date += timedelta(days=1)

    if not asset_history:
        print(f"    No valid asset history for {agent_folder}")
        return None

    result = {
        'name': agent_folder,
        'positions': positions,
        'assetHistory': asset_history,
        'initialValue': asset_history[0]['value'] if asset_history else 10000,
        'currentValue': asset_history[-1]['value'] if asset_history else 0,
        'return': ((asset_history[-1]['value'] - asset_history[0]['value']) / asset_history[0]['value'] * 100) if asset_history else 0
    }

    print(f"    ✓ {len(positions)} positions, {len(asset_history)} data points")
    return result


def process_benchmark_us(market_config, agents_data=None):
    """Process QQQ benchmark data for US market."""
    print("  Processing QQQ benchmark...")

    benchmark_file = market_config.get('benchmark_file', 'Adaily_prices_QQQ.json')
    benchmark_path = Path(__file__).parent.parent / 'docs' / 'data' / benchmark_file

    if not benchmark_path.exists():
        print("    QQQ benchmark file not found")
        return None

    try:
        with open(benchmark_path, 'r') as f:
            data = json.load(f)
            time_series = data.get('Time Series (60min)') or data.get('Time Series (Daily)')

        if not time_series:
            print("    No time series data in QQQ benchmark")
            return None

        # Get initial value and date range from agents (matches live calculation behavior)
        initial_value = 100000  # Default to match agent initial cash
        start_date_filter = None
        end_date_filter = None

        if agents_data:
            for agent_name, agent_data in agents_data.items():
                if agent_data.get('assetHistory'):
                    # Get initial value from first agent
                    initial_value = agent_data['assetHistory'][0]['value']

                    # Get date range
                    agent_start = agent_data['assetHistory'][0]['date']
                    agent_end = agent_data['assetHistory'][-1]['date']

                    if not start_date_filter or agent_start < start_date_filter:
                        start_date_filter = agent_start
                    if not end_date_filter or agent_end > end_date_filter:
                        end_date_filter = agent_end

            print(f"    Date filter: {start_date_filter} to {end_date_filter}")
            print(f"    Using initial value from agents: {initial_value}")

        # Convert to asset history format
        asset_history = []
        dates = sorted(time_series.keys())

        benchmark_start_price = None

        for date in dates:
            # Apply date filtering to match agent date ranges
            if start_date_filter and date < start_date_filter:
                continue
            if end_date_filter and date > end_date_filter:
                continue

            close_price = float(time_series[date].get('4. close') or time_series[date].get('4. sell price', 0))

            if benchmark_start_price is None:
                benchmark_start_price = close_price

            benchmark_return = (close_price - benchmark_start_price) / benchmark_start_price
            current_value = initial_value * (1 + benchmark_return)

            asset_history.append({
                'date': date,
                'value': current_value,
                'id': f'qqq-{date}',
                'action': None
            })

        result = {
            'name': 'QQQ Invesco',
            'positions': [],
            'assetHistory': asset_history,
            'initialValue': initial_value,
            'currentValue': asset_history[-1]['value'] if asset_history else initial_value,
            'return': ((asset_history[-1]['value'] - asset_history[0]['value']) / asset_history[0]['value'] * 100) if asset_history else 0,
            'currency': 'USD'
        }

        print(f"    ✓ {len(asset_history)} data points")
        return result

    except Exception as e:
        print(f"    Error processing QQQ benchmark: {e}")
        return None


def process_benchmark_cn(market_config, agents_data=None):
    """Process SSE 50 benchmark data for A-share market."""
    print("  Processing SSE 50 benchmark...")

    benchmark_file = market_config.get('benchmark_file', 'A_stock/index_daily_sse_50.json')
    benchmark_path = Path(__file__).parent.parent / 'docs' / 'data' / benchmark_file

    if not benchmark_path.exists():
        print("    SSE 50 benchmark file not found")
        return None

    try:
        with open(benchmark_path, 'r') as f:
            data = json.load(f)
            time_series = data.get('Time Series (Daily)')

        if not time_series:
            print("    No time series data in SSE 50 benchmark")
            return None

        # Find date range from agents (if provided)
        start_date_filter = None
        end_date_filter = None

        # Get initial value from first agent (matches live calculation behavior)
        initial_value = 100000  # Default to match agent initial cash

        if agents_data:
            for agent_name, agent_data in agents_data.items():
                if agent_data.get('assetHistory'):
                    # Get initial value from first agent
                    initial_value = agent_data['assetHistory'][0]['value']

                    # Get date range
                    agent_start = agent_data['assetHistory'][0]['date']
                    agent_end = agent_data['assetHistory'][-1]['date']

                    if not start_date_filter or agent_start < start_date_filter:
                        start_date_filter = agent_start
                    if not end_date_filter or agent_end > end_date_filter:
                        end_date_filter = agent_end

            print(f"    Date filter: {start_date_filter} to {end_date_filter}")
            print(f"    Using initial value from agents: {initial_value}")

        # Detect if this is hourly market by checking agent timestamps
        is_hourly_market = False
        all_agent_timestamps = set()
        if agents_data:
            for agent_name, agent_data in agents_data.items():
                if agent_data.get('assetHistory'):
                    first_date = agent_data['assetHistory'][0]['date']
                    if ':' in first_date:
                        is_hourly_market = True
                    # Collect all agent timestamps for hourly expansion
                    for h in agent_data['assetHistory']:
                        all_agent_timestamps.add(h['date'])
            print(f"    Market type: {'Hourly' if is_hourly_market else 'Daily'}")

        # Convert to asset history format
        asset_history = []
        dates = sorted(time_series.keys())

        benchmark_start_price = None

        # For hourly markets, use agent timestamps; for daily markets, use benchmark dates
        timestamps_to_use = sorted(all_agent_timestamps) if is_hourly_market else dates

        for timestamp in timestamps_to_use:
            # Apply date filtering to match agent date ranges
            if start_date_filter and timestamp < start_date_filter:
                continue
            if end_date_filter and timestamp > end_date_filter:
                continue

            # Find the benchmark price
            if is_hourly_market:
                # For hourly timestamps, extract date part and look up daily price
                date_only = timestamp.split(' ')[0]
                if date_only not in time_series:
                    continue
                close_price = float(time_series[date_only].get('4. close') or time_series[date_only].get('4. sell price', 0))
            else:
                # For daily timestamps, direct lookup
                if timestamp not in time_series:
                    continue
                close_price = float(time_series[timestamp].get('4. close') or time_series[timestamp].get('4. sell price', 0))

            if benchmark_start_price is None:
                benchmark_start_price = close_price

            benchmark_return = (close_price - benchmark_start_price) / benchmark_start_price
            current_value = initial_value * (1 + benchmark_return)

            asset_history.append({
                'date': timestamp,
                'value': current_value,
                'id': f'sse50-{timestamp}',
                'action': None
            })

        result = {
            'name': market_config.get('benchmark_display_name', 'SSE 50'),
            'positions': [],
            'assetHistory': asset_history,
            'initialValue': initial_value,
            'currentValue': asset_history[-1]['value'] if asset_history else initial_value,
            'return': ((asset_history[-1]['value'] - asset_history[0]['value']) / asset_history[0]['value'] * 100) if asset_history else 0,
            'currency': 'CNY'
        }

        print(f"    ✓ {len(asset_history)} data points")
        return result

    except Exception as e:
        print(f"    Error processing SSE 50 benchmark: {e}")
        return None


def generate_cache_for_market(market_id, market_config, config):
    """Generate cache file for a specific market."""
    print(f"\n{'='*60}")
    print(f"Generating cache for {market_id.upper()} market")
    print(f"{'='*60}")

    # Generate version hash
    version = get_data_version_hash(market_config)
    print(f"Version hash: {version}")

    # Process all enabled agents
    agents_data = {}

    if market_id == 'us':
        # Process US market agents
        for agent_config in market_config.get('agents', []):
            if agent_config.get('enabled', True):
                result = process_agent_data_us(agent_config, market_config)
                if result:
                    agents_data[agent_config['folder']] = result

        # Process benchmark (pass agents_data for initial value matching)
        benchmark_data = process_benchmark_us(market_config, agents_data)
        if benchmark_data:
            agents_data['QQQ Invesco'] = benchmark_data

    else:  # cn market
        # Load all A-share prices once
        print("  Loading A-share price data...")
        price_cache = load_price_data_cn(market_config)
        print(f"  Loaded prices for {len(price_cache)} symbols")

        # Process A-share market agents
        for agent_config in market_config.get('agents', []):
            if agent_config.get('enabled', True):
                result = process_agent_data_cn(agent_config, market_config, price_cache)
                if result:
                    agents_data[agent_config['folder']] = result

        # Process benchmark (pass agents_data for initial value matching and date range filtering)
        benchmark_data = process_benchmark_cn(market_config, agents_data)
        if benchmark_data:
            agents_data[benchmark_data['name']] = benchmark_data

    # Create cache object
    # Add a manual version prefix to force cache invalidation when data structure changes
    CACHE_FORMAT_VERSION = 'v4'  # Increment this when changing data structure (v4: fixed hourly SSE-50 benchmark)
    cache = {
        'version': f"{CACHE_FORMAT_VERSION}_{version}",
        'generatedAt': datetime.now().isoformat(),
        'market': market_id,
        'agentsData': agents_data
    }

    # Write cache file
    output_path = Path(__file__).parent.parent / 'docs' / 'data' / f'{market_id}_cache.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(cache, f, indent=2)

    print(f"\n✓ Cache generated: {output_path}")
    print(f"  - Version: {cache['version']}")
    print(f"  - Agents: {len(agents_data)}")
    print(f"  - File size: {output_path.stat().st_size / 1024:.1f} KB")

    return cache


def main():
    """Main function to generate cache files for all markets."""
    print("=" * 60)
    print("Pre-computing Frontend Cache")
    print("=" * 60)

    # Load configuration
    config = load_config()

    # Process each market (generate cache even for hidden markets like cn_hour)
    markets = config.get('markets', {})

    for market_id, market_config in markets.items():
        # Generate cache for all markets with data directories, even if UI-disabled
        # This allows 1D/1H toggle to work with cached data
        try:
            generate_cache_for_market(market_id, market_config, config)
        except Exception as e:
            print(f"\n✗ Error generating cache for {market_id}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("Cache generation complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Script to synthesize a crypto index in the same format as QQQ data.

This script:
1. Loads crypto hourly data from the filled JSONL file
2. Accepts user input for total index value and cryptocurrency percentages
3. Calculates weighted index values using open (buy price) and close (sell price)
4. Generates index data in QQQ-compatible format
5. Outputs to a JSON file

Usage: python synthesize_crypto_index.py
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import sys

def load_crypto_data(crypto_file):
    """Load all cryptocurrency data from JSONL file"""
    crypto_data = {}

    print(f"Loading crypto data from {crypto_file}...")
    with open(crypto_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                # Extract crypto symbol from Meta Data
                if 'Meta Data' in doc and '3. Digital Currency Name' in doc['Meta Data']:
                    crypto_name = doc['Meta Data']['3. Digital Currency Name']
                    crypto_symbol = doc['Meta Data'].get('2. Digital Currency Code', crypto_name)

                    # Find all Time Series data for this crypto
                    for key, value in doc.items():
                        if key.startswith('Time Series') and isinstance(value, dict):
                            crypto_data[crypto_name] = {
                                'symbol': crypto_symbol,
                                'name': crypto_name,
                                'time_series': dict(value)  # Convert to regular dict
                            }
                            break
            except Exception as e:
                print(f"Error parsing line {line_num}: {e}")
                continue

    print(f"Loaded data for {len(crypto_data)} cryptocurrencies")
    return crypto_data

def get_common_timestamps(crypto_data):
    """Find common timestamps across all cryptocurrencies"""
    if not crypto_data:
        return []

    # Get timestamps from first crypto
    first_crypto = list(crypto_data.keys())[0]
    common_timestamps = set(crypto_data[first_crypto]['time_series'].keys())

    # Find intersection with all other cryptos
    for crypto_name in crypto_data.keys():
        if crypto_name != first_crypto:
            timestamps = set(crypto_data[crypto_name]['time_series'].keys())
            common_timestamps.intersection_update(timestamps)

    return sorted(common_timestamps)

def validate_percentages(percentages, crypto_data):
    """Validate that percentages match available cryptocurrencies and sum to 100%"""
    total_percentage = sum(percentages.values())

    if abs(total_percentage - 100.0) > 0.01:
        raise ValueError(f"Percentages must sum to 100%. Current sum: {total_percentage:.2f}%")

    for crypto_name in percentages.keys():
        if crypto_name not in crypto_data:
            raise ValueError(f"Cryptocurrency '{crypto_name}' not found in data. Available: {list(crypto_data.keys())}")

def calculate_index_values(crypto_data, common_timestamps, percentages, total_value):
    """Calculate weighted index values for all timestamps"""
    index_values = {}

    print("Calculating index values...")
    for i, timestamp in enumerate(common_timestamps):
        if i % 100 == 0:
            print(f"  Processing {i+1}/{len(common_timestamps)} timestamps...")

        total_open = 0.0
        total_close = 0.0

        valid_timestamps = 0
        for crypto_name, percentage in percentages.items():
            crypto_series = crypto_data[crypto_name]['time_series']

            if timestamp in crypto_series:
                data_point = crypto_series[timestamp]
                buy_price = float(data_point.get('1. buy price', '0'))
                sell_price = float(data_point.get('4. sell price', '0'))

                # Skip if prices are invalid
                if buy_price <= 0 or sell_price <= 0:
                    continue

                valid_timestamps += 1

                # Calculate weighted contribution
                weight = percentage / 100.0
                crypto_value = total_value * weight
                crypto_amount = crypto_value / buy_price  # Amount of crypto to hold

                total_open += crypto_amount * buy_price
                total_close += crypto_amount * sell_price

        # Only store if we have valid data for at least half the cryptos
        if valid_timestamps >= len(percentages) / 2 and total_open > 0 and total_close > 0:
            # Set high/low to 0 to prevent unintended use
            # Only provide meaningful open/close values for weighted index calculation

            # Store in QQQ format (as strings with 4 decimal places)
            index_values[timestamp] = {
                "1. open": f"{total_open:.4f}",
                "2. high": "0.0000",  # Set to 0 to prevent use
                "3. low": "0.0000",   # Set to 0 to prevent use
                "4. close": f"{total_close:.4f}",
                "5. volume": "0"      # No volume calculation for index
            }
        else:
            print(f"    Warning: Skipping {timestamp} - insufficient valid data ({valid_timestamps}/{len(percentages)})")

    print("  Index calculation completed!")
    return index_values

def get_cd5_index_config(crypto_data):
    """Get CD5 index configuration with predefined weights"""
    print("\n" + "="*60)
    print("CD5 CRYPTO INDEX SYNTHESIS")
    print("="*60)

    # CD5 Index weights (as provided)
    cd5_weights = {
        'Bitcoin': 74.56,
        'Ethereum': 15.97,
        'Ripple': 5.20,    # XRP
        'Solana': 3.53,
        'Cardano': 0.76
    }

    print("CD5 Index Composition:")
    print("Effective Date: 2025-10-31")
    print("Index: CD5")
    print(f"{'Ticker':<10} {'Name':<10} {'Weight (%)':<10}")
    print("-" * 35)
    print(f"{'BTC':<10} {'Bitcoin':<10} {cd5_weights['Bitcoin']:>8.2f}")
    print(f"{'ETH':<10} {'Ethereum':<10} {cd5_weights['Ethereum']:>8.2f}")
    print(f"{'XRP':<10} {'XRP':<10} {cd5_weights['Ripple']:>8.2f}")
    print(f"{'SOL':<10} {'Solana':<10} {cd5_weights['Solana']:>8.2f}")
    print(f"{'ADA':<10} {'Cardano':<10} {cd5_weights['Cardano']:>8.2f}")

    # Get total value
    while True:
        try:
            total_value = float(input(f"\nEnter total index value in USDT (default: 100000): ") or "100000")
            if total_value > 0:
                break
            print("Please enter a positive value.")
        except ValueError:
            print("Please enter a valid number.")

    # Validate that all CD5 cryptos are available
    available_cryptos = set(crypto_data.keys())
    required_cryptos = set(cd5_weights.keys())
    missing_cryptos = required_cryptos - available_cryptos

    if missing_cryptos:
        print(f"Error: Required CD5 cryptocurrencies not found in data: {missing_cryptos}")
        print(f"Available: {list(available_cryptos)}")
        return None, None

    print(f"\nCD5 Index Configuration:")
    for crypto_name, weight in cd5_weights.items():
        crypto_value = total_value * (weight / 100.0)
        symbol = crypto_data[crypto_name]['symbol']
        timestamps = len(crypto_data[crypto_name]['time_series'])
        print(f"  {crypto_name} ({symbol}): {weight:.2f}% = ${crypto_value:,.2f} ({timestamps} data points)")

    return total_value, cd5_weights

def generate_index_metadata(index_name, total_value, percentages):
    """Generate metadata for the crypto index"""
    if index_name == "CD5":
        allocation_str = "CD5 Index (BTC: 74.56%, ETH: 15.97%, XRP: 5.20%, SOL: 3.53%, ADA: 0.76%)"
        symbol = "CD5"
    else:
        allocation_str = ", ".join([f"{crypto}: {pct:.1f}%" for crypto, pct in percentages.items()])
        symbol = f"CRYPTO_INDEX_{index_name.upper()}"

    return {
        "1. Information": f"{allocation_str} - Hourly open, high, low, close prices and volume - Total Value: ${total_value:,.0f} USDT",
        "2. Symbol": symbol,
        "3. Last Refreshed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "4. Interval": "60min",
        "5. Output Size": "Full size",
        "6. Time Zone": "UTC"
    }

def save_index_data(index_name, metadata, index_values, output_dir):
    """Save the synthesized index data to JSON file"""
    output_file = output_dir / f"{index_name}_crypto_index.json"

    index_data = {
        "Meta Data": metadata,
        "Time Series (60min)": index_values
    }

    print(f"\nSaving index data to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully saved index data!")
    return output_file

def main():
    """Main function to synthesize crypto index"""
    crypto_file = Path(__file__).parent / "crypto_hourly_merged_filled.jsonl"
    output_dir = Path(__file__).parent

    if not crypto_file.exists():
        print(f"Error: Crypto data file {crypto_file} does not exist!")
        print("Please run fill_crypto_gaps.py first to create the filled crypto data.")
        sys.exit(1)

    print("=" * 60)
    print("CRYPTO INDEX SYNTHESIZER")
    print("Convert crypto data to QQQ-compatible index format")
    print("=" * 60)

    # Load crypto data
    crypto_data = load_crypto_data(crypto_file)

    # Get common timestamps
    common_timestamps = get_common_timestamps(crypto_data)
    if not common_timestamps:
        print("Error: No common timestamps found across cryptocurrencies!")
        sys.exit(1)

    print(f"Found {len(common_timestamps)} common timestamps")
    print(f"Date range: {common_timestamps[0]} to {common_timestamps[-1]}")

    # Get CD5 index configuration
    total_value, percentages = get_cd5_index_config(crypto_data)

    if total_value is None or percentages is None:
        print("Failed to configure CD5 index. Exiting.")
        sys.exit(1)

    # Calculate index values
    print(f"\nCalculating weighted index for total value: ${total_value:,.2f}")
    index_values = calculate_index_values(crypto_data, common_timestamps, percentages, total_value)

    # Generate metadata for CD5 index
    index_name = "CD5"
    metadata = generate_index_metadata(index_name, total_value, percentages)

    # Save index data
    output_file = save_index_data(index_name, metadata, index_values, output_dir)

    # Final summary
    print("\n" + "=" * 60)
    print("SYNTHESIS COMPLETE")
    print("=" * 60)

    print(f"Index name: {index_name}")
    print(f"Total value: ${total_value:,.2f}")
    print(f"Cryptocurrencies: {len(percentages)}")
    print(f"Data points: {len(index_values)}")
    print(f"Date range: {common_timestamps[0]} to {common_timestamps[-1]}")
    print(f"Output file: {output_file}")

    # Show sample values
    print(f"\nSample index values:")
    actual_timestamps = sorted(index_values.keys())
    if len(actual_timestamps) >= 3:
        sample_timestamps = [actual_timestamps[0], actual_timestamps[len(actual_timestamps)//2], actual_timestamps[-1]]
    elif actual_timestamps:
        sample_timestamps = actual_timestamps
    else:
        sample_timestamps = []

    for ts in sample_timestamps:
        values = index_values[ts]
        print(f"  {ts}: Open=${float(values['1. open']):,.2f}, Close=${float(values['4. close']):,.2f}")

if __name__ == "__main__":
    main()
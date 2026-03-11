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
                # Extract crypto symbol from Meta Data (适配现有数据格式)
                if 'Meta Data' in doc and '2. Symbol' in doc['Meta Data']:
                    crypto_symbol = doc['Meta Data']['2. Symbol']
                    # 从symbol中提取币种名称，例如 "BTC-USDT" -> "Bitcoin"
                    crypto_name = {
                        'BTC-USDT': 'Bitcoin',
                        'ETH-USDT': 'Ethereum',
                        'XRP-USDT': 'Ripple',
                        'SOL-USDT': 'Solana',
                        'ADA-USDT': 'Cardano',
                        'SUI-USDT': 'Sui',
                        'LINK-USDT': 'Chainlink',
                        'AVAX-USDT': 'Avalanche',
                        'LTC-USDT': 'Litecoin',
                        'DOT-USDT': 'Polkadot'
                    }.get(crypto_symbol, crypto_symbol.replace('-USDT', ''))

                    # Find Time Series data for this crypto
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

def calculate_index_values(crypto_data, common_timestamps, percentages, total_value, base_date):
    """Calculate weighted index values for all timestamps using a base purchase date"""
    index_values = {}

    print("Calculating index values...")

    # 第一步：根据基准日期的价格计算每个加密货币的数量
    print(f"  Step 1: Calculating crypto amounts based on base date {base_date}...")
    crypto_amounts = {}

    # 计算每个加密货币的固定数量
    for crypto_name, percentage in percentages.items():
        weight = percentage / 100.0
        crypto_value = total_value * weight

        # 使用基准日的开盘价买入
        base_price = float(crypto_data[crypto_name]['time_series'][base_date]['1. buy price'])
        crypto_amounts[crypto_name] = crypto_value / base_price

    print(f"  Fixed crypto amounts calculated:")
    total_units_value = 0.0
    for crypto_name, amount in crypto_amounts.items():
        base_price = float(crypto_data[crypto_name]['time_series'][base_date]['1. buy price'])
        value_at_base = amount * base_price
        total_units_value += value_at_base
        print(f"    {crypto_name}: {amount:.6f} units @ ${base_price} = ${value_at_base:,.2f}")

    print(f"  Total portfolio value at base date: ${total_units_value:,.2f}")

    # 第二步：从基准日期开始计算每天的指数值
    print("  Step 2: Calculating daily index values using fixed amounts...")

    # 找到基准日期在时间序列中的位置
    base_index = common_timestamps.index(base_date)

    for i, timestamp in enumerate(common_timestamps):
        # 只计算基准日期及之后的数据
        if i < base_index:
            continue

        if (i - base_index) % 100 == 0:
            print(f"  Processing {i-base_index+1}/{len(common_timestamps)-base_index} timestamps from base date...")

        total_open_value = 0.0
        total_close_value = 0.0
        valid_timestamps = 0

        for crypto_name, crypto_amount in crypto_amounts.items():
            crypto_series = crypto_data[crypto_name]['time_series']

            if timestamp in crypto_series:
                data_point = crypto_series[timestamp]
                open_price = float(data_point.get('1. buy price', '0'))
                close_price = float(data_point.get('4. sell price', '0'))

                # Skip if essential prices are invalid
                if open_price > 0 and close_price > 0:
                    valid_timestamps += 1
                    # 使用固定的加密货币数量 × 当天价格
                    total_open_value += crypto_amount * open_price
                    total_close_value += crypto_amount * close_price

        # Only store if we have valid data for at least half the cryptos
        if valid_timestamps >= len(crypto_amounts) / 2 and total_close_value > 0:
            # 第一天（基准日），开盘价等于组合价值
            if i == base_index:
                open_value = total_open_value
            else:
                # 其他天，开盘价等于前一天的收盘价
                prev_date = common_timestamps[i-1]
                open_value = float(index_values[prev_date]["4. close"])

            # Store in QQQ format (as strings with 4 decimal places)
            # High/Low设置为0，因为无法准确计算组合的最高/最低价值
            index_values[timestamp] = {
                "1. open": f"{open_value:.4f}",
                "2. high": "0.0000",  # 无法准确计算
                "3. low": "0.0000",   # 无法准确计算
                "4. close": f"{total_close_value:.4f}",
                "5. volume": "0"      # No volume calculation for index
            }
        else:
            print(f"    Warning: Skipping {timestamp} - insufficient valid data ({valid_timestamps}/{len(crypto_amounts)})")

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
    print("Index: CD5")
    print(f"{'Ticker':<10} {'Name':<10} {'Weight (%)':<10}")
    print("-" * 35)
    print(f"{'BTC':<10} {'Bitcoin':<10} {cd5_weights['Bitcoin']:>8.2f}")
    print(f"{'ETH':<10} {'Ethereum':<10} {cd5_weights['Ethereum']:>8.2f}")
    print(f"{'XRP':<10} {'XRP':<10} {cd5_weights['Ripple']:>8.2f}")
    print(f"{'SOL':<10} {'Solana':<10} {cd5_weights['Solana']:>8.2f}")
    print(f"{'ADA':<10} {'Cardano':<10} {cd5_weights['Cardano']:>8.2f}")

    # 获取总价值
    total_value = 50000.0  # 默认值
    print(f"\nTotal Index Value: ${total_value:,.0f} USDT")

    # 选择买入日期
    available_dates = None
    for crypto_name in cd5_weights.keys():
        if crypto_name in crypto_data:
            dates = set(crypto_data[crypto_name]['time_series'].keys())
            if available_dates is None:
                available_dates = dates
            else:
                available_dates.intersection_update(dates)
        else:
            available_dates = set()
            break

    if not available_dates:
        print("Error: No common dates found for all CD5 cryptocurrencies!")
        return None, None

    sorted_dates = sorted(available_dates)
    print(f"Available date range: {sorted_dates[0]} to {sorted_dates[-1]}")

    # 默认使用第一个可用日期作为买入日期，修改为与agent模拟开始时间一致
    base_date = "2025-11-02"  # 修改为agent模拟开始时间，与基准保持一致
    if base_date not in available_dates:
        # 如果指定日期不可用，使用最近的可用日期
        base_date = sorted_dates[0]
        print(f"Specified date not available, using: {base_date}")
    else:
        print(f"Base purchase date: {base_date}")

    # Validate that all CD5 cryptos are available
    available_cryptos = set(crypto_data.keys())
    required_cryptos = set(cd5_weights.keys())
    missing_cryptos = required_cryptos - available_cryptos

    if missing_cryptos:
        print(f"Error: Required CD5 cryptocurrencies not found in data: {missing_cryptos}")
        print(f"Available: {list(available_cryptos)}")
        return None, None

    print(f"\nAsset allocation based on {base_date} prices:")
    for crypto_name, weight in cd5_weights.items():
        crypto_value = total_value * (weight / 100.0)
        symbol = crypto_data[crypto_name]['symbol']

        # 获取基准日的开盘价
        buy_price = float(crypto_data[crypto_name]['time_series'][base_date]['1. buy price'])
        crypto_amount = crypto_value / buy_price

        print(f"  {crypto_name} ({symbol}): {weight:.2f}% = ${crypto_value:,.2f} → {crypto_amount:.6f} units @ ${buy_price}")

    return total_value, cd5_weights, base_date

def generate_index_metadata(index_name, total_value, percentages):
    """Generate metadata for the crypto index"""
    if index_name == "CD5":
        allocation_str = "CD5 Index (BTC: 74.56%, ETH: 15.97%, XRP: 5.20%, SOL: 3.53%, ADA: 0.76%)"
        symbol = "CD5"
    else:
        allocation_str = ", ".join([f"{crypto}: {pct:.1f}%" for crypto, pct in percentages.items()])
        symbol = f"CRYPTO_INDEX_{index_name.upper()}"

    return {
        "1. Information": f"{allocation_str} - Daily open, high, low, close prices and volume - Total Value: ${total_value:,.0f} USDT",
        "2. Symbol": symbol,
        "3. Last Refreshed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "4. Interval": "daily",
        "5. Output Size": "Full size",
        "6. Time Zone": "UTC"
    }

def save_index_data(index_name, metadata, index_values, output_dir):
    """Save the synthesized index data to JSON file"""
    output_file = output_dir / f"{index_name}_crypto_index.json"

    index_data = {
        "Meta Data": metadata,
        "Time Series (Daily)": index_values
    }

    print(f"\nSaving index data to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully saved index data!")
    return output_file

def main():
    """Main function to synthesize crypto index"""
    crypto_file = Path(__file__).parent / "crypto_merged.jsonl"
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
    config_result = get_cd5_index_config(crypto_data)

    if not config_result or len(config_result) != 3:
        print("Failed to configure CD5 index. Exiting.")
        sys.exit(1)

    total_value, percentages, base_date = config_result

    # Calculate index values
    print(f"\nCalculating weighted index for total value: ${total_value:,.2f}")
    index_values = calculate_index_values(crypto_data, common_timestamps, percentages, total_value, base_date)

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
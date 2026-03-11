#!/usr/bin/env python3
"""
Merge crypto daily price JSON files into a single JSONL file with automatic symbol fixing.

This script:
1. Merges individual crypto daily price JSON files into crypto_merged.jsonl
2. Renames price fields (open→buy price, close→sell price)
3. Automatically adds -USDT suffix to crypto symbols (e.g., BTC → BTC-USDT)
4. Creates backups of existing files
5. Verifies the symbol fixes were applied correctly

Usage:
    python merge_crypto_jsonl.py

The individual crypto files should be located in the 'coin/' subdirectory
and follow the naming pattern: daily_prices_{SYMBOL}.json
"""

import glob
import json
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Major cryptocurrencies against USDT (using USD as proxy on Alpha Vantage)
crypto_symbols_usdt = [
    "BTC",   # Bitcoin/USDT
    "ETH",   # Ethereum/USDT
    "XRP",   # Ripple/USDT
    "SOL",   # Solana/USDT
    "ADA",   # Cardano/USDT
    "SUI",   # Sui/USDT
    "LINK",  # Chainlink/USDT
    "AVAX",  # Avalanche/USDT
    "LTC",   # Litecoin/USDT
    "DOT",   # Polkadot/USDT
]

def backup_crypto_data():
    """Create a backup of the existing crypto_merged.jsonl file if it exists"""
    crypto_file = Path(output_file)
    backup_file = Path(output_file + ".backup")

    if crypto_file.exists():
        shutil.copy2(crypto_file, backup_file)
        print(f"✅ Created backup: {backup_file}")
        return True
    else:
        print(f"ℹ️  No existing file to backup: {crypto_file}")
        return False

def verify_symbol_fixes():
    """Verify that all symbols in the merged file have -USDT suffix"""
    crypto_file = Path(output_file)

    print("\n🔍 Verifying symbol fixes...")

    if not crypto_file.exists():
        print(f"❌ File not found: {crypto_file}")
        return False

    try:
        symbols_found = set()
        usdt_count = 0
        total_lines = 0
        transformations = {}

        with open(crypto_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line.strip())
                    meta = data.get("Meta Data", {})
                    symbol = meta.get("2. Symbol", "")

                    if symbol:
                        symbols_found.add(symbol)
                        total_lines += 1

                        if symbol.endswith("-USDT"):
                            usdt_count += 1
                        else:
                            # Record symbols that need fixing
                            base_symbol = symbol.replace("-USDT", "")
                            transformations[symbol] = f"{base_symbol}-USDT"

                        if line_num <= 5:  # Show first few examples
                            print(f"  Line {line_num}: {symbol}")

                    if line_num == 10:  # Stop after showing examples
                        break

                except json.JSONDecodeError:
                    continue

        print(f"\n✅ Verification Results:")
        print(f"  📊 Total symbols checked: {total_lines}")
        print(f"  🎯 Symbols with -USDT: {usdt_count}")
        print(f"  📈 Unique symbols: {len(symbols_found)}")

        if transformations:
            print(f"  ⚠️  Symbols that need fixing: {len(transformations)}")
            for original, new in sorted(transformations.items())[:5]:  # Show first 5
                print(f"    {original} → {new}")

        if usdt_count == total_lines and total_lines > 0:
            print("  ✅ All symbols have -USDT suffix!")
            return True
        else:
            print(f"  ⚠️  Only {usdt_count}/{total_lines} symbols have -USDT suffix")
            return False

    except Exception as e:
        print(f"❌ Error during verification: {e}")
        return False

# Merge all crypto daily price JSON files, write one line per file to crypto_merged.jsonl
current_dir = os.path.dirname(__file__)
assert (Path(current_dir) / "coin").exists(), "coin/ directory not found!"
pattern = os.path.join(current_dir, "coin", "daily_prices_*.json")
files = sorted(glob.glob(pattern))
assert files, "No crypto daily price files found to merge!"
output_file = os.path.join(current_dir, "crypto_merged.jsonl")

print(f"Found {len(files)} crypto files to merge")
print(f"Output file: {output_file}")

# Create backup of existing file if it exists
backup_crypto_data()

with open(output_file, "w", encoding="utf-8") as fout:
    for fp in files:
        basename = os.path.basename(fp)
        print(f"Processing: {basename}")

        # Only process files that contain our crypto symbols
        if not any(symbol in basename for symbol in crypto_symbols_usdt):
            print(f"  Skipping: {basename} (not in crypto symbols list)")
            continue

        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Rename fields: "1. open" -> "1. buy price"；"4. close" -> "4. sell price"
        # For the latest date, only keep "1. buy price"
        # Also fix crypto symbols by adding -USDT suffix
        try:
            # Find all keys starting with "Time Series"
            series = None
            for key, value in data.items():
                if key.startswith("Time Series"):
                    series = value
                    break

            if isinstance(series, dict) and series:
                # First rename fields for all dates
                for d, bar in list(series.items()):
                    if not isinstance(bar, dict):
                        continue
                    if "1. open" in bar:
                        bar["1. buy price"] = bar.pop("1. open")
                    if "4. close" in bar:
                        bar["4. sell price"] = bar.pop("4. close")

                # Then process latest date, keep only buy price
                latest_date = max(series.keys())
                latest_bar = series.get(latest_date, {})
                if isinstance(latest_bar, dict):
                    buy_val = latest_bar.get("1. buy price")
                    series[latest_date] = {"1. buy price": buy_val} if buy_val is not None else {}

                # Update Meta Data description and fix symbol
                meta = data.get("Meta Data", {})
                if isinstance(meta, dict):
                    meta["1. Information"] = "Daily Prices (buy price, high, low, sell price) and Volumes"

                    # Fix crypto symbol by adding -USDT suffix
                    original_symbol = meta.get("2. Symbol", "")
                    if original_symbol and not original_symbol.endswith("-USDT"):
                        new_symbol = f"{original_symbol}-USDT"
                        meta["2. Symbol"] = new_symbol

                        # Also update the information field
                        if "1. Information" in meta and original_symbol in meta["1. Information"]:
                            meta["1. Information"] = meta["1. Information"].replace(original_symbol, new_symbol)

                        print(f"  Fixed symbol: {original_symbol} → {new_symbol}")

        except Exception as e:
            print(f"  Error processing {basename}: {e}")
            # If structure error, write as-is
            pass

        # Write to merged file
        fout.write(json.dumps(data, ensure_ascii=False) + "\n")
        print(f"  Added to merged file")

print(f"\nCrypto merge complete! Output saved to: {output_file}")
processed_count = len([f for f in files if any(symbol in os.path.basename(f) for symbol in crypto_symbols_usdt)])
print(f"Total symbols processed: {processed_count}")

# Verify that symbol fixes were applied correctly
verify_symbol_fixes()
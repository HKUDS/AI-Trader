"""
Merge Crypto JSON files into unified JSONL format

Convert individual symbol JSON files into a single JSONL file
compatible with the trading system
"""

import json
from pathlib import Path
from typing import List, Dict, Any


def merge_crypto_data(
    input_dir: str = "./data/crypto",
    output_file: str = "./data/crypto/merged.jsonl"
):
    """
    Merge all crypto JSON files into unified JSONL
    
    Args:
        input_dir: Directory containing JSON files
        output_file: Output JSONL file path
    """
    input_path = Path(input_dir)
    output_path = Path(output_file)
    
    # Find all JSON files
    json_files = list(input_path.glob("ohlcv_*.json"))
    
    if not json_files:
        print(f"⚠️ No JSON files found in {input_dir}")
        return
    
    print(f"📊 Found {len(json_files)} JSON files to merge")
    
    merged_count = 0
    
    with open(output_path, 'w') as outfile:
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                symbol = data.get('symbol', '')
                timeframe = data.get('timeframe', '')
                candles = data.get('data', [])
                
                if not candles:
                    continue
                
                # Convert to time series format
                time_series = {}
                for candle in candles:
                    dt = candle['datetime']
                    time_series[dt] = {
                        'open': candle['open'],
                        'high': candle['high'],
                        'low': candle['low'],
                        'close': candle['close'],
                        'volume': candle['volume']
                    }
                
                # Create merged entry
                merged_entry = {
                    'symbol': symbol,
                    'exchange': data.get('exchange', 'bybit'),
                    'timeframe': timeframe,
                    'time_series': time_series
                }
                
                # Write as JSONL
                json.dump(merged_entry, outfile)
                outfile.write('\n')
                
                merged_count += 1
                print(f"✅ Merged {symbol}: {len(candles)} candles")
                
            except Exception as e:
                print(f"❌ Failed to merge {json_file}: {e}")
    
    print(f"\n✅ Merged {merged_count} symbols into {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Merge crypto data to JSONL")
    parser.add_argument("--input", default="./data/crypto", help="Input directory")
    parser.add_argument("--output", default="./data/crypto/merged.jsonl", help="Output file")
    
    args = parser.parse_args()
    
    merge_crypto_data(args.input, args.output)
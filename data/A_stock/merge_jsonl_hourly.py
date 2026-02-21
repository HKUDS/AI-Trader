"""
A股小时级数据转JSONL格式脚本

功能：
1. 从 A_stock_hourly.csv 读取60分钟K线数据
2. 转换为与 Alpha Vantage 格式兼容的 JSONL 格式
3. 每只股票一行JSON，包含 Meta Data 和 Time Series (60min)

依赖：
- pandas: 数据处理库

作者: AI-Trader
日期: 2025-11-16
"""

import json
from pathlib import Path
from typing import Dict

import pandas as pd


def convert_hourly_to_jsonl(
    csv_path: str = "A_stock_data/A_stock_hourly.csv",
    output_path: str = "merged_hourly.jsonl",
    stock_name_csv: str = "A_stock_data/sse_50_weight.csv",
) -> None:
    """Convert A-share hourly CSV data to JSONL format compatible with the trading system.

    The output format matches the Alpha Vantage intraday format:
    - Each line is a JSON object for one stock
    - Contains "Meta Data" and "Time Series (60min)" fields
    - Uses "1. buy price" (open), "2. high", "3. low", "4. sell price" (close), "5. volume"
    - Includes stock name from sse_50_weight.csv for better AI understanding

    Args:
        csv_path: Path to the A-share hourly price CSV file (default: A_stock_data/A_stock_hourly.csv)
        output_path: Path to output JSONL file (default: merged_hourly.jsonl - current directory)
        stock_name_csv: Path to SSE 50 weight CSV containing stock names (default: A_stock_data/sse_50_weight.csv)
    """
    csv_path = Path(csv_path)
    output_path = Path(output_path)
    stock_name_csv = Path(stock_name_csv)

    if not csv_path.exists():
        print(f"❌ Error: CSV file not found: {csv_path}")
        return

    print(f"📖 Reading CSV file: {csv_path}")

    # Read CSV data
    df = pd.read_csv(csv_path)

    # Read stock name mapping
    stock_name_map = {}
    if stock_name_csv.exists():
        print(f"📖 Reading stock names from: {stock_name_csv}")
        name_df = pd.read_csv(stock_name_csv)
        # Create mapping from con_code (stock_code) to stock_name
        stock_name_map = dict(zip(name_df["con_code"], name_df["stock_name"]))
        print(f"✅ Loaded {len(stock_name_map)} stock names")
    else:
        print(f"⚠️  Warning: Stock name file not found: {stock_name_csv}")

    print(f"📊 Total records: {len(df)}")
    print(f"📋 Columns: {df.columns.tolist()}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Group by stock symbol
    grouped = df.groupby("stock_code")

    print(f"🔄 Processing {len(grouped)} stocks...")

    with open(output_path, "w", encoding="utf-8") as fout:
        for stock_code, group_df in grouped:
            # Sort by datetime ascending
            group_df = group_df.sort_values("trade_date", ascending=True)

            # Get latest datetime for Meta Data
            latest_datetime = str(group_df["trade_date"].max())

            # Build Time Series (60min) data
            time_series = {}

            for idx, row in group_df.iterrows():
                datetime_str = str(row["trade_date"])  # Format: "2025-10-09 10:30"
                
                # Add :00 seconds if not present (e.g., "10:30" -> "10:30:00", "14:00" -> "14:00:00")
                if datetime_str.count(':') == 1:
                    datetime_formatted = datetime_str + ":00"
                else:
                    datetime_formatted = datetime_str

                # For the latest datetime, only include buy price (to prevent future information leakage)
                if datetime_str == latest_datetime:
                    time_series[datetime_formatted] = {
                        "1. buy price": str(row["open"])
                    }
                else:
                    time_series[datetime_formatted] = {
                        "1. buy price": str(row["open"]),
                        "2. high": str(row["high"]),
                        "3. low": str(row["low"]),
                        "4. sell price": str(row["close"]),
                        "5. volume": str(int(row["volume"])) if pd.notna(row["volume"]) else "0",
                    }

            # Get stock name from mapping
            stock_name = stock_name_map.get(stock_code, "Unknown")

            # Build complete JSON object
            json_obj = {
                "Meta Data": {
                    "1. Information": "Intraday (60min) open, high, low, close prices and volume",
                    "2. Symbol": stock_code,
                    "2.1. Name": stock_name,
                    "3. Last Refreshed": latest_datetime,
                    "4. Interval": "60min",
                    "5. Output Size": "Full size",
                    "6. Time Zone": "Asia/Shanghai",
                },
                "Time Series (60min)": time_series,
            }

            # Write to JSONL file
            fout.write(json.dumps(json_obj, ensure_ascii=False) + "\n")

    print(f"✅ Data conversion completed: {output_path}")
    print(f"✅ Total stocks: {len(grouped)}")
    print(f"✅ File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    # Convert A-share hourly data to JSONL format
    print("=" * 60)
    print("A-Share Hourly Data Converter")
    print("=" * 60)
    convert_hourly_to_jsonl()
    print("=" * 60)


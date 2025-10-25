import json
import os
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def convert_a_stock_to_jsonl(
    csv_path: str = "./A_stock/daily_prices_sse_50.csv", output_path: str = "./A_stock/merged.jsonl"
) -> None:
    """Convert A-share CSV data to JSONL format compatible with the trading system.

    The output format matches the Alpha Vantage format used for NASDAQ data:
    - Each line is a JSON object for one stock
    - Contains "Meta Data" and "Time Series (Daily)" fields
    - Uses "1. buy price" (open), "2. high", "3. low", "4. sell price" (close), "5. volume"

    Args:
        csv_path: Path to the A-share daily price CSV file
        output_path: Path to output JSONL file
    """
    csv_path = Path(csv_path)
    output_path = Path(output_path)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return

    print(f"Reading CSV file: {csv_path}")

    # Read CSV data
    df = pd.read_csv(csv_path)

    print(f"Total records: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Group by stock symbol
    grouped = df.groupby("ts_code")

    print(f"Processing {len(grouped)} stocks...")

    with open(output_path, "w", encoding="utf-8") as fout:
        for ts_code, group_df in grouped:
            # Sort by date ascending
            group_df = group_df.sort_values("trade_date", ascending=True)

            # Get latest date for Meta Data
            latest_date = str(group_df["trade_date"].max())
            latest_date_formatted = f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:]}"

            # Build Time Series (Daily) data
            time_series = {}

            for idx, row in group_df.iterrows():
                date_str = str(row["trade_date"])
                date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

                # For the latest date, only include buy price (to prevent future information leakage)
                if date_str == latest_date:
                    time_series[date_formatted] = {"1. buy price": str(row["open"])}
                else:
                    time_series[date_formatted] = {
                        "1. buy price": str(row["open"]),
                        "2. high": str(row["high"]),
                        "3. low": str(row["low"]),
                        "4. sell price": str(row["close"]),
                        "5. volume": (
                            str(int(row["vol"] * 100)) if pd.notna(row["vol"]) else "0"
                        ),  # Convert to shares (vol is in 手, 1手=100股)
                    }

            # Build complete JSON object
            json_obj = {
                "Meta Data": {
                    "1. Information": "Daily Prices (buy price, high, low, sell price) and Volumes",
                    "2. Symbol": ts_code,
                    "3. Last Refreshed": latest_date_formatted,
                    "4. Output Size": "Full",
                    "5. Time Zone": "Asia/Shanghai",
                },
                "Time Series (Daily)": time_series,
            }

            # Write to JSONL file
            fout.write(json.dumps(json_obj, ensure_ascii=False) + "\n")

    print(f"✅ Data conversion completed: {output_path}")
    print(f"✅ Total stocks: {len(grouped)}")
    print(f"✅ File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    # Convert A-share data to JSONL format
    print("=" * 60)
    print("A-Share Data Converter")
    print("=" * 60)
    convert_a_stock_to_jsonl()
    print("=" * 60)

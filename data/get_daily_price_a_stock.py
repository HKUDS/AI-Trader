import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

load_dotenv()


def get_last_month_dates() -> tuple[str, str]:
    """Get the first and last day of last month.

    Returns:
        tuple[str, str]: (start_date, end_date) in 'YYYYMMDD' format
    """
    today = datetime.now()
    first_day_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_day_of_this_month - timedelta(days=1)
    first_day_of_last_month = last_day_of_last_month.replace(day=1)

    start_date = first_day_of_last_month.strftime("%Y%m%d")
    end_date = last_day_of_last_month.strftime("%Y%m%d")

    return start_date, end_date


def calculate_batch_days(num_stocks: int, max_records: int = 6000) -> int:
    """Calculate how many days of data can be fetched per batch.

    Args:
        num_stocks: Number of stocks to fetch
        max_records: Maximum records per API call (default: 6000)

    Returns:
        int: Number of days per batch
    """
    return max(1, max_records // num_stocks)


def get_daily_price_a_stock(
    index_code: str = "000016.SH",
    output_dir: Optional[Path] = None,
    daily_start_date: str = "20250101",
    fallback_csv: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    """Get daily price data for A-share index constituents.

    Args:
        index_code: Index code, default is SSE 50 (000016.SH)
        output_dir: Output directory, defaults to './data/A_stock' if None
        daily_start_date: Start date for daily price data in 'YYYYMMDD' format
        fallback_csv: Fallback CSV file path for index constituents

    Returns:
        pd.DataFrame: DataFrame containing daily price data, None if failed
    """
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("Error: TUSHARE_TOKEN not found")
        return None

    ts.set_token(token)
    pro = ts.pro_api()

    # Get index constituents from last month
    index_start_date, index_end_date = get_last_month_dates()

    # Daily price data from daily_start_date to today
    daily_end_date = datetime.now().strftime("%Y%m%d")

    try:
        df = pro.index_weight(index_code=index_code, start_date=index_start_date, end_date=index_end_date)

        # If API returns empty data, try to read from fallback CSV
        if df.empty:
            if fallback_csv and Path(fallback_csv).exists():
                print(f"API returned empty data, reading from fallback: {fallback_csv}")
                df = pd.read_csv(fallback_csv)
            else:
                print(f"No index constituent data found for {index_code}")
                return None

        code_list = df["con_code"].tolist()
        code_str = ",".join(code_list)
        num_stocks = len(code_list)

        # Calculate batch size based on 6000 records limit
        batch_days = calculate_batch_days(num_stocks)

        # Parse dates
        start_dt = datetime.strptime(daily_start_date, "%Y%m%d")
        end_dt = datetime.strptime(daily_end_date, "%Y%m%d")

        all_data = []
        current_start = start_dt

        while current_start <= end_dt:
            current_end = min(current_start + timedelta(days=batch_days - 1), end_dt)

            batch_start_str = current_start.strftime("%Y%m%d")
            batch_end_str = current_end.strftime("%Y%m%d")

            df_batch = pro.daily(ts_code=code_str, start_date=batch_start_str, end_date=batch_end_str)

            if not df_batch.empty:
                all_data.append(df_batch)

            current_start = current_end + timedelta(days=1)

        if not all_data:
            print("No daily price data found")
            return None

        df2 = pd.concat(all_data, ignore_index=True)

        # Sort by trade_date and ts_code in ascending order
        df2 = df2.sort_values(by=["trade_date", "ts_code"], ascending=True).reset_index(drop=True)

        if output_dir is None:
            # Use absolute path relative to script location
            output_dir = Path(__file__).parent / "A_stock"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Simplified filename
        index_name = "sse_50" if index_code == "000016.SH" else index_code.replace(".", "_")
        daily_file = output_dir / f"daily_prices_{index_name}.csv"
        df2.to_csv(daily_file, index=False, encoding="utf-8")
        print(f"Data saved to: {daily_file} (shape: {df2.shape})")

        return df2

    except Exception as e:
        print(f"Error: {str(e)}")
        return None


if __name__ == "__main__":
    fallback_path = Path(__file__).parent / "A_stock" / "sse_50_weight.csv"

    df = get_daily_price_a_stock(index_code="000016.SH", daily_start_date="20250101", fallback_csv=fallback_path)

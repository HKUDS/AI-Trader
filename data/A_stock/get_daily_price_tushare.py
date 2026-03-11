import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

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


def api_call_with_retry(api_func, pro_api_instance, max_retries: int = 3, retry_delay: int = 5, timeout: int = 120, **kwargs):
    """Call tushare API with retry mechanism and timeout handling.
    
    Args:
        api_func: The tushare API function to call
        pro_api_instance: The tushare pro_api instance (needed to set timeout)
        max_retries: Maximum number of retry attempts
        retry_delay: Delay in seconds between retries
        timeout: Request timeout in seconds
        **kwargs: Arguments to pass to the API function
        
    Returns:
        Result from the API call
        
    Raises:
        Exception: If all retries fail
    """
    import requests
    
    # Set timeout for the pro_api instance's underlying requests session
    if hasattr(pro_api_instance, 'api') and hasattr(pro_api_instance.api, 'timeout'):
        pro_api_instance.api.timeout = timeout
    
    for attempt in range(1, max_retries + 1):
        try:
            result = api_func(**kwargs)
            return result
            
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout, 
                requests.exceptions.ConnectionError) as e:
            if attempt < max_retries:
                wait_time = retry_delay * attempt
                print(f"⚠️ 网络超时错误 (尝试 {attempt}/{max_retries})，等待 {wait_time} 秒后重试...")
                print(f"错误详情: {str(e)}")
                time.sleep(wait_time)
            else:
                print(f"❌ 所有重试尝试均失败")
                raise
        except Exception as e:
            # Check if it's a timeout-related error in the error message
            error_str = str(e).lower()
            if 'timeout' in error_str or 'timed out' in error_str or 'read timeout' in error_str:
                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    print(f"⚠️ 网络超时错误 (尝试 {attempt}/{max_retries})，等待 {wait_time} 秒后重试...")
                    print(f"错误详情: {str(e)}")
                    time.sleep(wait_time)
                else:
                    print(f"❌ 所有重试尝试均失败")
                    raise
            else:
                # For other errors, also retry
                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    print(f"⚠️ API 调用错误 (尝试 {attempt}/{max_retries})，等待 {wait_time} 秒后重试...")
                    print(f"错误详情: {str(e)}")
                    time.sleep(wait_time)
                else:
                    print(f"❌ 所有重试尝试均失败")
                    raise
    
    raise Exception("所有重试尝试均失败")


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
    
    # Set timeout for tushare API requests (increase to 120 seconds)
    if hasattr(pro, 'api') and hasattr(pro.api, 'timeout'):
        pro.api.timeout = 120

    # Get index constituents from last month
    index_start_date, index_end_date = get_last_month_dates()

    # Daily price data from daily_start_date to today
    daily_end_date = datetime.now().strftime("%Y%m%d")

    try:
        print(f"正在获取指数成分股数据: {index_code} ({index_start_date} - {index_end_date})")
        df = api_call_with_retry(
            pro.index_weight,
            pro_api_instance=pro,
            index_code=index_code,
            start_date=index_start_date,
            end_date=index_end_date,
            timeout=120
        )

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
        total_batches = ((end_dt - start_dt).days // batch_days) + 1
        batch_num = 0

        while current_start <= end_dt:
            current_end = min(current_start + timedelta(days=batch_days - 1), end_dt)

            batch_start_str = current_start.strftime("%Y%m%d")
            batch_end_str = current_end.strftime("%Y%m%d")
            batch_num += 1

            print(f"正在获取批次 {batch_num}/{total_batches}: {batch_start_str} - {batch_end_str}")
            
            df_batch = api_call_with_retry(
                pro.daily,
                pro_api_instance=pro,
                ts_code=code_str,
                start_date=batch_start_str,
                end_date=batch_end_str,
                timeout=120
            )

            if not df_batch.empty:
                all_data.append(df_batch)
                print(f"✅ 批次 {batch_num} 获取成功，获得 {len(df_batch)} 条记录")

            # Add delay between batches to avoid rate limiting
            if current_start < end_dt:
                time.sleep(1)  # 1 second delay between batches

            current_start = current_end + timedelta(days=1)

        if not all_data:
            print("No daily price data found")
            return None

        df2 = pd.concat(all_data, ignore_index=True)

        # Sort by trade_date and ts_code in ascending order
        df2 = df2.sort_values(by=["trade_date", "ts_code"], ascending=True).reset_index(drop=True)

        if output_dir is None:
            # Use A_stock_data subdirectory as default
            output_dir = Path(__file__).parent / "A_stock_data"
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


def convert_index_daily_to_json(
    df: pd.DataFrame,
    symbol: str = "000016.SH",
    output_file: Optional[Path] = None,
) -> Dict:
    """Convert index daily data to JSON format similar to Alpha Vantage format.

    Args:
        df: DataFrame from pro.index_daily() with columns: ts_code, trade_date, close, open, high, low, pre_close, change, pct_chg, vol, amount
        symbol: Index symbol
        output_file: Output JSON file path, if None will not save to file

    Returns:
        Dict: JSON-formatted data
    """
    if df.empty:
        print("Warning: Empty DataFrame provided")
        return {}

    # Sort by trade_date in descending order (latest first)
    df = df.sort_values(by="trade_date", ascending=False).reset_index(drop=True)

    # Get the last refreshed date
    last_refreshed = df.iloc[0]["trade_date"]
    last_refreshed_formatted = f"{last_refreshed[:4]}-{last_refreshed[4:6]}-{last_refreshed[6:]}"

    # Build the JSON structure
    json_data = {
        "Meta Data": {
            "1. Information": "Daily Prices (open, high, low, close) and Volumes",
            "2. Symbol": symbol,
            "3. Last Refreshed": last_refreshed_formatted,
            "4. Output Size": "Compact",
            "5. Time Zone": "Asia/Shanghai",
        },
        "Time Series (Daily)": {},
    }

    # Convert each row to the time series format
    for _, row in df.iterrows():
        trade_date = row["trade_date"]
        date_formatted = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

        json_data["Time Series (Daily)"][date_formatted] = {
            "1. open": f"{row['open']:.4f}",
            "2. high": f"{row['high']:.4f}",
            "3. low": f"{row['low']:.4f}",
            "4. close": f"{row['close']:.4f}",
            "5. volume": str(int(row["vol"])) if pd.notna(row["vol"]) else "0",
        }

    # Save to file if output_file is specified
    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4, ensure_ascii=False)
        print(f"JSON data saved to: {output_file}")

    return json_data


def get_index_daily_data(
    index_code: str = "000016.SH",
    start_date: str = "20250101",
    end_date: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    """Get index daily data and convert to JSON format.

    Args:
        index_code: Index code, default is SSE 50 (000016.SH)
        start_date: Start date in 'YYYYMMDD' format
        end_date: End date in 'YYYYMMDD' format, defaults to today if None
        output_dir: Output directory, defaults to './data/A_stock' if None

    Returns:
        pd.DataFrame: DataFrame containing index daily data, None if failed
    """
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("Error: TUSHARE_TOKEN not found")
        return None

    ts.set_token(token)
    pro = ts.pro_api()
    
    # Set timeout for tushare API requests (increase to 120 seconds)
    if hasattr(pro, 'api') and hasattr(pro.api, 'timeout'):
        pro.api.timeout = 120

    # Set end_date to today if not specified
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    try:
        print(f"正在获取指数日线数据: {index_code} ({start_date} - {end_date})")
        df = api_call_with_retry(
            pro.index_daily,
            pro_api_instance=pro,
            ts_code=index_code,
            start_date=start_date,
            end_date=end_date,
            timeout=120
        )

        if df.empty:
            print(f"No index daily data found for {index_code}")
            return None

        if output_dir is None:
            output_dir = Path(__file__).parent
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        index_name = "sse_50" if index_code == "000016.SH" else index_code.replace(".", "_")
        json_file = output_dir / f"index_daily_{index_name}.json"
        convert_index_daily_to_json(df, symbol=index_code, output_file=json_file)

        return df

    except Exception as e:
        print(f"Error: {str(e)}")
        return None


if __name__ == "__main__":
    fallback_path = Path(__file__).parent / "A_stock_data" / "sse_50_weight.csv"

    # Get constituent stocks daily prices
    df = get_daily_price_a_stock(index_code="000016.SH", daily_start_date="20251001", fallback_csv=fallback_path)

    # Get index daily data and convert to JSON
    print("\n" + "=" * 50)
    print("Fetching index daily data...")
    print("=" * 50)
    df_index = get_index_daily_data(index_code="000016.SH", start_date="20251001")

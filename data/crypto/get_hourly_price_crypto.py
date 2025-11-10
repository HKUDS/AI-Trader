import os
import time
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Major cryptocurrencies against USDT (using USD as proxy on Alpha Vantage)
crypto_symbols_usdt = [
    "BTC",   # Bitcoin/USDT
    "ETH",   # Ethereum/USDT
    "XRP",   # Ripple/USDT
    "SOL",   # Solana/USDT
    "ADA",   # Cardano/USDT
    # "SUI",   # Sui/USDT # remove due to no USDT market data
    "LINK",  # Chainlink/USDT
    "AVAX",  # Avalanche/USDT
    # "LTC",   # Litecoin/USDT # remove due to no USDT market data
    "DOT",   # Polkadot/USDT
]


def update_json(data: dict, SYMBOL: str):
    """Update JSON file with new hourly data, merging with existing data"""
    # Ensure the 'coin' folder exists relative to this script's directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    coin_dir = os.path.join(current_dir, "coin")
    os.makedirs(coin_dir, exist_ok=True)

    file_path = f'{coin_dir}/hourly_prices_{SYMBOL}.json'

    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                old_data = json.load(f)

            # Merge new and old "Time Series (60min)", new data takes priority
            old_ts = old_data.get("Time Series (60min)", {})
            new_ts = data.get("Time Series (60min)", {})
            merged_ts = {**old_ts, **new_ts}  # New data overwrites old data for same timestamps

            # Create new data dictionary, avoid directly modifying the passed data
            merged_data = data.copy()
            merged_data["Time Series (60min)"] = merged_ts

            # If new data doesn't have Meta Data, keep old Meta Data
            if "Meta Data" not in merged_data and "Meta Data" in old_data:
                merged_data["Meta Data"] = old_data["Meta Data"]

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=4)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    except (IOError, json.JSONDecodeError, KeyError) as e:
        print(f"Error when updating {SYMBOL}: {e}")
        raise


def get_crypto_hourly_price(SYMBOL: str, month: str = None):
    """
    Get hourly cryptocurrency price data from Alpha Vantage

    Args:
        SYMBOL: Crypto symbol (e.g., 'BTC', 'ETH')
        month: Optional month in YYYY-MM format (e.g., '2025-10')
    """
    FUNCTION = "CRYPTO_INTRADAY"
    INTERVAL = "60min"
    OUTPUTSIZE = 'full'  # Get full length intraday time series
    MARKET = "USDT"  # Market for cryptocurrency trading (USDT equivalent)
    APIKEY = os.getenv("ALPHAADVANTAGE_API_KEY")

    if not APIKEY:
        print("Error: ALPHAADVANTAGE_API_KEY not found in environment variables")
        return None

    # Build URL for cryptocurrency intraday data
    url = f'https://www.alphavantage.co/query?function={FUNCTION}&symbol={SYMBOL}&market={MARKET}&interval={INTERVAL}&outputsize={OUTPUTSIZE}&apikey={APIKEY}'

    # Note: CRYPTO_INTRADAY doesn't support month parameter like TIME_SERIES_INTRADAY
    # It returns recent intraday data by default

    try:
        print(f"Fetching hourly data for {SYMBOL}/{MARKET}...")
        # Note: month parameter is not supported by CRYPTO_INTRADAY API
        r = requests.get(url)
        data = r.json()

        # Print response for debugging
        print(f"Response for {SYMBOL}: {data}")

        if data.get("Note") is not None or data.get("Information") is not None:
            print(f"API Error for {SYMBOL}: {data.get('Note', data.get('Information', 'Unknown error'))}")
            return None

        # Check if we got valid time series data - handle different key formats
        time_series_key = None
        for key in data.keys():
            if "Time Series" in key:
                time_series_key = key
                break

        if not time_series_key:
            print(f"No hourly time series data found for {SYMBOL}")
            print(f"Available keys in response: {list(data.keys())}")
            return None

        # Rename the key to standard format if needed
        if time_series_key != "Time Series (60min)":
            data["Time Series (60min)"] = data.pop(time_series_key)

        update_json(data, SYMBOL)
        print(f"Successfully saved hourly data for {SYMBOL}")
        return data

    except requests.exceptions.RequestException as e:
        print(f"Network error fetching {SYMBOL}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error for {SYMBOL}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching {SYMBOL}: {e}")
        return None


def get_all_crypto_hourly_prices(symbols_list=None, delay_seconds=12):
    """
    Get hourly prices for all cryptocurrencies with rate limiting

    Args:
        symbols_list: List of crypto symbols, defaults to crypto_symbols_usdt
        delay_seconds: Delay between API calls (default: 12 seconds for rate limits)
    """
    if symbols_list is None:
        symbols_list = crypto_symbols_usdt

    print(f"Starting crypto hourly price collection for {len(symbols_list)} symbols...")
    print(f"Using {delay_seconds} second delay between calls to respect API rate limits")
    print("Note: CRYPTO_INTRADAY API returns most recent data, not historical data")

    successful = 0
    failed = 0
    failed_symbols = []  # Track failed symbols

    for i, symbol in enumerate(symbols_list, 1):
        print(f"\n[{i}/{len(symbols_list)}] Processing {symbol}...")

        result = get_crypto_hourly_price(symbol)

        if result:
            successful += 1
        else:
            failed += 1
            failed_symbols.append(symbol)

        # Add delay between API calls except for the last one
        if i < len(symbols_list):
            print(f"Waiting {delay_seconds} seconds before next request...")
            time.sleep(delay_seconds)

    print(f"\n" + "="*50)
    print(f"Summary: {successful} successful, {failed} failed")
    if failed_symbols:
        print(f"Failed symbols (no USDT market data): {', '.join(failed_symbols)}")
        print("These symbols should be removed from the crypto_symbols_usdt list")
    print(f"Data collected: Most recent intraday data")
    print(f"Rate limit: {delay_seconds}s delay between calls")
    print("="*50)


if __name__ == "__main__":
    # Download hourly crypto data (most recent data)
    print("Fetching hourly cryptocurrency data (most recent)...")

    # Test with BTC first
    # test_symbols = ["BTC"]
    # print("Testing with BTC first...")
    # get_all_crypto_hourly_prices(test_symbols, delay_seconds=12)

    # If BTC test is successful, uncomment to get all symbols
    get_all_crypto_hourly_prices(crypto_symbols_usdt, delay_seconds=12)
import os
import time
import json
import requests
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Load crypto configuration
def load_crypto_config():
    """Load crypto configuration from JSON file"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_config.json")

    if not os.path.exists(config_path):
        print(f"Error: crypto_config.json not found at {config_path}")
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"Loaded crypto configuration from {config_path}")
        return config
    except Exception as e:
        print(f"Error loading crypto config: {e}")
        return None

# Get global config variable
crypto_config = load_crypto_config()

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

# Use symbols from config if available
if crypto_config and "symbols" in crypto_config:
    crypto_symbols_usdt = crypto_config["symbols"]
    print(f"Using symbols from config: {crypto_symbols_usdt}")


def backup_data(path):
    """Create backup of file or directory by adding _backup suffix"""
    if not os.path.exists(path):
        return False

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}_backup_{timestamp}"

        if os.path.isfile(path):
            shutil.copy2(path, backup_path)
            print(f"Created file backup: {backup_path}")
        elif os.path.isdir(path):
            if os.path.exists(backup_path):
                shutil.rmtree(backup_path)
            shutil.copytree(path, backup_path)
            print(f"Created directory backup: {backup_path}")

        return True
    except Exception as e:
        print(f"Error creating backup for {path}: {e}")
        return False


def backup_coin_directory_if_needed():
    """Backup the entire coin directory if configured"""
    coin_folder = get_config_value("file_paths.coin_folder", "coin")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    coin_dir = os.path.join(current_dir, coin_folder)

    if os.path.exists(coin_dir):
        return backup_data(coin_dir)

    return False


def get_config_value(key, default=None):
    """Get configuration value from crypto_config"""
    global crypto_config
    if crypto_config is None:
        return default

    # Handle nested keys like "auto_merge.enabled"
    keys = key.split('.')
    value = crypto_config
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default

    return value


def merge_crypto_data(new_data, old_data):
    """Merge new crypto data with old data, always using new data for conflicts"""
    if not old_data:
        return new_data

    if not new_data:
        return old_data

    merged_data = old_data.copy()

    # Get time series data
    old_time_series = old_data.get("Time Series (Daily)", {})
    new_time_series = new_data.get("Time Series (Daily)", {})

    # Merge time series data
    merged_time_series = old_time_series.copy()

    for date, new_values in new_time_series.items():
        # Always use new data (overwrite old data if date exists)
        merged_time_series[date] = new_values

    # Sort the merged time series by date (latest to oldest)
    sorted_time_series = dict(sorted(merged_time_series.items(), reverse=True))

    # Update merged data with sorted time series
    merged_data["Time Series (Daily)"] = sorted_time_series

    # Update metadata from new data if available
    if new_data.get("Meta Data"):
        merged_data["Meta Data"] = new_data["Meta Data"].copy()

    return merged_data


def load_existing_crypto_data(filepath):
    """Load existing crypto data from JSON file"""
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading existing data from {filepath}: {e}")
        return None


def save_crypto_data_with_merge(data, symbol, filepath):
    """Save crypto data with forced merging and backup"""
    # Check if we should create backup
    backup_before_merge = get_config_value("auto_merge.backup_before_merge", True)

    # Load existing data
    existing_data = load_existing_crypto_data(filepath)

    if existing_data and backup_before_merge:
        backup_data(filepath)

    # Merge data (always merge - no configuration option)
    if existing_data:
        merged_data = merge_crypto_data(data, existing_data)
        print(f"Merged data for {symbol} (always using new data)")
    else:
        merged_data = data
        print(f"No existing data found for {symbol}, saving new data")

    # Save merged data
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=4)

    return merged_data


def convert_crypto_to_standard_format(data, symbol):
    """Convert Alpha Vantage crypto format to standard stock format"""

    # Extract metadata
    metadata = data.get("Meta Data", {})
    time_series = data.get("Time Series (Digital Currency Daily)", {})

    # Build standard JSON structure matching stock format
    standard_data = {
        "Meta Data": {
            "1. Information": metadata.get("1. Information", "Daily Prices (open, high, low, close) and Volumes"),
            "2. Symbol": symbol,
            "3. Last Refreshed": metadata.get("6. Last Refreshed"),
            "4. Output Size": "Compact",
            "5. Time Zone": metadata.get("7. Time Zone", "UTC")
        },
        "Time Series (Daily)": {}
    }

    # Convert time series data to match stock format
    for date, values in time_series.items():
        standard_data["Time Series (Daily)"][date] = {
            "1. open": values.get("1. open", "0"),
            "2. high": values.get("2. high", "0"),
            "3. low": values.get("3. low", "0"),
            "4. close": values.get("4. close", "0"),
            "5. volume": values.get("5. volume", "0")
        }

    # Sort time series by date (latest to oldest)
    standard_data["Time Series (Daily)"] = dict(sorted(standard_data["Time Series (Daily)"].items(), reverse=True))

    return standard_data


def get_crypto_daily_price(symbol: str, market: str = "USD"):
    """
    Get daily cryptocurrency price data from Alpha Vantage
    Uses USD as proxy for USDT pairs

    Args:
        symbol: Crypto symbol (e.g., 'BTC', 'ETH')
        market: Target market currency (default: 'USD' as USDT proxy)
    """
    FUNCTION = "DIGITAL_CURRENCY_DAILY"
    APIKEY = os.getenv("ALPHAADVANTAGE_API_KEY")

    if not APIKEY:
        print("Error: ALPHAADVANTAGE_API_KEY not found in environment variables")
        return None

    url = (
        f"https://www.alphavantage.co/query?"
        f"function={FUNCTION}&symbol={symbol}&market={market}&apikey={APIKEY}"
    )

    try:
        print(f"Fetching data for {symbol}/{market}...")
        r = requests.get(url)
        data = r.json()

        # Error handling identical to stock implementation
        if data.get("Note") is not None or data.get("Information") is not None:
            print(f"API Error for {symbol}: {data.get('Note', data.get('Information', 'Unknown error'))}")
            return None

        # Check if we got valid data
        if "Time Series (Digital Currency Daily)" not in data:
            print(f"No time series data found for {symbol}")
            print(f"Response: {data}")
            return None

        # Convert to standard format
        standard_data = convert_crypto_to_standard_format(data, symbol)

        # Get file paths from config or use defaults
        coin_folder = get_config_value("file_paths.coin_folder", "coin")

        # Save with same naming convention as stocks
        # Ensure the coin folder exists relative to this script's directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        coin_dir = os.path.join(current_dir, coin_folder)
        os.makedirs(coin_dir, exist_ok=True)
        filename = f"{coin_dir}/daily_prices_{symbol}.json"

        # Save with merging functionality
        saved_data = save_crypto_data_with_merge(standard_data, symbol, filename)

        print(f"Successfully saved data for {symbol} to {filename}")
        return saved_data

    except requests.exceptions.RequestException as e:
        print(f"Network error fetching {symbol}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error for {symbol}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching {symbol}: {e}")
        return None


def get_all_crypto_prices(symbols_list=None, delay_seconds=None):
    """
    Get daily prices for all cryptocurrencies with rate limiting

    Args:
        symbols_list: List of crypto symbols, defaults to crypto_symbols_usdt
        delay_seconds: Delay between API calls (default: from config, typically 12 seconds)
    """
    if symbols_list is None:
        symbols_list = crypto_symbols_usdt

    # Use delay from config if not specified
    if delay_seconds is None:
        delay_seconds = get_config_value("api_settings.delay_seconds", 12)

    print(f"Starting crypto price collection for {len(symbols_list)} symbols...")
    print(f"Using {delay_seconds} second delay between calls to respect API rate limits")

    successful = 0
    failed = 0

    for i, symbol in enumerate(symbols_list, 1):
        print(f"\n[{i}/{len(symbols_list)}] Processing {symbol}...")

        result = get_crypto_daily_price(symbol)

        if result:
            successful += 1
        else:
            failed += 1

        # Add delay between API calls except for the last one
        if i < len(symbols_list):
            print(f"Waiting {delay_seconds} seconds before next request...")
            time.sleep(delay_seconds)

    print(f"\n" + "="*50)
    print(f"Summary: {successful} successful, {failed} failed")
    print(f"Rate limit: {delay_seconds}s delay between calls")
    print("="*50)


def get_daily_price(symbol: str):
    """
    Get daily price for crypto symbol, mirrors stock implementation exactly
    This function provides the same interface as the stock version
    """
    return get_crypto_daily_price(symbol, market="USD")


if __name__ == "__main__":
    # Test with BTC only
    # test_symbols = ["BTC"]

    print("Testing with sample symbols first...")
    # get_all_crypto_prices(test_symbols, delay_seconds=12)

    # Uncomment the line below to fetch all cryptocurrencies
    get_all_crypto_prices(crypto_symbols_usdt, delay_seconds=12)
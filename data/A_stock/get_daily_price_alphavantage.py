import os

import requests
from dotenv import load_dotenv

load_dotenv()
import json
import datetime
from collections import OrderedDict
sse_50_codes = [
    "600519.SHH",
    "601318.SHH",
    "600036.SHH",
    "601899.SHH",
    "600900.SHH",
    "601166.SHH",
    "600276.SHH",
    "600030.SHH",
    "603259.SHH",
    "688981.SHH",
    "688256.SHH",
    "601398.SHH",
    "688041.SHH",
    "601211.SHH",
    "601288.SHH",
    "601328.SHH",
    "688008.SHH",
    "600887.SHH",
    "600150.SHH",
    "601816.SHH",
    "601127.SHH",
    "600031.SHH",
    "688012.SHH",
    "603501.SHH",
    "601088.SHH",
    "600309.SHH",
    "601601.SHH",
    "601668.SHH",
    "603993.SHH",
    "601012.SHH",
    "601728.SHH",
    "600690.SHH",
    "600809.SHH",
    "600941.SHH",
    "600406.SHH",
    "601857.SHH",
    "601766.SHH",
    "601919.SHH",
    "600050.SHH",
    "600760.SHH",
    "601225.SHH",
    "600028.SHH",
    "601988.SHH",
    "688111.SHH",
    "601985.SHH",
    "601888.SHH",
    "601628.SHH",
    "601600.SHH",
    "601658.SHH",
    "600048.SHH"
]

def filter_data(data: dict,after_date: str):
    data_filtered = {}
    for date in data["Time Series (Daily)"]:
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
        after_date_obj = datetime.datetime.strptime(after_date, "%Y-%m-%d")
        if date_obj > after_date_obj:
            data_filtered[date] = data["Time Series (Daily)"][date]
    data["Time Series (Daily)"] = data_filtered
    return data

def merge_data(existing_data: dict, new_data: dict):
    """合并数据：保留已存在的日期，只添加新日期"""
    if existing_data is None or "Time Series (Daily)" not in existing_data:
        return new_data
    
    existing_dates = existing_data["Time Series (Daily)"]
    new_dates = new_data["Time Series (Daily)"]
    
    # 合并：保留已存在的日期，添加新日期
    merged_dates = existing_dates.copy()
    for date in new_dates:
        if date not in merged_dates:
            merged_dates[date] = new_dates[date]
    
    # 按日期排序（降序，最新的在前）
    sorted_dates = OrderedDict(sorted(merged_dates.items(), key=lambda x: x[0], reverse=True))
    
    # 更新数据：保留 existing_data 的 Meta Data，但更新 Last Refreshed
    merged_data = existing_data.copy()
    merged_data["Time Series (Daily)"] = sorted_dates
    
    # 更新 Meta Data 中的 Last Refreshed（使用最新的日期）
    if sorted_dates:
        merged_data["Meta Data"]["3. Last Refreshed"] = list(sorted_dates.keys())[0]
    
    return merged_data

def load_existing_data(filepath: str):
    """加载已存在的数据文件"""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return None
    return None

def get_daily_price(SYMBOL: str):
    FUNCTION = "TIME_SERIES_DAILY"
    OUTPUTSIZE = "compact"
    APIKEY = os.getenv("ALPHAADVANTAGE_API_KEY")
    url = (
        f"https://www.alphavantage.co/query?function={FUNCTION}&symbol={SYMBOL}&entitlement=delayed&outputsize={OUTPUTSIZE}&apikey={APIKEY}"
    )
    r = requests.get(url)
    data = r.json()
    stock_name = data.get("Meta Data").get("2. Symbol")
    print("Done for ", stock_name)
    if data.get("Note") is not None or data.get("Information") is not None:
        print(f"Error")
        exit()
        return
    if OUTPUTSIZE == "full":
        data = filter_data(data, "2025-10-01")
    
    # 合并数据：保留已存在的日期，只添加新日期
    output_file = f"./A_stock_data/daily_prices_{SYMBOL}.json"
    existing_data = load_existing_data(output_file)
    data = merge_data(existing_data, data)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    if SYMBOL == "000016.SHH":
        # 对于 000016.SHH，也需要合并 Adaily_prices 文件
        adaily_file = f"./A_stock_data/Adaily_prices_{SYMBOL}.json"
        existing_adaily_data = load_existing_data(adaily_file)
        adaily_data = merge_data(existing_adaily_data, data)
        
        with open(adaily_file, "w", encoding="utf-8") as f:
            json.dump(adaily_data, f, ensure_ascii=False, indent=4)
        
        # 对于 index_daily_sse_50.json，也需要合并
        index_file = "./A_stock_data/index_daily_sse_50.json"
        existing_index_data = load_existing_data(index_file)
        index_data = data.copy()
        index_data["Meta Data"]["2. Symbol"] = "000016.SH"
        index_data = merge_data(existing_index_data, index_data)
        
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    for symbol in sse_50_codes:
        get_daily_price(symbol)
    get_daily_price("000016.SHH")

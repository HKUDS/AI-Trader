import yfinance as yf
import json
from datetime import datetime, timedelta
import time

all_nasdaq_100_symbols = [
    "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
    "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
    "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
    "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
    "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
    "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
    "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
    "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
    "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
    "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
    "ON", "BIIB", "LULU", "CDW", "GFS"
]

def format_price(value, decimals=4):
    return f"{float(value):.{decimals}f}"

def format_volume(value):
    return str(int(value))

def get_daily_price(SYMBOL: str):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=150)
    
    ticker = yf.Ticker(SYMBOL)
    hist = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
    
    if hist.empty:
        raise Exception(f"No data available for {SYMBOL}")
    
    data = {
        "Meta Data": {
            "1. Information": "Daily Prices (Open, High, Low, Close, Volume)",
            "2. Symbol": SYMBOL,
            "3. Last Refreshed": hist.index[-1].strftime("%Y-%m-%d"),
            "4. Output Size": "Compact",
            "5. Time Zone": "US/Eastern"
        },
        "Time Series (Daily)": {}
    }
    
    for date, row in hist.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        data["Time Series (Daily)"][date_str] = {
            "1. open": format_price(row['Open']),
            "2. high": format_price(row['High']),
            "3. low": format_price(row['Low']),
            "4. close": format_price(row['Close']),
            "5. volume": format_volume(row['Volume'])
        }
    
    print(data)
    with open(f'./daily_prices_{SYMBOL}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    if SYMBOL == "QQQ":
        with open(f'./Adaily_prices_{SYMBOL}.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    for symbol in all_nasdaq_100_symbols:
        get_daily_price(symbol)

    get_daily_price("QQQ")
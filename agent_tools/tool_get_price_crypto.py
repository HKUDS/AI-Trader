"""
Cryptocurrency Price Query Tool for MCP

Real-time and historical price data for crypto trading
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("crypto-price-service")

# Import exchange manager
from .tool_crypto_exchange import CryptoExchangeManager


@mcp.tool()
def get_crypto_price_realtime(
    symbol: str,
    exchange: str = "bybit",
    testnet: bool = True
) -> Dict[str, Any]:
    """
    Get real-time cryptocurrency price
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT:USDT')
        exchange: Exchange name (bybit, binance, coinbase, kraken)
        testnet: Use testnet mode
        
    Returns:
        Price information dictionary
    """
    try:
        manager = CryptoExchangeManager(exchange, testnet)
        
        # Get ticker data
        ticker = manager.exchange.fetch_ticker(symbol)
        
        return {
            "success": True,
            "symbol": symbol,
            "exchange": exchange,
            "price": ticker.get('last'),
            "bid": ticker.get('bid'),
            "ask": ticker.get('ask'),
            "high_24h": ticker.get('high'),
            "low_24h": ticker.get('low'),
            "change_24h": ticker.get('percentage'),
            "volume_24h": ticker.get('quoteVolume'),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "symbol": symbol
        }


@mcp.tool()
def get_crypto_ohlcv(
    symbol: str,
    timeframe: str = "1m",
    limit: int = 100,
    exchange: str = "bybit",
    testnet: bool = True
) -> Dict[str, Any]:
    """
    Get OHLCV (candlestick) data for crypto
    
    Args:
        symbol: Trading pair
        timeframe: Timeframe (30s, 1m, 5m, 15m, 30m, 1h, 4h, 1d)
        limit: Number of candles
        exchange: Exchange name
        testnet: Use testnet mode
        
    Returns:
        OHLCV data array
    """
    try:
        manager = CryptoExchangeManager(exchange, testnet)
        ohlcv = manager.get_ohlcv(symbol, timeframe, limit)
        
        # Format data
        formatted_data = []
        for candle in ohlcv:
            formatted_data.append({
                "timestamp": candle[0],
                "datetime": datetime.fromtimestamp(candle[0] / 1000).isoformat(),
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5]
            })
        
        return {
            "success": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "data": formatted_data,
            "count": len(formatted_data)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "symbol": symbol
        }


@mcp.tool()
def get_crypto_price_local(
    symbol: str,
    date: str,
    data_path: str = "./data/crypto/merged.jsonl"
) -> Dict[str, Any]:
    """
    Get historical cryptocurrency price from local data
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        date: Date in format YYYY-MM-DD HH:MM:SS or YYYY-MM-DD
        data_path: Path to merged JSONL data file
        
    Returns:
        Historical price data
    """
    try:
        data_file = Path(data_path)
        
        if not data_file.exists():
            return {
                "success": False,
                "error": f"Data file not found: {data_path}",
                "symbol": symbol
            }
        
        # Parse date
        if ' ' in date:
            target_date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        else:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        
        # Search in JSONL file
        with open(data_file, 'r') as f:
            for line in f:
                data = json.loads(line)
                
                if data.get('symbol') == symbol:
                    # Check time series data
                    time_series = data.get('time_series', {})
                    
                    # Try exact match or closest
                    date_str = target_date.strftime("%Y-%m-%d %H:%M:%S")
                    if date_str in time_series:
                        candle = time_series[date_str]
                        return {
                            "success": True,
                            "symbol": symbol,
                            "date": date_str,
                            "open": candle.get('open'),
                            "high": candle.get('high'),
                            "low": candle.get('low'),
                            "close": candle.get('close'),
                            "volume": candle.get('volume')
                        }
        
        return {
            "success": False,
            "error": f"No data found for {symbol} on {date}",
            "symbol": symbol
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "symbol": symbol
        }


@mcp.tool()
def get_top_crypto_by_change(
    exchange: str = "bybit",
    limit: int = 50,
    testnet: bool = True
) -> Dict[str, Any]:
    """
    Get top cryptocurrencies sorted by 24h change
    
    Args:
        exchange: Exchange name
        limit: Number of symbols to return
        testnet: Use testnet mode
        
    Returns:
        List of top crypto symbols with change data
    """
    try:
        manager = CryptoExchangeManager(exchange, testnet)
        tickers = manager.exchange.fetch_tickers()
        
        # Filter and sort
        crypto_list = []
        for symbol, ticker in tickers.items():
            if 'USDT' in symbol:
                crypto_list.append({
                    "symbol": symbol,
                    "price": ticker.get('last'),
                    "change_24h": ticker.get('percentage', 0),
                    "volume_24h": ticker.get('quoteVolume', 0)
                })
        
        # Sort by absolute change
        crypto_list.sort(key=lambda x: abs(x['change_24h']), reverse=True)
        
        return {
            "success": True,
            "exchange": exchange,
            "top_symbols": crypto_list[:limit],
            "count": len(crypto_list[:limit])
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Start MCP server
if __name__ == "__main__":
    port = int(os.getenv("GETPRICE_CRYPTO_HTTP_PORT", 8004))
    print(f"🚀 Starting Crypto Price MCP server on port {port}")
    mcp.run(transport="sse", port=port)
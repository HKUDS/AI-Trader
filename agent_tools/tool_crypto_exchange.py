"""
Multi-Exchange Cryptocurrency Integration

Supports:
- ByBit (Primary, Derivatives)
- Binance (Futures/Spot)
- Coinbase Pro
- Kraken Futures

Features:
- Real-time price data
- Order execution
- Position management
- Symbol sorting by 24h change
"""

import os
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import ccxt
from dotenv import load_dotenv

load_dotenv()


class CryptoExchangeManager:
    """
    Unified interface for multiple crypto exchanges
    """
    
    def __init__(
        self,
        exchange_name: str = "bybit",
        testnet: bool = True,
        asset_type: str = "derivatives"
    ):
        """
        Initialize exchange connection
        
        Args:
            exchange_name: Exchange name (bybit, binance, coinbase, kraken)
            testnet: Use testnet/sandbox
            asset_type: derivatives or spot
        """
        self.exchange_name = exchange_name.lower()
        self.testnet = testnet
        self.asset_type = asset_type
        self.exchange = None
        
        # Initialize exchange
        self._init_exchange()
    
    def _init_exchange(self):
        """Initialize exchange connection"""
        try:
            if self.exchange_name == "bybit":
                self.exchange = ccxt.bybit({
                    'apiKey': os.getenv('BYBIT_API_KEY', ''),
                    'secret': os.getenv('BYBIT_API_SECRET', ''),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future' if self.asset_type == 'derivatives' else 'spot',
                    }
                })
                if self.testnet:
                    self.exchange.set_sandbox_mode(True)
                    print("✅ ByBit initialized (TESTNET)")
                else:
                    print("✅ ByBit initialized (LIVE)")
            
            elif self.exchange_name == "binance":
                self.exchange = ccxt.binance({
                    'apiKey': os.getenv('BINANCE_API_KEY', ''),
                    'secret': os.getenv('BINANCE_API_SECRET', ''),
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future' if self.asset_type == 'derivatives' else 'spot',
                    }
                })
                if self.testnet:
                    self.exchange.set_sandbox_mode(True)
                    print("✅ Binance initialized (TESTNET)")
                else:
                    print("✅ Binance initialized (LIVE)")
            
            elif self.exchange_name == "coinbase":
                self.exchange = ccxt.coinbase({
                    'apiKey': os.getenv('COINBASE_API_KEY', ''),
                    'secret': os.getenv('COINBASE_API_SECRET', ''),
                    'enableRateLimit': True,
                })
                print("✅ Coinbase initialized")
            
            elif self.exchange_name == "kraken":
                self.exchange = ccxt.kraken({
                    'apiKey': os.getenv('KRAKEN_API_KEY', ''),
                    'secret': os.getenv('KRAKEN_API_SECRET', ''),
                    'enableRateLimit': True,
                })
                print("✅ Kraken initialized")
            
            else:
                raise ValueError(f"Unsupported exchange: {self.exchange_name}")
            
            # Load markets
            self.exchange.load_markets()
            
        except Exception as e:
            print(f"❌ Failed to initialize {self.exchange_name}: {e}")
            raise
    
    def get_top_derivatives(
        self,
        sort_by: str = "24h_change",
        order: str = "desc",
        limit: int = 50,
        min_volume: float = 1000000
    ) -> List[str]:
        """
        Get top derivatives sorted by 24h change
        
        Args:
            sort_by: Sorting criteria (24h_change, volume, price)
            order: asc or desc
            limit: Number of symbols to return
            min_volume: Minimum 24h volume in USD
            
        Returns:
            List of trading pairs (e.g., ['BTCUSDT', 'ETHUSDT', ...])
        """
        try:
            print(f"🔍 Fetching top {limit} derivatives by {sort_by}...")
            
            # Fetch tickers
            tickers = self.exchange.fetch_tickers()
            
            # Filter derivatives (USDT perpetual/futures)
            derivatives = []
            for symbol, ticker in tickers.items():
                # Filter for USDT pairs
                if 'USDT' in symbol and ':USDT' in symbol:  # Derivative format
                    try:
                        change_24h = ticker.get('percentage', 0) or 0
                        volume_24h = ticker.get('quoteVolume', 0) or 0
                        
                        # Filter by minimum volume
                        if volume_24h >= min_volume:
                            derivatives.append({
                                'symbol': symbol,
                                'change_24h': abs(change_24h),  # Sort by absolute change
                                'volume_24h': volume_24h,
                                'price': ticker.get('last', 0)
                            })
                    except Exception as e:
                        continue
            
            # Sort by criteria
            if sort_by == "24h_change":
                derivatives.sort(key=lambda x: x['change_24h'], reverse=(order == 'desc'))
            elif sort_by == "volume":
                derivatives.sort(key=lambda x: x['volume_24h'], reverse=(order == 'desc'))
            
            # Return top symbols
            top_symbols = [d['symbol'] for d in derivatives[:limit]]
            
            print(f"✅ Found {len(top_symbols)} top derivatives")
            print(f"   Top 5: {top_symbols[:5]}")
            
            return top_symbols
            
        except Exception as e:
            print(f"⚠️ Failed to fetch derivatives: {e}")
            # Return default popular pairs
            return [
                "BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT",
                "SOL/USDT:USDT", "XRP/USDT:USDT", "ADA/USDT:USDT",
                "DOGE/USDT:USDT", "MATIC/USDT:USDT", "DOT/USDT:USDT",
                "AVAX/USDT:USDT"
            ]
    
    def get_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT:USDT')
            
        Returns:
            Current price or None
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker.get('last')
        except Exception as e:
            print(f"❌ Failed to get price for {symbol}: {e}")
            return None
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1m',
        limit: int = 100
    ) -> List[List]:
        """
        Get OHLCV (candlestick) data
        
        Args:
            symbol: Trading pair
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, etc.)
            limit: Number of candles
            
        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            print(f"❌ Failed to get OHLCV for {symbol}: {e}")
            return []
    
    def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = 'market',
        price: Optional[float] = None,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Create an order
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Order amount
            order_type: 'market' or 'limit'
            price: Limit price (for limit orders)
            params: Additional parameters (leverage, reduceOnly, etc.)
            
        Returns:
            Order info or None
        """
        try:
            if self.testnet:
                print(f"🧪 TESTNET ORDER: {side} {amount} {symbol} @ {order_type}")
                return {
                    'id': f"test_{int(time.time())}",
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'type': order_type,
                    'status': 'closed',
                    'price': price or self.get_price(symbol)
                }
            
            order = self.exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
                params=params or {}
            )
            
            print(f"✅ Order created: {order['id']}")
            return order
            
        except Exception as e:
            print(f"❌ Failed to create order: {e}")
            return None
    
    def get_balance(self) -> Dict[str, float]:
        """
        Get account balance
        
        Returns:
            Dictionary of balances by currency
        """
        try:
            balance = self.exchange.fetch_balance()
            return balance.get('total', {})
        except Exception as e:
            print(f"❌ Failed to get balance: {e}")
            return {}
    
    def get_positions(self) -> List[Dict]:
        """
        Get open positions (for derivatives)
        
        Returns:
            List of position info
        """
        try:
            if self.asset_type != 'derivatives':
                return []
            
            positions = self.exchange.fetch_positions()
            return [p for p in positions if float(p.get('contracts', 0)) > 0]
        except Exception as e:
            print(f"❌ Failed to get positions: {e}")
            return []
    
    def close_position(self, symbol: str) -> bool:
        """
        Close a position
        
        Args:
            symbol: Trading pair
            
        Returns:
            True if successful
        """
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos['symbol'] == symbol:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    amount = abs(float(pos['contracts']))
                    
                    self.create_order(
                        symbol=symbol,
                        side=side,
                        amount=amount,
                        params={'reduceOnly': True}
                    )
                    print(f"✅ Closed position: {symbol}")
                    return True
            
            print(f"⚠️ No open position found for {symbol}")
            return False
            
        except Exception as e:
            print(f"❌ Failed to close position: {e}")
            return False


# Convenience functions for MCP tool integration

def get_top_derivatives(
    exchange: str = "bybit",
    sort_by: str = "24h_change",
    order: str = "desc",
    limit: int = 50,
    asset_type: str = "derivatives",
    testnet: bool = True
) -> List[str]:
    """
    Get top derivatives sorted by 24h change
    
    MCP Tool compatible function
    """
    manager = CryptoExchangeManager(
        exchange_name=exchange,
        testnet=testnet,
        asset_type=asset_type
    )
    return manager.get_top_derivatives(sort_by, order, limit)


def get_crypto_price(
    symbol: str,
    exchange: str = "bybit",
    testnet: bool = True
) -> Optional[float]:
    """
    Get current crypto price
    
    MCP Tool compatible function
    """
    manager = CryptoExchangeManager(
        exchange_name=exchange,
        testnet=testnet
    )
    return manager.get_price(symbol)


def execute_crypto_trade(
    symbol: str,
    side: str,
    amount: float,
    exchange: str = "bybit",
    order_type: str = "market",
    testnet: bool = True
) -> Optional[Dict]:
    """
    Execute a crypto trade
    
    MCP Tool compatible function
    """
    manager = CryptoExchangeManager(
        exchange_name=exchange,
        testnet=testnet
    )
    return manager.create_order(symbol, side, amount, order_type)
"""
Event Detector - Real-time market event detection system

Monitors two primary event sources:
1. News feeds (RSS, APIs, webhooks)
2. Market momentum changes (price swings, volume spikes)

Emits events to the processing queue when triggers are detected.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event types for classification"""
    NEWS_BREAKING = "news_breaking"
    NEWS_STOCK_SPECIFIC = "news_stock_specific"
    MOMENTUM_SWING = "momentum_swing"
    VOLUME_SPIKE = "volume_spike"
    VOLATILITY_BREAKOUT = "volatility_breakout"
    EARNINGS_ALERT = "earnings_alert"


class EventPriority(Enum):
    """Event priority levels"""
    HIGH = 1    # Immediate action required
    MEDIUM = 2  # Process within minutes
    LOW = 3     # Process when capacity available


@dataclass
class MarketEvent:
    """Market event data structure"""
    event_id: str
    event_type: EventType
    priority: EventPriority
    timestamp: str
    symbols: List[str]  # Affected stock symbols
    title: str
    description: str
    source: str
    metadata: Dict  # Additional event-specific data

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            **asdict(self),
            'event_type': self.event_type.value,
            'priority': self.priority.value,
            'symbols': self.symbols,
        }


class NewsMonitor:
    """
    News feed monitor using multiple sources.

    Supports:
    - Jina AI for news search
    - RSS feeds (optional)
    - Custom webhooks (optional)
    """

    def __init__(
        self,
        stock_symbols: List[str],
        jina_api_key: Optional[str] = None,
        check_interval: int = 60,  # seconds
        lookback_minutes: int = 5
    ):
        """
        Initialize news monitor

        Args:
            stock_symbols: List of stocks to monitor
            jina_api_key: Jina AI API key for news search
            check_interval: How often to check for news (seconds)
            lookback_minutes: How far back to search for news
        """
        self.stock_symbols = stock_symbols
        self.jina_api_key = jina_api_key
        self.check_interval = check_interval
        self.lookback_minutes = lookback_minutes

        # Track seen articles to avoid duplicates
        self.seen_article_ids = set()

        # Callbacks for event emission
        self.event_callbacks: List[Callable] = []

    def register_callback(self, callback: Callable):
        """Register callback for event emission"""
        self.event_callbacks.append(callback)

    async def emit_event(self, event: MarketEvent):
        """Emit event to all registered callbacks"""
        for callback in self.event_callbacks:
            await callback(event)

    async def fetch_jina_news(self, query: str) -> List[Dict]:
        """
        Fetch news from Jina AI

        Args:
            query: Search query

        Returns:
            List of news articles
        """
        if not self.jina_api_key:
            logger.warning("Jina API key not provided, skipping Jina news fetch")
            return []

        try:
            url = "https://api.jina.ai/v1/search"
            headers = {
                "Authorization": f"Bearer {self.jina_api_key}",
                "Content-Type": "application/json"
            }

            # Calculate time range
            since_time = datetime.now() - timedelta(minutes=self.lookback_minutes)

            payload = {
                "q": query,
                "search_type": "news",
                "count": 20,
                "since": since_time.isoformat()
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("results", [])
                    else:
                        logger.error(f"Jina API error: {response.status}")
                        return []

        except Exception as e:
            logger.error(f"Error fetching Jina news: {e}")
            return []

    async def check_stock_news(self, symbol: str) -> List[MarketEvent]:
        """
        Check news for specific stock symbol

        Args:
            symbol: Stock symbol

        Returns:
            List of market events
        """
        events = []

        # Fetch news from Jina
        query = f"{symbol} stock news"
        articles = await self.fetch_jina_news(query)

        for article in articles:
            # Generate unique ID for deduplication
            article_id = f"{article.get('url', '')}_{article.get('title', '')}"

            if article_id in self.seen_article_ids:
                continue

            self.seen_article_ids.add(article_id)

            # Determine priority based on keywords
            title = article.get('title', '').lower()
            description = article.get('description', '').lower()

            priority = EventPriority.LOW
            if any(word in title or word in description for word in
                   ['breaking', 'alert', 'earnings', 'acquisition', 'merger']):
                priority = EventPriority.HIGH
            elif any(word in title or word in description for word in
                     ['announces', 'reports', 'launches', 'partnership']):
                priority = EventPriority.MEDIUM

            # Determine event type
            event_type = EventType.NEWS_STOCK_SPECIFIC
            if 'earnings' in title or 'earnings' in description:
                event_type = EventType.EARNINGS_ALERT
                priority = EventPriority.HIGH

            event = MarketEvent(
                event_id=f"news_{symbol}_{datetime.now().timestamp()}",
                event_type=event_type,
                priority=priority,
                timestamp=datetime.now().isoformat(),
                symbols=[symbol],
                title=article.get('title', 'No title'),
                description=article.get('description', 'No description'),
                source=article.get('url', 'Unknown source'),
                metadata={
                    'url': article.get('url', ''),
                    'published_date': article.get('published_date', ''),
                    'source_name': article.get('source', 'Unknown')
                }
            )

            events.append(event)

        return events

    async def run_monitoring_loop(self):
        """Run continuous news monitoring loop"""
        logger.info(f"🔍 Starting news monitoring for {len(self.stock_symbols)} symbols")
        logger.info(f"   Check interval: {self.check_interval}s")
        logger.info(f"   Lookback: {self.lookback_minutes} minutes")

        while True:
            try:
                # Check news for all symbols
                for symbol in self.stock_symbols:
                    events = await self.check_stock_news(symbol)

                    # Emit events
                    for event in events:
                        logger.info(f"📰 New event: {event.title} [{symbol}] - Priority: {event.priority.name}")
                        await self.emit_event(event)

                # Wait before next check
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in news monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retry


class MomentumDetector:
    """
    Market momentum detector for price swings and volume spikes.

    Monitors:
    - Sudden price changes (>X% in Y minutes)
    - Volume spikes (>X times average)
    - Volatility breakouts
    """

    def __init__(
        self,
        stock_symbols: List[str],
        price_threshold: float = 0.03,  # 3% price change
        volume_threshold: float = 2.0,  # 2x average volume
        check_interval: int = 30  # seconds
    ):
        """
        Initialize momentum detector

        Args:
            stock_symbols: List of stocks to monitor
            price_threshold: Price change threshold (e.g., 0.03 = 3%)
            volume_threshold: Volume spike threshold (e.g., 2.0 = 2x average)
            check_interval: How often to check (seconds)
        """
        self.stock_symbols = stock_symbols
        self.price_threshold = price_threshold
        self.volume_threshold = volume_threshold
        self.check_interval = check_interval

        # Price history for momentum calculation
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}

        # Callbacks
        self.event_callbacks: List[Callable] = []

    def register_callback(self, callback: Callable):
        """Register callback for event emission"""
        self.event_callbacks.append(callback)

    async def emit_event(self, event: MarketEvent):
        """Emit event to all registered callbacks"""
        for callback in self.event_callbacks:
            await callback(event)

    async def fetch_current_price(self, symbol: str) -> Optional[float]:
        """
        Fetch current price for symbol

        This should integrate with your existing get_stock_price tool
        or Alpha Vantage API.

        Args:
            symbol: Stock symbol

        Returns:
            Current price or None
        """
        # TODO: Integrate with existing price fetching system
        # For now, this is a placeholder
        try:
            # This would call your existing stock price tool
            # from agent_tools import get_stock_price
            # price = get_stock_price(symbol, datetime.now().strftime("%Y-%m-%d"))
            # return price

            logger.debug(f"Fetching price for {symbol}")
            return None  # Placeholder

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return None

    def calculate_momentum(self, symbol: str) -> Optional[float]:
        """
        Calculate price momentum for symbol

        Args:
            symbol: Stock symbol

        Returns:
            Momentum percentage or None
        """
        if symbol not in self.price_history:
            return None

        history = self.price_history[symbol]
        if len(history) < 2:
            return None

        # Calculate % change from oldest to newest
        oldest_price = history[0][1]
        newest_price = history[-1][1]

        momentum = (newest_price - oldest_price) / oldest_price
        return momentum

    async def check_momentum(self, symbol: str) -> Optional[MarketEvent]:
        """
        Check momentum for specific symbol

        Args:
            symbol: Stock symbol

        Returns:
            Market event if threshold exceeded, None otherwise
        """
        current_price = await self.fetch_current_price(symbol)

        if current_price is None:
            return None

        # Update price history
        now = datetime.now()
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append((now, current_price))

        # Keep only last 10 minutes of data
        cutoff = now - timedelta(minutes=10)
        self.price_history[symbol] = [
            (ts, price) for ts, price in self.price_history[symbol]
            if ts > cutoff
        ]

        # Calculate momentum
        momentum = self.calculate_momentum(symbol)

        if momentum is None:
            return None

        # Check if threshold exceeded
        if abs(momentum) >= self.price_threshold:
            direction = "up" if momentum > 0 else "down"

            event = MarketEvent(
                event_id=f"momentum_{symbol}_{now.timestamp()}",
                event_type=EventType.MOMENTUM_SWING,
                priority=EventPriority.HIGH if abs(momentum) >= 0.05 else EventPriority.MEDIUM,
                timestamp=now.isoformat(),
                symbols=[symbol],
                title=f"{symbol} price {direction} {abs(momentum)*100:.2f}%",
                description=f"Significant price movement detected: {momentum*100:+.2f}% in last 10 minutes",
                source="momentum_detector",
                metadata={
                    'momentum': momentum,
                    'current_price': current_price,
                    'direction': direction,
                    'threshold': self.price_threshold
                }
            )

            return event

        return None

    async def run_monitoring_loop(self):
        """Run continuous momentum monitoring loop"""
        logger.info(f"📊 Starting momentum monitoring for {len(self.stock_symbols)} symbols")
        logger.info(f"   Price threshold: {self.price_threshold*100}%")
        logger.info(f"   Check interval: {self.check_interval}s")

        while True:
            try:
                # Check momentum for all symbols
                for symbol in self.stock_symbols:
                    event = await self.check_momentum(symbol)

                    if event:
                        logger.info(f"⚡ Momentum event: {event.title} - Priority: {event.priority.name}")
                        await self.emit_event(event)

                # Wait before next check
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in momentum monitoring loop: {e}")
                await asyncio.sleep(5)


class EventDetector:
    """
    Main event detector coordinating news and momentum monitoring
    """

    def __init__(
        self,
        stock_symbols: List[str],
        jina_api_key: Optional[str] = None,
        news_check_interval: int = 60,
        momentum_check_interval: int = 30,
        price_threshold: float = 0.03
    ):
        """
        Initialize event detector

        Args:
            stock_symbols: List of stocks to monitor
            jina_api_key: Jina AI API key
            news_check_interval: News check interval (seconds)
            momentum_check_interval: Momentum check interval (seconds)
            price_threshold: Price change threshold for momentum events
        """
        self.stock_symbols = stock_symbols

        # Initialize monitors
        self.news_monitor = NewsMonitor(
            stock_symbols=stock_symbols,
            jina_api_key=jina_api_key,
            check_interval=news_check_interval
        )

        self.momentum_detector = MomentumDetector(
            stock_symbols=stock_symbols,
            price_threshold=price_threshold,
            check_interval=momentum_check_interval
        )

        # Event queue
        self.event_queue: asyncio.Queue = asyncio.Queue()

        # Register callbacks
        self.news_monitor.register_callback(self._on_event)
        self.momentum_detector.register_callback(self._on_event)

    async def _on_event(self, event: MarketEvent):
        """Handle event from monitors"""
        await self.event_queue.put(event)

    async def start(self):
        """Start all monitoring systems"""
        logger.info("🚀 Starting Event Detector System")

        # Start both monitors concurrently
        await asyncio.gather(
            self.news_monitor.run_monitoring_loop(),
            self.momentum_detector.run_monitoring_loop()
        )

    async def get_next_event(self) -> MarketEvent:
        """Get next event from queue (blocking)"""
        return await self.event_queue.get()


# Example usage
if __name__ == "__main__":
    async def test_detector():
        # Test symbols
        symbols = ["AAPL", "NVDA", "TSLA", "MSFT"]

        detector = EventDetector(
            stock_symbols=symbols,
            jina_api_key=None,  # Set your Jina API key
            news_check_interval=60,
            momentum_check_interval=30
        )

        # Process events
        async def process_events():
            while True:
                event = await detector.get_next_event()
                print(f"\n🔔 Event received: {event.title}")
                print(f"   Type: {event.event_type.value}")
                print(f"   Priority: {event.priority.name}")
                print(f"   Symbols: {', '.join(event.symbols)}")

        # Run detector and processor
        await asyncio.gather(
            detector.start(),
            process_events()
        )

    # Run test
    asyncio.run(test_detector())

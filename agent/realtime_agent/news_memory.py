"""
News Memory System - Compressed storage of news events

Maintains a token-efficient memory of recent news with:
- Automatic summarization/compression
- Semantic deduplication
- Sliding window retention (24-48 hours)
- Fast retrieval by symbol/time/topic
- Token budget tracking
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import logging

from agent.realtime_agent.event_detector import MarketEvent, EventType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CompressedNewsEvent:
    """Compressed news event for memory efficiency"""
    event_id: str
    timestamp: str
    symbols: List[str]
    summary: str  # Compressed version (max 100 chars)
    sentiment: str  # "bullish", "bearish", "neutral"
    impact: str  # "high", "medium", "low"
    event_type: str
    source_hash: str  # For deduplication

    def to_compact_dict(self) -> Dict:
        """Convert to compact dictionary (minimal tokens)"""
        return {
            'ts': self.timestamp[:10],  # Just date
            'sym': ','.join(self.symbols),
            'txt': self.summary,
            'sent': self.sentiment[0].upper(),  # B/N/X
            'imp': self.impact[0].upper()  # H/M/L
        }

    def to_natural_language(self) -> str:
        """Convert to natural language (for agent context)"""
        symbols_str = ', '.join(self.symbols)
        return f"{self.timestamp[:10]}: {self.summary} [{symbols_str}] ({self.sentiment}/{self.impact})"

    def estimate_tokens(self) -> int:
        """Estimate token count (rough approximation)"""
        # Rule of thumb: 1 token ≈ 4 characters
        text = self.to_natural_language()
        return len(text) // 4


class NewsMemoryManager:
    """
    Manages compressed news memory with token budget control
    """

    def __init__(
        self,
        max_token_budget: int = 2000,  # Max tokens for news context
        retention_hours: int = 48,  # How long to keep news
        max_events_per_symbol: int = 10  # Max events per symbol
    ):
        """
        Initialize news memory manager

        Args:
            max_token_budget: Maximum tokens to use for news context
            retention_hours: Hours to retain news events
            max_events_per_symbol: Maximum events to keep per symbol
        """
        self.max_token_budget = max_token_budget
        self.retention_hours = retention_hours
        self.max_events_per_symbol = max_events_per_symbol

        # Storage
        self.events: List[CompressedNewsEvent] = []
        self.events_by_symbol: Dict[str, List[CompressedNewsEvent]] = defaultdict(list)

        # Deduplication tracking
        self.seen_hashes: set = set()

        # Statistics
        self.total_events_received = 0
        self.duplicate_events_filtered = 0
        self.events_expired = 0

    def _compute_content_hash(self, event: MarketEvent) -> str:
        """
        Compute hash of event content for deduplication

        Args:
            event: Market event

        Returns:
            Content hash
        """
        # Hash based on title + symbols + date
        content = f"{event.title}_{','.join(sorted(event.symbols))}_{event.timestamp[:10]}"
        return hashlib.md5(content.encode()).hexdigest()

    def _compress_event(self, event: MarketEvent) -> CompressedNewsEvent:
        """
        Compress market event into compact form

        Args:
            event: Original market event

        Returns:
            Compressed event
        """
        # Compress title/description (max 100 chars)
        summary = event.title
        if len(summary) > 100:
            summary = summary[:97] + "..."

        # Infer sentiment from title (basic heuristic)
        title_lower = event.title.lower()
        sentiment = "neutral"

        positive_words = ['surge', 'gains', 'up', 'beat', 'positive', 'growth', 'record', 'partnership', 'acquisition']
        negative_words = ['fall', 'drop', 'down', 'miss', 'negative', 'loss', 'decline', 'lawsuit', 'warning']

        if any(word in title_lower for word in positive_words):
            sentiment = "bullish"
        elif any(word in title_lower for word in negative_words):
            sentiment = "bearish"

        # Infer impact from priority
        impact = {
            1: "high",    # HIGH priority
            2: "medium",  # MEDIUM priority
            3: "low"      # LOW priority
        }.get(event.priority.value, "low")

        # Compute hash for deduplication
        source_hash = self._compute_content_hash(event)

        return CompressedNewsEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            symbols=event.symbols,
            summary=summary,
            sentiment=sentiment,
            impact=impact,
            event_type=event.event_type.value,
            source_hash=source_hash
        )

    def _is_duplicate(self, compressed_event: CompressedNewsEvent) -> bool:
        """
        Check if event is duplicate

        Args:
            compressed_event: Compressed event to check

        Returns:
            True if duplicate
        """
        return compressed_event.source_hash in self.seen_hashes

    def _cleanup_expired(self):
        """Remove events older than retention period"""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)

        # Filter events
        before_count = len(self.events)
        self.events = [
            event for event in self.events
            if datetime.fromisoformat(event.timestamp) > cutoff_time
        ]
        after_count = len(self.events)

        if before_count > after_count:
            expired = before_count - after_count
            self.events_expired += expired
            logger.info(f"🗑️  Cleaned up {expired} expired events")

        # Rebuild symbol index
        self.events_by_symbol.clear()
        for event in self.events:
            for symbol in event.symbols:
                self.events_by_symbol[symbol].append(event)

        # Rebuild hash tracking
        self.seen_hashes = {event.source_hash for event in self.events}

    def _enforce_symbol_limits(self):
        """Enforce max events per symbol"""
        for symbol, symbol_events in self.events_by_symbol.items():
            if len(symbol_events) > self.max_events_per_symbol:
                # Keep most recent
                symbol_events.sort(key=lambda e: e.timestamp, reverse=True)
                to_remove = symbol_events[self.max_events_per_symbol:]

                # Remove from main storage
                for event in to_remove:
                    if event in self.events:
                        self.events.remove(event)
                        self.seen_hashes.discard(event.source_hash)

                # Update symbol index
                self.events_by_symbol[symbol] = symbol_events[:self.max_events_per_symbol]

    def add_event(self, event: MarketEvent) -> bool:
        """
        Add event to memory (with compression and deduplication)

        Args:
            event: Market event to add

        Returns:
            True if added, False if duplicate
        """
        self.total_events_received += 1

        # Compress
        compressed = self._compress_event(event)

        # Check for duplicate
        if self._is_duplicate(compressed):
            self.duplicate_events_filtered += 1
            logger.debug(f"Duplicate event filtered: {compressed.summary}")
            return False

        # Add to storage
        self.events.append(compressed)
        self.seen_hashes.add(compressed.source_hash)

        # Index by symbol
        for symbol in compressed.symbols:
            self.events_by_symbol[symbol].append(compressed)

        logger.info(f"📝 Added to memory: {compressed.summary} [{','.join(compressed.symbols)}]")

        # Periodic cleanup
        if len(self.events) % 50 == 0:
            self._cleanup_expired()
            self._enforce_symbol_limits()

        return True

    def get_events_for_symbol(
        self,
        symbol: str,
        limit: Optional[int] = None
    ) -> List[CompressedNewsEvent]:
        """
        Get events for specific symbol

        Args:
            symbol: Stock symbol
            limit: Maximum number of events to return

        Returns:
            List of compressed events
        """
        events = self.events_by_symbol.get(symbol, [])

        # Sort by timestamp (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        if limit:
            events = events[:limit]

        return events

    def get_recent_events(
        self,
        hours: int = 24,
        limit: Optional[int] = None
    ) -> List[CompressedNewsEvent]:
        """
        Get recent events across all symbols

        Args:
            hours: Hours to look back
            limit: Maximum number of events to return

        Returns:
            List of compressed events
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        # Filter by time
        events = [
            event for event in self.events
            if datetime.fromisoformat(event.timestamp) > cutoff
        ]

        # Sort by timestamp (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        if limit:
            events = events[:limit]

        return events

    def get_context_for_agent(
        self,
        symbols: Optional[List[str]] = None,
        max_tokens: Optional[int] = None
    ) -> Tuple[str, int]:
        """
        Get compressed context for agent (respecting token budget)

        Args:
            symbols: Optional list of symbols to focus on
            max_tokens: Maximum tokens to use (defaults to max_token_budget)

        Returns:
            Tuple of (context_string, estimated_tokens)
        """
        if max_tokens is None:
            max_tokens = self.max_token_budget

        # Get events
        if symbols:
            events = []
            for symbol in symbols:
                events.extend(self.get_events_for_symbol(symbol, limit=5))
            # Deduplicate
            seen_ids = set()
            unique_events = []
            for event in events:
                if event.event_id not in seen_ids:
                    unique_events.append(event)
                    seen_ids.add(event.event_id)
            events = unique_events
        else:
            events = self.get_recent_events(hours=24, limit=20)

        # Sort by timestamp (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Build context within token budget
        context_lines = ["# Recent News Events (Last 24-48h)\n"]
        current_tokens = len(context_lines[0]) // 4

        for event in events:
            line = event.to_natural_language()
            line_tokens = event.estimate_tokens()

            if current_tokens + line_tokens > max_tokens:
                break

            context_lines.append(line)
            current_tokens += line_tokens

        context = "\n".join(context_lines)
        return context, current_tokens

    def get_statistics(self) -> Dict:
        """Get memory statistics"""
        total_tokens = sum(event.estimate_tokens() for event in self.events)

        return {
            "total_events": len(self.events),
            "events_by_symbol": {
                symbol: len(events)
                for symbol, events in self.events_by_symbol.items()
            },
            "total_tokens": total_tokens,
            "token_budget": self.max_token_budget,
            "token_utilization": f"{(total_tokens / self.max_token_budget) * 100:.1f}%",
            "retention_hours": self.retention_hours,
            "total_received": self.total_events_received,
            "duplicates_filtered": self.duplicate_events_filtered,
            "events_expired": self.events_expired
        }

    def save_to_file(self, filepath: str):
        """Save memory to JSON file"""
        data = {
            "metadata": {
                "saved_at": datetime.now().isoformat(),
                "statistics": self.get_statistics()
            },
            "events": [
                {
                    "event_id": e.event_id,
                    "timestamp": e.timestamp,
                    "symbols": e.symbols,
                    "summary": e.summary,
                    "sentiment": e.sentiment,
                    "impact": e.impact,
                    "event_type": e.event_type,
                    "source_hash": e.source_hash
                }
                for e in self.events
            ]
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"💾 Memory saved to {filepath}")

    def load_from_file(self, filepath: str):
        """Load memory from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        self.events.clear()
        self.events_by_symbol.clear()
        self.seen_hashes.clear()

        for event_data in data['events']:
            event = CompressedNewsEvent(**event_data)
            self.events.append(event)
            self.seen_hashes.add(event.source_hash)

            for symbol in event.symbols:
                self.events_by_symbol[symbol].append(event)

        logger.info(f"📂 Memory loaded from {filepath} ({len(self.events)} events)")


# Example usage
if __name__ == "__main__":
    from event_detector import MarketEvent, EventType, EventPriority

    # Create memory manager
    memory = NewsMemoryManager(
        max_token_budget=2000,
        retention_hours=48,
        max_events_per_symbol=10
    )

    # Test event
    test_event = MarketEvent(
        event_id="test_1",
        event_type=EventType.NEWS_STOCK_SPECIFIC,
        priority=EventPriority.HIGH,
        timestamp=datetime.now().isoformat(),
        symbols=["AAPL", "NVDA"],
        title="Apple and NVIDIA announce groundbreaking AI partnership",
        description="Two tech giants team up for next-gen AI chips",
        source="https://example.com/news",
        metadata={}
    )

    # Add event
    memory.add_event(test_event)

    # Get context
    context, tokens = memory.get_context_for_agent(symbols=["AAPL"])
    print(f"\nContext ({tokens} tokens):")
    print(context)

    # Statistics
    print("\nMemory Statistics:")
    stats = memory.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

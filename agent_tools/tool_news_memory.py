"""
News Memory MCP Tool - Query recent news by stock ticker

Provides trading agents with access to compressed, relevant news via tool calls.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from mcp_server_local import ToolFunction, app
import logging

# Import news memory system
try:
    from agent.realtime_agent.news_memory import NewsMemoryManager, CompressedNewsEvent
except ImportError:
    # Fallback for when realtime agent isn't initialized yet
    NewsMemoryManager = None
    CompressedNewsEvent = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global news memory instance (initialized on first use)
_global_news_memory: Optional[NewsMemoryManager] = None


def get_news_memory() -> NewsMemoryManager:
    """Get or create global news memory instance"""
    global _global_news_memory

    if _global_news_memory is None:
        if NewsMemoryManager is None:
            raise RuntimeError("NewsMemoryManager not available. Install realtime agent components.")

        _global_news_memory = NewsMemoryManager(
            max_token_budget=2000,
            retention_hours=48,
            max_events_per_symbol=20
        )

        # Try to load existing memory from disk
        memory_file = os.path.join(project_root, "data", "news_memory", "memory.json")
        if os.path.exists(memory_file):
            try:
                _global_news_memory.load_from_file(memory_file)
                logger.info(f"📂 Loaded news memory from disk")
            except Exception as e:
                logger.warning(f"Failed to load news memory: {e}")

    return _global_news_memory


def save_news_memory():
    """Save news memory to disk"""
    global _global_news_memory

    if _global_news_memory is not None:
        memory_dir = os.path.join(project_root, "data", "news_memory")
        os.makedirs(memory_dir, exist_ok=True)

        memory_file = os.path.join(memory_dir, "memory.json")
        _global_news_memory.save_to_file(memory_file)


@ToolFunction(name="get_recent_news")
async def get_recent_news(
    symbol: str,
    hours: int = 24,
    max_events: int = 10
) -> str:
    """
    Get recent news for a specific stock symbol.

    This tool provides compressed, agent-summarized news events for trading decisions.
    News is automatically filtered, deduplicated, and compressed to minimize token usage.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "NVDA")
        hours: Hours to look back (default: 24, max: 48)
        max_events: Maximum number of events to return (default: 10)

    Returns:
        Formatted news summary with sentiment and impact analysis
    """
    try:
        memory = get_news_memory()

        # Get events for symbol
        events = memory.get_events_for_symbol(symbol, limit=max_events)

        # Filter by time window
        cutoff = datetime.now() - timedelta(hours=min(hours, 48))
        events = [
            e for e in events
            if datetime.fromisoformat(e.timestamp) > cutoff
        ]

        if not events:
            return f"No recent news found for {symbol} in the last {hours} hours."

        # Format response
        lines = [f"Recent News for {symbol} (Last {hours}h):\n"]

        for i, event in enumerate(events, 1):
            timestamp = datetime.fromisoformat(event.timestamp).strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"{i}. [{timestamp}] {event.summary}\n"
                f"   Sentiment: {event.sentiment.upper()}, Impact: {event.impact.upper()}\n"
            )

        # Add summary statistics
        bullish = sum(1 for e in events if e.sentiment == "bullish")
        bearish = sum(1 for e in events if e.sentiment == "bearish")
        neutral = len(events) - bullish - bearish

        lines.append(f"\nSummary: {bullish} bullish, {bearish} bearish, {neutral} neutral events")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting recent news: {e}")
        return f"Error retrieving news for {symbol}: {str(e)}"


@ToolFunction(name="get_market_news_summary")
async def get_market_news_summary(
    symbols: List[str],
    hours: int = 12
) -> str:
    """
    Get aggregated news summary across multiple stocks.

    Useful for getting a market overview before trading decisions.

    Args:
        symbols: List of stock ticker symbols
        hours: Hours to look back (default: 12)

    Returns:
        Aggregated news summary with key events
    """
    try:
        memory = get_news_memory()

        all_events = []
        for symbol in symbols:
            events = memory.get_events_for_symbol(symbol, limit=5)
            cutoff = datetime.now() - timedelta(hours=hours)
            events = [
                e for e in events
                if datetime.fromisoformat(e.timestamp) > cutoff
            ]
            all_events.extend(events)

        if not all_events:
            return f"No recent news found for {', '.join(symbols)} in the last {hours} hours."

        # Sort by timestamp (most recent first)
        all_events.sort(key=lambda e: e.timestamp, reverse=True)

        # Group by impact
        high_impact = [e for e in all_events if e.impact == "high"]
        medium_impact = [e for e in all_events if e.impact == "medium"]

        lines = [f"Market News Summary - {', '.join(symbols)} (Last {hours}h):\n"]

        # High impact news
        if high_impact:
            lines.append("⚠️  HIGH IMPACT NEWS:")
            for event in high_impact[:5]:  # Top 5
                timestamp = datetime.fromisoformat(event.timestamp).strftime("%m-%d %H:%M")
                symbols_str = ','.join(event.symbols)
                lines.append(f"  [{timestamp}] {symbols_str}: {event.summary} ({event.sentiment})")

        # Medium impact news
        if medium_impact and len(high_impact) < 3:
            lines.append("\n📊 MEDIUM IMPACT NEWS:")
            for event in medium_impact[:3]:
                timestamp = datetime.fromisoformat(event.timestamp).strftime("%m-%d %H:%M")
                symbols_str = ','.join(event.symbols)
                lines.append(f"  [{timestamp}] {symbols_str}: {event.summary} ({event.sentiment})")

        # Sentiment breakdown
        bullish = sum(1 for e in all_events if e.sentiment == "bullish")
        bearish = sum(1 for e in all_events if e.sentiment == "bearish")
        neutral = len(all_events) - bullish - bearish

        lines.append(f"\nOverall Sentiment: {bullish} bullish, {bearish} bearish, {neutral} neutral")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting market news summary: {e}")
        return f"Error retrieving market news: {str(e)}"


@ToolFunction(name="search_news_by_keywords")
async def search_news_by_keywords(
    keywords: List[str],
    hours: int = 24,
    max_results: int = 10
) -> str:
    """
    Search news by keywords across all tracked stocks.

    Useful for finding specific types of news (e.g., "earnings", "partnership", "lawsuit").

    Args:
        keywords: List of keywords to search for
        hours: Hours to look back (default: 24)
        max_results: Maximum results to return (default: 10)

    Returns:
        Matching news events
    """
    try:
        memory = get_news_memory()

        # Get all recent events
        all_events = memory.get_recent_events(hours=hours, limit=100)

        # Filter by keywords (case-insensitive)
        matching_events = []
        keywords_lower = [k.lower() for k in keywords]

        for event in all_events:
            summary_lower = event.summary.lower()
            if any(keyword in summary_lower for keyword in keywords_lower):
                matching_events.append(event)

        if not matching_events:
            return f"No news found matching keywords: {', '.join(keywords)}"

        # Limit results
        matching_events = matching_events[:max_results]

        # Format response
        lines = [f"News Matching Keywords: {', '.join(keywords)}\n"]

        for i, event in enumerate(matching_events, 1):
            timestamp = datetime.fromisoformat(event.timestamp).strftime("%Y-%m-%d %H:%M")
            symbols_str = ','.join(event.symbols)
            lines.append(
                f"{i}. [{timestamp}] {symbols_str}: {event.summary}\n"
                f"   Sentiment: {event.sentiment.upper()}, Impact: {event.impact.upper()}\n"
            )

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error searching news: {e}")
        return f"Error searching news: {str(e)}"


@ToolFunction(name="get_news_statistics")
async def get_news_statistics() -> str:
    """
    Get statistics about the news memory system.

    Useful for understanding news volume and coverage.

    Returns:
        News memory statistics
    """
    try:
        memory = get_news_memory()
        stats = memory.get_statistics()

        lines = [
            "📊 News Memory Statistics:\n",
            f"Total Events: {stats['total_events']}",
            f"Total Tokens: {stats['total_tokens']} / {stats['token_budget']}",
            f"Utilization: {stats['token_utilization']}",
            f"Retention: {stats['retention_hours']} hours",
            f"\nEvents Received: {stats['total_received']}",
            f"Duplicates Filtered: {stats['duplicates_filtered']}",
            f"Events Expired: {stats['events_expired']}",
            f"\nEvents by Symbol:"
        ]

        # Top 10 symbols by event count
        symbol_counts = sorted(
            stats['events_by_symbol'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        for symbol, count in symbol_counts:
            lines.append(f"  {symbol}: {count} events")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return f"Error getting statistics: {str(e)}"


# Export tools
if __name__ == "__main__":
    print("News Memory MCP Tools:")
    print("  - get_recent_news(symbol, hours, max_events)")
    print("  - get_market_news_summary(symbols, hours)")
    print("  - search_news_by_keywords(keywords, hours, max_results)")
    print("  - get_news_statistics()")

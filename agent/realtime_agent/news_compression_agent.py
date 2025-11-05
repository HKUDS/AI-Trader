"""
News Compression Agent - Creates token-efficient summaries of news

This agent processes raw news and creates compressed, actionable summaries
optimized for trading agent consumption.

Goals:
- Compress news to <100 characters while preserving key information
- Extract sentiment (bullish/bearish/neutral)
- Assess impact magnitude (high/medium/low)
- Remove fluff and marketing language
- Focus on actionable trading signals
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from agent.realtime_agent.event_detector import MarketEvent, EventType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CompressedNews:
    """Compressed news output"""
    event_id: str
    timestamp: str
    symbols: List[str]
    original_title: str
    compressed_summary: str  # Max 100 chars
    sentiment: str  # "bullish", "bearish", "neutral"
    impact: str  # "high", "medium", "low"
    confidence: float  # 0.0-1.0
    reasoning: str  # Brief reasoning for classification


class NewsCompressionAgent:
    """
    Agent specialized in compressing news for memory efficiency

    Uses Claude to:
    1. Extract core message from verbose news
    2. Classify sentiment and impact
    3. Generate ultra-concise summaries (<100 chars)
    4. Preserve trading-relevant information
    """

    def __init__(
        self,
        anthropic_api_key: str,
        model: str = "sonnet"
    ):
        """
        Initialize news compression agent

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use (default: "sonnet")
        """
        self.api_key = anthropic_api_key
        self.model = model

        # Create client
        self.client = ClaudeSDKClient(ClaudeAgentOptions(
            model=model,
            api_key=anthropic_api_key
        ))

        # Statistics
        self.total_compressed = 0
        self.total_chars_saved = 0

    async def compress(self, event: MarketEvent) -> CompressedNews:
        """
        Compress news event into token-efficient format

        Args:
            event: Raw market event

        Returns:
            Compressed news
        """
        prompt = f"""You are a financial news compression specialist for an AI trading system.

Your task: Compress this news into an ultra-concise, actionable summary (MAX 100 characters).

Original News:
Title: {event.title}
Description: {event.description}
Symbols: {', '.join(event.symbols)}
Source: {event.source}

Requirements:
1. **Summary**: Extract core message in ≤100 chars (be ruthless, remove fluff)
2. **Sentiment**: Classify as "bullish", "bearish", or "neutral" for stocks
3. **Impact**: Rate as "high", "medium", or "low" based on price-moving potential
4. **Confidence**: Rate your classification confidence (0.0-1.0)
5. **Reasoning**: Brief explanation (max 50 words)

Examples:
- "Apple announces groundbreaking new iPhone with revolutionary AI features"
  → "AAPL: New iPhone w/ AI features" (31 chars)

- "NVIDIA reports quarterly earnings that significantly beat analyst expectations"
  → "NVDA Q earnings beat est" (24 chars)

- "Tesla CEO faces lawsuit over controversial social media posts"
  → "TSLA CEO lawsuit re: posts" (27 chars)

Output JSON:
{{
  "compressed_summary": "ultra-concise summary (max 100 chars)",
  "sentiment": "bullish" / "bearish" / "neutral",
  "impact": "high" / "medium" / "low",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Focus on facts, not speculation. Preserve ticker symbols."""

        try:
            # Query agent
            await self.client.query(prompt)
            response = await self.client.receive_response()

            # Parse response
            content = response.get("content", "")

            # Extract JSON
            import json
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            result = json.loads(json_str)

            # Validate summary length
            summary = result.get("compressed_summary", "")
            if len(summary) > 100:
                logger.warning(f"Summary too long ({len(summary)} chars), truncating")
                summary = summary[:97] + "..."

            compressed = CompressedNews(
                event_id=event.event_id,
                timestamp=event.timestamp,
                symbols=event.symbols,
                original_title=event.title,
                compressed_summary=summary,
                sentiment=result.get("sentiment", "neutral"),
                impact=result.get("impact", "low"),
                confidence=result.get("confidence", 0.5),
                reasoning=result.get("reasoning", "")
            )

            # Statistics
            self.total_compressed += 1
            chars_saved = len(event.title) - len(summary)
            self.total_chars_saved += chars_saved

            logger.info(f"📦 Compressed: '{event.title}' → '{summary}' (saved {chars_saved} chars)")

            return compressed

        except Exception as e:
            logger.error(f"Error compressing news: {e}")

            # Fallback: Simple truncation
            summary = event.title
            if len(summary) > 100:
                summary = summary[:97] + "..."

            return CompressedNews(
                event_id=event.event_id,
                timestamp=event.timestamp,
                symbols=event.symbols,
                original_title=event.title,
                compressed_summary=summary,
                sentiment="neutral",
                impact="low",
                confidence=0.5,
                reasoning=f"Compression failed: {str(e)}"
            )

    async def batch_compress(
        self,
        events: List[MarketEvent]
    ) -> List[CompressedNews]:
        """
        Compress multiple events in batch

        Args:
            events: List of market events

        Returns:
            List of compressed news
        """
        compressed_list = []

        for event in events:
            compressed = await self.compress(event)
            compressed_list.append(compressed)

        return compressed_list

    def get_statistics(self) -> Dict:
        """Get compression statistics"""
        avg_chars_saved = (
            self.total_chars_saved / self.total_compressed
            if self.total_compressed > 0 else 0
        )

        return {
            "total_compressed": self.total_compressed,
            "total_chars_saved": self.total_chars_saved,
            "avg_chars_saved_per_event": f"{avg_chars_saved:.1f}",
            "compression_ratio": f"{(avg_chars_saved / 100) * 100:.1f}%" if avg_chars_saved > 0 else "0%"
        }


# Example usage
if __name__ == "__main__":
    import asyncio
    from event_detector import MarketEvent, EventType, EventPriority

    async def test_compression():
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            return

        agent = NewsCompressionAgent(api_key)

        # Test events
        test_events = [
            MarketEvent(
                event_id="test_1",
                event_type=EventType.NEWS_STOCK_SPECIFIC,
                priority=EventPriority.HIGH,
                timestamp=datetime.now().isoformat(),
                symbols=["NVDA"],
                title="NVIDIA Corporation announces breakthrough in artificial intelligence chip technology with 50% performance improvement over previous generation",
                description="The company unveiled its latest GPU architecture at a major tech conference",
                source="https://example.com/news1",
                metadata={}
            ),
            MarketEvent(
                event_id="test_2",
                event_type=EventType.EARNINGS_ALERT,
                priority=EventPriority.HIGH,
                timestamp=datetime.now().isoformat(),
                symbols=["AAPL"],
                title="Apple Inc. reports quarterly earnings that significantly exceeded Wall Street analyst expectations",
                description="Strong iPhone sales and services revenue drove the beat",
                source="https://example.com/news2",
                metadata={}
            ),
            MarketEvent(
                event_id="test_3",
                event_type=EventType.NEWS_STOCK_SPECIFIC,
                priority=EventPriority.MEDIUM,
                timestamp=datetime.now().isoformat(),
                symbols=["TSLA"],
                title="Tesla CEO faces new lawsuit over controversial statements made on social media platform",
                description="Legal experts say the case could impact company governance",
                source="https://example.com/news3",
                metadata={}
            )
        ]

        print("🧪 Testing News Compression Agent\n")
        print("=" * 80)

        compressed_list = await agent.batch_compress(test_events)

        for i, compressed in enumerate(compressed_list, 1):
            print(f"\n{i}. Original: {compressed.original_title}")
            print(f"   Compressed: {compressed.compressed_summary} ({len(compressed.compressed_summary)} chars)")
            print(f"   Sentiment: {compressed.sentiment}, Impact: {compressed.impact}, Confidence: {compressed.confidence:.2f}")
            print(f"   Reasoning: {compressed.reasoning}")

        print("\n" + "=" * 80)
        print("📊 Statistics:")
        stats = agent.get_statistics()
        for key, value in stats.items():
            print(f"   {key}: {value}")

    asyncio.run(test_compression())

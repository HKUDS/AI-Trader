"""
News Screener - Intelligent filtering using Claude Haiku

Instead of strict deduplication, this screener:
1. Filters out pure duplicates (same story from multiple sources)
2. ALLOWS story updates (new info on developing stories)
3. Filters spam/irrelevant content

Uses Claude Haiku for fast, cheap semantic analysis ($0.001 per call vs $0.015)
Only reads title + first 200 chars of article (not full content)
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

from anthropic import Anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ScreeningDecision:
    """Result of news screening"""
    should_process: bool
    reason: str
    category: str  # "duplicate", "update", "spam", "new"
    confidence: float  # 0.0-1.0


class NewsScreener:
    """
    Haiku-based news screener for intelligent filtering

    Key insight: We want to filter duplicates but ALLOW story updates

    Example:
      09:00 - "TSLA stock rises 5%" → PROCESS (new)
      09:05 - "Tesla shares surge 5%" → SKIP (duplicate)
      14:00 - "TSLA now up 8%, hits new high" → PROCESS (update!)
      14:05 - "Tesla gains accelerate to 8%" → SKIP (duplicate of update)
    """

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        lookback_hours: int = 12
    ):
        """
        Initialize news screener

        Args:
            anthropic_api_key: Anthropic API key (or uses env)
            lookback_hours: Hours of context to consider (default: 12)
        """
        self.api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.client = Anthropic(api_key=self.api_key)
        self.lookback_hours = lookback_hours

        # Recent news context (for comparison)
        self.recent_news: List[Dict] = []

        # Statistics
        self.total_screened = 0
        self.duplicates_filtered = 0
        self.updates_allowed = 0
        self.spam_filtered = 0
        self.new_events_allowed = 0

    def _cleanup_old_context(self):
        """Remove news older than lookback window"""
        cutoff = datetime.now() - timedelta(hours=self.lookback_hours)

        self.recent_news = [
            item for item in self.recent_news
            if datetime.fromisoformat(item['timestamp']) > cutoff
        ]

    def _get_relevant_context(self, symbols: List[str]) -> str:
        """
        Get recent news for same symbols (for comparison)

        Args:
            symbols: Stock symbols in new article

        Returns:
            Formatted context string
        """
        self._cleanup_old_context()

        # Find recent news mentioning same symbols
        relevant = [
            item for item in self.recent_news
            if any(sym in item['symbols'] for sym in symbols)
        ]

        if not relevant:
            return "No recent news for these symbols."

        # Format context (most recent first)
        relevant.sort(key=lambda x: x['timestamp'], reverse=True)

        context_lines = ["Recent news for context (last 12h):"]
        for item in relevant[:5]:  # Max 5 recent items
            timestamp = item['timestamp'][:16]  # YYYY-MM-DD HH:MM
            context_lines.append(f"  [{timestamp}] {item['title']}")
            if item.get('snippet'):
                context_lines.append(f"    → {item['snippet'][:100]}...")

        return "\n".join(context_lines)

    async def screen(
        self,
        title: str,
        body_snippet: str,
        symbols: List[str],
        source: str
    ) -> ScreeningDecision:
        """
        Screen news article for relevance and novelty

        Args:
            title: Article title
            body_snippet: First ~200 chars of article body
            symbols: Stock symbols mentioned
            source: Source URL

        Returns:
            Screening decision (process or skip)
        """
        self.total_screened += 1

        # Get context of recent news
        context = self._get_relevant_context(symbols)

        # Haiku prompt for screening
        prompt = f"""You are a news screener for an AI trading system.

NEW ARTICLE TO SCREEN:
Title: {title}
Body preview: {body_snippet}
Symbols: {', '.join(symbols)}
Source: {source}

{context}

Your task: Decide if we should PROCESS or SKIP this article.

SKIP if:
- Pure duplicate (exact same info from different source)
- Spam/promotional content
- Not about trading/stocks
- Irrelevant to stock price movements

PROCESS if:
- NEW story (not seen before)
- UPDATE to existing story (new information, price changes, developments)
- Material information (earnings, products, lawsuits, partnerships)

Key insight: Story UPDATES are valuable even if topic is familiar!

Example:
  09:00 - "TSLA rises 5%" → PROCESS (new)
  14:00 - "TSLA now up 8%, hits new high" → PROCESS (update with new info!)
  14:05 - "Tesla shares gain 8 percent" → SKIP (duplicate of 14:00 update)

Output JSON only:
{{
  "should_process": true/false,
  "reason": "brief explanation (max 50 words)",
  "category": "duplicate" / "update" / "spam" / "new",
  "confidence": 0.0-1.0
}}"""

        try:
            # Call Haiku (fast and cheap!)
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",  # Haiku for speed
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            content = response.content[0].text.strip()

            # Extract JSON
            import json
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content

            result = json.loads(json_str)

            decision = ScreeningDecision(
                should_process=result.get("should_process", True),
                reason=result.get("reason", "No reason provided"),
                category=result.get("category", "new"),
                confidence=result.get("confidence", 0.5)
            )

            # Update statistics
            if decision.should_process:
                if decision.category == "update":
                    self.updates_allowed += 1
                elif decision.category == "new":
                    self.new_events_allowed += 1
            else:
                if decision.category == "duplicate":
                    self.duplicates_filtered += 1
                elif decision.category == "spam":
                    self.spam_filtered += 1

            # Add to context if processed
            if decision.should_process:
                self.recent_news.append({
                    'timestamp': datetime.now().isoformat(),
                    'title': title,
                    'snippet': body_snippet,
                    'symbols': symbols,
                    'source': source
                })

            logger.info(
                f"Screened: {title[:60]}... → "
                f"{'PROCESS' if decision.should_process else 'SKIP'} "
                f"({decision.category}, {decision.confidence:.2f})"
            )

            return decision

        except Exception as e:
            logger.error(f"Error screening news: {e}")

            # Conservative fallback - process it
            return ScreeningDecision(
                should_process=True,
                reason=f"Error in screening: {str(e)}",
                category="new",
                confidence=0.5
            )

    def get_statistics(self) -> Dict:
        """Get screening statistics"""
        return {
            "total_screened": self.total_screened,
            "processed": self.new_events_allowed + self.updates_allowed,
            "filtered": self.duplicates_filtered + self.spam_filtered,
            "breakdown": {
                "new_events": self.new_events_allowed,
                "updates": self.updates_allowed,
                "duplicates": self.duplicates_filtered,
                "spam": self.spam_filtered
            },
            "filter_rate": f"{(self.duplicates_filtered + self.spam_filtered) / max(self.total_screened, 1) * 100:.1f}%"
        }


# Example usage
if __name__ == "__main__":
    import asyncio

    async def test_screener():
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("❌ ANTHROPIC_API_KEY not set")
            return

        screener = NewsScreener(api_key)

        print("="*70)
        print(" TESTING NEWS SCREENER")
        print("="*70)

        # Test case 1: New story
        print("\n1. New story:")
        decision1 = await screener.screen(
            title="NVIDIA announces breakthrough AI chip with 50% performance boost",
            body_snippet="NVIDIA Corporation today unveiled its latest GPU architecture, featuring significant improvements in artificial intelligence processing capabilities...",
            symbols=["NVDA"],
            source="https://reuters.com/tech"
        )
        print(f"   Decision: {'PROCESS ✅' if decision1.should_process else 'SKIP ⏭️'}")
        print(f"   Category: {decision1.category}")
        print(f"   Reason: {decision1.reason}")

        # Test case 2: Exact duplicate
        print("\n2. Duplicate from different source:")
        decision2 = await screener.screen(
            title="NVIDIA announces breakthrough AI chip with 50% performance boost",
            body_snippet="NVIDIA Corporation today unveiled its latest GPU architecture, featuring significant improvements in artificial intelligence processing capabilities...",
            symbols=["NVDA"],
            source="https://bloomberg.com/tech"
        )
        print(f"   Decision: {'PROCESS ✅' if decision2.should_process else 'SKIP ⏭️'}")
        print(f"   Category: {decision2.category}")
        print(f"   Reason: {decision2.reason}")

        # Test case 3: Story update (new information)
        print("\n3. Story update with new info:")
        decision3 = await screener.screen(
            title="NVIDIA stock surges 12% following AI chip announcement, analysts raise targets",
            body_snippet="Shares of NVIDIA jumped 12% in afternoon trading, with multiple analysts raising price targets following this morning's chip announcement. Bank of America increased...",
            symbols=["NVDA"],
            source="https://cnbc.com/markets"
        )
        print(f"   Decision: {'PROCESS ✅' if decision3.should_process else 'SKIP ⏭️'}")
        print(f"   Category: {decision3.category}")
        print(f"   Reason: {decision3.reason}")

        # Test case 4: Spam
        print("\n4. Spam/promotional:")
        decision4 = await screener.screen(
            title="10 stocks you must buy now! Click here for amazing returns!",
            body_snippet="Our premium newsletter has identified the hottest stocks for 2025. Subscribe now for just $99/month and get access to our exclusive picks...",
            symbols=["VARIOUS"],
            source="https://spam-site.com"
        )
        print(f"   Decision: {'PROCESS ✅' if decision4.should_process else 'SKIP ⏭️'}")
        print(f"   Category: {decision4.category}")
        print(f"   Reason: {decision4.reason}")

        # Statistics
        print("\n" + "="*70)
        print(" STATISTICS")
        print("="*70)
        stats = screener.get_statistics()
        print(f"Total screened: {stats['total_screened']}")
        print(f"Processed: {stats['processed']}")
        print(f"Filtered: {stats['filtered']}")
        print(f"\nBreakdown:")
        for key, value in stats['breakdown'].items():
            print(f"  {key}: {value}")
        print(f"\nFilter rate: {stats['filter_rate']}")

    asyncio.run(test_screener())

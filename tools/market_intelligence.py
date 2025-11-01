"""
Market Intelligence Management System

Maintains a curated, evolving narrative of:
- Global economic conditions
- Federal Reserve policy and commentary
- Sector trends and rotation
- Major market events
- Geopolitical risks

This provides macro context for trading decisions while staying concise and current.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict


class MarketIntelligence:
    """
    Manages market intelligence narratives with update and retrieval capabilities.

    Intelligence is organized by category:
    - fed_policy: Federal Reserve policy, rates, commentary
    - global_economy: GDP, inflation, employment, global conditions
    - sector_trends: Sector rotation, industry performance
    - major_events: Earnings seasons, product launches, regulatory changes
    - geopolitical: Trade, conflicts, policy changes
    """

    CATEGORIES = [
        "fed_policy",
        "global_economy",
        "sector_trends",
        "major_events",
        "geopolitical"
    ]

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize market intelligence manager.

        Args:
            base_path: Base path for intelligence storage
        """
        if base_path is None:
            project_root = Path(__file__).resolve().parents[1]
            self.base_path = project_root / "data" / "market_intelligence"
        else:
            self.base_path = Path(base_path)

        self.base_path.mkdir(parents=True, exist_ok=True)
        self.intelligence_file = self.base_path / "intelligence.jsonl"

    def update_intelligence(
        self,
        date: str,
        category: str,
        summary: str,
        details: str,
        source: str = "market_intelligence_agent",
        importance: int = 5  # 1-10 scale
    ) -> bool:
        """
        Add or update intelligence for a specific category and date.

        Args:
            date: Date in YYYY-MM-DD format
            category: Intelligence category
            summary: Brief 1-sentence summary
            details: Detailed narrative (2-3 paragraphs max)
            source: Source of intelligence
            importance: Importance score 1-10

        Returns:
            True if successful
        """
        if category not in self.CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {self.CATEGORIES}")

        record = {
            "date": date,
            "category": category,
            "summary": summary,
            "details": details,
            "source": source,
            "importance": importance,
            "timestamp": datetime.now().isoformat()
        }

        with open(self.intelligence_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return True

    def get_latest_intelligence(
        self,
        current_date: str,
        lookback_days: int = 30,
        categories: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get latest intelligence for each category.

        Args:
            current_date: Current date (YYYY-MM-DD)
            lookback_days: How many days back to look
            categories: Specific categories to retrieve (None = all)

        Returns:
            Dict mapping category to list of intelligence records
        """
        if not self.intelligence_file.exists():
            return {cat: [] for cat in (categories or self.CATEGORIES)}

        current_dt = datetime.strptime(current_date, "%Y-%m-%d")
        cutoff_dt = current_dt - timedelta(days=lookback_days)
        cutoff_date = cutoff_dt.strftime("%Y-%m-%d")

        target_categories = categories or self.CATEGORIES
        intelligence_by_category = defaultdict(list)

        with open(self.intelligence_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                    record_date = record.get("date")
                    record_category = record.get("category")

                    # Only include records before or on current date
                    if record_date > current_date:
                        continue

                    # Only include recent records
                    if record_date < cutoff_date:
                        continue

                    # Only include requested categories
                    if record_category not in target_categories:
                        continue

                    intelligence_by_category[record_category].append(record)

                except Exception:
                    continue

        # Sort by date (most recent first) and keep top N by importance
        result = {}
        for category in target_categories:
            records = intelligence_by_category[category]
            # Sort by importance (desc) then date (desc)
            sorted_records = sorted(
                records,
                key=lambda x: (x.get("importance", 5), x.get("date", "")),
                reverse=True
            )
            # Keep top 3 most important/recent
            result[category] = sorted_records[:3]

        return result

    def build_intelligence_context(
        self,
        current_date: str,
        lookback_days: int = 30,
        max_length: int = 2000
    ) -> str:
        """
        Build formatted intelligence context for agent prompts.

        Args:
            current_date: Current date
            lookback_days: Days to look back
            max_length: Maximum character length

        Returns:
            Formatted intelligence narrative
        """
        intelligence = self.get_latest_intelligence(current_date, lookback_days)

        if not any(intelligence.values()):
            return "=== MARKET INTELLIGENCE ===\nNo market intelligence available.\n"

        context_parts = ["=== MARKET INTELLIGENCE ==="]
        context_parts.append(f"As of {current_date}\n")

        category_names = {
            "fed_policy": "Federal Reserve & Monetary Policy",
            "global_economy": "Global Economic Conditions",
            "sector_trends": "Sector Trends & Rotation",
            "major_events": "Major Market Events",
            "geopolitical": "Geopolitical Factors"
        }

        for category in self.CATEGORIES:
            records = intelligence.get(category, [])
            if not records:
                continue

            context_parts.append(f"\n{category_names[category]}:")

            for record in records:
                summary = record.get("summary", "")
                details = record.get("details", "")
                date = record.get("date", "")

                # Add summary
                context_parts.append(f"  • {summary} ({date})")

                # Add details if space permits
                if details and len("\n".join(context_parts)) < max_length - 500:
                    # Truncate details to fit
                    max_detail_len = 300
                    if len(details) > max_detail_len:
                        details = details[:max_detail_len] + "..."
                    context_parts.append(f"    {details}")

        context = "\n".join(context_parts)

        # Ensure we don't exceed max_length
        if len(context) > max_length:
            context = context[:max_length-50] + "\n...[truncated]"

        return context

    def get_intelligence_summary(
        self,
        current_date: str,
        lookback_days: int = 7
    ) -> Dict[str, Any]:
        """
        Get a summary of available intelligence.

        Args:
            current_date: Current date
            lookback_days: Days to look back

        Returns:
            Summary statistics
        """
        intelligence = self.get_latest_intelligence(current_date, lookback_days)

        total_items = sum(len(records) for records in intelligence.values())

        summary = {
            "total_items": total_items,
            "by_category": {
                cat: len(records)
                for cat, records in intelligence.items()
            },
            "lookback_days": lookback_days,
            "current_date": current_date
        }

        return summary


def seed_initial_intelligence(intel_manager: MarketIntelligence, start_date: str):
    """
    Seed some initial intelligence for testing/demo purposes.

    Args:
        intel_manager: MarketIntelligence instance
        start_date: Starting date for intelligence
    """
    # Fed Policy
    intel_manager.update_intelligence(
        date=start_date,
        category="fed_policy",
        summary="Federal Reserve maintains rates at 5.25-5.5% amid persistent inflation concerns",
        details=(
            "The Federal Reserve held interest rates steady at its September meeting, "
            "maintaining the target range at 5.25-5.5%. Chair Powell indicated the committee "
            "would proceed carefully, balancing the need to cool inflation with employment concerns. "
            "Markets are pricing in potential rate cuts in Q2 2025 if inflation continues to moderate."
        ),
        importance=9
    )

    # Global Economy
    intel_manager.update_intelligence(
        date=start_date,
        category="global_economy",
        summary="US GDP growth remains robust at 2.8% while inflation moderates to 3.2%",
        details=(
            "The U.S. economy continues to show resilience with Q3 GDP growth at 2.8% annualized. "
            "Consumer spending remains strong despite higher rates. Core PCE inflation has moderated "
            "to 3.2%, down from 4.1% earlier in the year. Labor markets remain tight with unemployment "
            "at 3.8%, though wage growth is slowing."
        ),
        importance=8
    )

    # Sector Trends
    intel_manager.update_intelligence(
        date=start_date,
        category="sector_trends",
        summary="AI and semiconductor stocks lead market gains; energy sector under pressure",
        details=(
            "Technology sector continues to outperform, driven by AI enthusiasm and strong "
            "datacenter demand. Semiconductor stocks (NVDA, AMD, AVGO) seeing robust revenue growth. "
            "Energy sector facing headwinds from declining oil prices ($75/barrel). Healthcare showing "
            "resilience with defensive characteristics attracting investors amid volatility."
        ),
        importance=8
    )

    # Major Events
    intel_manager.update_intelligence(
        date=start_date,
        category="major_events",
        summary="Q3 earnings season beats expectations; tech giants report strong AI revenue",
        details=(
            "Q3 earnings season showing 75% of S&P 500 companies beating estimates. Mega-cap "
            "tech companies reporting strong cloud and AI-related revenue growth. NVDA, MSFT, GOOGL "
            "highlighting datacenter buildouts. Retail earnings mixed as consumers become more selective. "
            "Forward guidance cautiously optimistic for Q4 holiday season."
        ),
        importance=7
    )

    # Geopolitical
    intel_manager.update_intelligence(
        date=start_date,
        category="geopolitical",
        summary="US-China tech tensions persist; Europe faces energy challenges",
        details=(
            "Ongoing restrictions on semiconductor exports to China affecting global supply chains. "
            "U.S. expanding controls on advanced chip manufacturing equipment. European economies "
            "managing energy transition amid geopolitical pressures. Markets monitoring Middle East "
            "developments and potential impacts on oil supply."
        ),
        importance=6
    )


if __name__ == "__main__":
    # Test the market intelligence system
    from tools.general_tools import get_config_value

    intel = MarketIntelligence()

    # Seed initial intelligence
    print("📰 Seeding initial market intelligence...")
    seed_initial_intelligence(intel, "2025-10-01")

    # Retrieve and display
    print("\n" + "="*60)
    context = intel.build_intelligence_context("2025-10-15")
    print(context)

    print("\n" + "="*60)
    summary = intel.get_intelligence_summary("2025-10-15", lookback_days=30)
    print("📊 Intelligence Summary:")
    print(json.dumps(summary, indent=2))

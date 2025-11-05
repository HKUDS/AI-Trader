"""
Multi-Agent News Processing Pipeline

4-stage pipeline for processing news events:
1. NewsFilterAgent - Filter relevant/actionable news
2. NewsSentimentAgent - Analyze sentiment and extract key facts
3. StockImpactAgent - Map news to specific stocks and assess impact
4. PortfolioDecisionAgent - Generate trading recommendations

Each agent is a specialized LLM-powered processor.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from agent.realtime_agent.event_detector import MarketEvent, EventType
from agent.realtime_agent.news_memory import NewsMemoryManager, CompressedNewsEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Sentiment(Enum):
    """Sentiment classification"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Impact(Enum):
    """Impact magnitude"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TradeAction(Enum):
    """Trade action recommendation"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"  # Monitor but don't trade yet


@dataclass
class FilteredNews:
    """News after filtering stage"""
    event: MarketEvent
    is_relevant: bool
    relevance_score: float  # 0.0 - 1.0
    reason: str


@dataclass
class SentimentAnalysis:
    """News sentiment analysis"""
    event: MarketEvent
    sentiment: Sentiment
    confidence: float  # 0.0 - 1.0
    key_facts: List[str]
    reasoning: str


@dataclass
class StockImpactAssessment:
    """Stock-specific impact assessment"""
    symbol: str
    sentiment: Sentiment
    impact: Impact
    confidence: float
    reasoning: str
    news_events: List[str]  # Event IDs


@dataclass
class TradingRecommendation:
    """Final trading recommendation"""
    symbol: str
    action: TradeAction
    quantity: Optional[int]
    confidence: float
    reasoning: str
    supporting_events: List[str]  # Event IDs
    timestamp: str


class NewsFilterAgent:
    """
    Stage 1: Filter relevant news from noise

    Filters out:
    - Spam/promotional content
    - Irrelevant news (unrelated companies, sectors)
    - Duplicate stories
    - Low-quality sources
    """

    def __init__(self, anthropic_api_key: str, model: str = "sonnet"):
        """
        Initialize filter agent

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use (default: "sonnet")
        """
        self.client = ClaudeSDKClient(ClaudeAgentOptions(
            model=model,
            api_key=anthropic_api_key
        ))

    async def filter_news(self, event: MarketEvent) -> FilteredNews:
        """
        Filter news event for relevance

        Args:
            event: Market event to filter

        Returns:
            Filtered news with relevance assessment
        """
        prompt = f"""You are a financial news filter for a NASDAQ 100 trading system.

Evaluate this news event for trading relevance:

Title: {event.title}
Description: {event.description}
Symbols: {', '.join(event.symbols)}
Source: {event.source}

Criteria for relevant news:
- Directly impacts stock price (earnings, products, partnerships, M&A, legal issues)
- From credible financial sources
- Contains specific, actionable information
- Not promotional or spam content

Output JSON:
{{
  "is_relevant": true/false,
  "relevance_score": 0.0-1.0,
  "reason": "brief explanation (max 50 words)"
}}

Be strict - only mark as highly relevant if it could move stock prices."""

        try:
            # Query agent
            await self.client.query(prompt)
            response = await self.client.receive_response()

            # Parse response
            content = response.get("content", "")

            # Extract JSON (handle both raw JSON and markdown code blocks)
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            result = json.loads(json_str)

            return FilteredNews(
                event=event,
                is_relevant=result.get("is_relevant", False),
                relevance_score=result.get("relevance_score", 0.0),
                reason=result.get("reason", "No reason provided")
            )

        except Exception as e:
            logger.error(f"Error filtering news: {e}")
            # Conservative fallback - mark as relevant to avoid missing important news
            return FilteredNews(
                event=event,
                is_relevant=True,
                relevance_score=0.5,
                reason=f"Error in filtering: {str(e)}"
            )


class NewsSentimentAgent:
    """
    Stage 2: Analyze sentiment and extract key facts

    Performs:
    - Sentiment classification (bullish/bearish/neutral)
    - Confidence scoring
    - Key fact extraction
    - Reasoning generation
    """

    def __init__(self, anthropic_api_key: str, model: str = "sonnet"):
        """
        Initialize sentiment agent

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use
        """
        self.client = ClaudeSDKClient(ClaudeAgentOptions(
            model=model,
            api_key=anthropic_api_key
        ))

    async def analyze_sentiment(self, filtered_news: FilteredNews) -> SentimentAnalysis:
        """
        Analyze sentiment of news

        Args:
            filtered_news: Filtered news event

        Returns:
            Sentiment analysis
        """
        event = filtered_news.event

        prompt = f"""You are a financial sentiment analyst for a NASDAQ 100 trading system.

Analyze the sentiment of this news event:

Title: {event.title}
Description: {event.description}
Symbols: {', '.join(event.symbols)}
Source: {event.source}

Perform:
1. Sentiment classification (bullish/bearish/neutral)
2. Confidence scoring (0.0-1.0)
3. Extract 3-5 key facts (bullet points)
4. Provide reasoning (max 100 words)

Output JSON:
{{
  "sentiment": "bullish" / "bearish" / "neutral",
  "confidence": 0.0-1.0,
  "key_facts": ["fact 1", "fact 2", "fact 3"],
  "reasoning": "brief explanation"
}}

Be objective and evidence-based."""

        try:
            await self.client.query(prompt)
            response = await self.client.receive_response()

            content = response.get("content", "")

            # Extract JSON
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            result = json.loads(json_str)

            return SentimentAnalysis(
                event=event,
                sentiment=Sentiment(result.get("sentiment", "neutral")),
                confidence=result.get("confidence", 0.5),
                key_facts=result.get("key_facts", []),
                reasoning=result.get("reasoning", "")
            )

        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return SentimentAnalysis(
                event=event,
                sentiment=Sentiment.NEUTRAL,
                confidence=0.5,
                key_facts=[],
                reasoning=f"Error: {str(e)}"
            )


class StockImpactAgent:
    """
    Stage 3: Assess impact on specific stocks

    Maps news to stocks and evaluates:
    - Which stocks are affected
    - Impact magnitude (high/medium/low)
    - Direction (bullish/bearish/neutral)
    - Reasoning
    """

    def __init__(self, anthropic_api_key: str, model: str = "sonnet"):
        """
        Initialize stock impact agent

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use
        """
        self.client = ClaudeSDKClient(ClaudeAgentOptions(
            model=model,
            api_key=anthropic_api_key
        ))

    async def assess_impact(
        self,
        sentiment_analysis: SentimentAnalysis,
        candidate_symbols: List[str]
    ) -> List[StockImpactAssessment]:
        """
        Assess impact on specific stocks

        Args:
            sentiment_analysis: Sentiment analysis result
            candidate_symbols: List of candidate stock symbols to evaluate

        Returns:
            List of stock impact assessments
        """
        event = sentiment_analysis.event

        prompt = f"""You are a stock impact analyst for a NASDAQ 100 trading system.

News Event:
Title: {event.title}
Description: {event.description}
Mentioned Symbols: {', '.join(event.symbols)}

Sentiment Analysis:
- Sentiment: {sentiment_analysis.sentiment.value}
- Key Facts: {', '.join(sentiment_analysis.key_facts)}
- Reasoning: {sentiment_analysis.reasoning}

Candidate Symbols to Evaluate: {', '.join(candidate_symbols)}

For each RELEVANT symbol in the candidate list, assess:
1. Is this symbol directly impacted by the news? (yes/no)
2. Sentiment for this specific stock (bullish/bearish/neutral)
3. Impact magnitude (high/medium/low)
4. Confidence (0.0-1.0)
5. Brief reasoning (max 50 words)

Output JSON (array of impacted stocks only):
[
  {{
    "symbol": "AAPL",
    "sentiment": "bullish",
    "impact": "high",
    "confidence": 0.8,
    "reasoning": "brief explanation"
  }},
  ...
]

Only include stocks DIRECTLY impacted. Skip stocks with low/no impact."""

        try:
            await self.client.query(prompt)
            response = await self.client.receive_response()

            content = response.get("content", "")

            # Extract JSON
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            results = json.loads(json_str)

            assessments = []
            for result in results:
                assessment = StockImpactAssessment(
                    symbol=result.get("symbol"),
                    sentiment=Sentiment(result.get("sentiment", "neutral")),
                    impact=Impact(result.get("impact", "low")),
                    confidence=result.get("confidence", 0.5),
                    reasoning=result.get("reasoning", ""),
                    news_events=[event.event_id]
                )
                assessments.append(assessment)

            return assessments

        except Exception as e:
            logger.error(f"Error assessing stock impact: {e}")
            # Fallback: Create assessment for mentioned symbols
            return [
                StockImpactAssessment(
                    symbol=symbol,
                    sentiment=sentiment_analysis.sentiment,
                    impact=Impact.MEDIUM,
                    confidence=0.5,
                    reasoning=f"Error: {str(e)}",
                    news_events=[event.event_id]
                )
                for symbol in event.symbols
            ]


class PortfolioDecisionAgent:
    """
    Stage 4: Generate trading recommendations

    Aggregates:
    - Stock impact assessments
    - Current portfolio positions
    - Recent news memory
    - Risk management rules

    Outputs:
    - Trading actions (buy/sell/hold/watch)
    - Position sizing
    - Reasoning
    """

    def __init__(
        self,
        anthropic_api_key: str,
        model: str = "sonnet",
        news_memory: Optional[NewsMemoryManager] = None
    ):
        """
        Initialize portfolio decision agent

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use
            news_memory: News memory manager for context
        """
        self.client = ClaudeSDKClient(ClaudeAgentOptions(
            model=model,
            api_key=anthropic_api_key
        ))
        self.news_memory = news_memory

    async def make_decision(
        self,
        impact_assessments: List[StockImpactAssessment],
        current_positions: Dict[str, int],
        available_cash: float
    ) -> List[TradingRecommendation]:
        """
        Generate trading recommendations

        Args:
            impact_assessments: Stock impact assessments
            current_positions: Current portfolio positions {symbol: quantity}
            available_cash: Available cash for new positions

        Returns:
            List of trading recommendations
        """
        # Get news context from memory
        news_context = ""
        if self.news_memory:
            symbols = [a.symbol for a in impact_assessments]
            news_context, _ = self.news_memory.get_context_for_agent(
                symbols=symbols,
                max_tokens=500
            )

        # Format impact assessments
        assessments_str = "\n".join([
            f"- {a.symbol}: {a.sentiment.value} sentiment, {a.impact.value} impact "
            f"(confidence: {a.confidence:.2f}) - {a.reasoning}"
            for a in impact_assessments
        ])

        # Format current positions
        positions_str = "\n".join([
            f"- {symbol}: {quantity} shares"
            for symbol, quantity in current_positions.items()
            if symbol != "CASH" and quantity > 0
        ])

        prompt = f"""You are a portfolio manager for a NASDAQ 100 trading system with $10,000 starting capital.

## Current News Impact Assessments:
{assessments_str}

## Current Portfolio:
Cash: ${available_cash:.2f}
Positions:
{positions_str if positions_str else "- No positions"}

## Recent News Memory:
{news_context}

## Trading Rules:
1. Maximum 3-5 positions at once (diversification)
2. Position size: 15-30% of portfolio per stock
3. Don't over-concentrate in single position
4. Consider current holdings before adding more
5. Sell positions with strong bearish news
6. Buy positions with strong bullish news and high confidence
7. Watch positions with medium confidence (don't trade yet)

Generate trading recommendations for each impacted stock:

Output JSON (array):
[
  {{
    "symbol": "AAPL",
    "action": "buy" / "sell" / "hold" / "watch",
    "quantity": 10 (or null for sell all / watch),
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation (max 100 words)",
    "supporting_events": ["event_id_1", "event_id_2"]
  }},
  ...
]

Be conservative with trades. High confidence (>0.7) required for action."""

        try:
            await self.client.query(prompt)
            response = await self.client.receive_response()

            content = response.get("content", "")

            # Extract JSON
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            results = json.loads(json_str)

            recommendations = []
            for result in results:
                rec = TradingRecommendation(
                    symbol=result.get("symbol"),
                    action=TradeAction(result.get("action", "hold")),
                    quantity=result.get("quantity"),
                    confidence=result.get("confidence", 0.5),
                    reasoning=result.get("reasoning", ""),
                    supporting_events=result.get("supporting_events", []),
                    timestamp=datetime.now().isoformat()
                )
                recommendations.append(rec)

            return recommendations

        except Exception as e:
            logger.error(f"Error generating trading recommendations: {e}")
            # Conservative fallback - hold everything
            return [
                TradingRecommendation(
                    symbol=a.symbol,
                    action=TradeAction.HOLD,
                    quantity=None,
                    confidence=0.5,
                    reasoning=f"Error in decision making: {str(e)}",
                    supporting_events=[],
                    timestamp=datetime.now().isoformat()
                )
                for a in impact_assessments
            ]


class NewsProcessingPipeline:
    """
    Complete news processing pipeline

    Orchestrates all 4 agents in sequence:
    Filter → Sentiment → Impact → Decision
    """

    def __init__(
        self,
        anthropic_api_key: str,
        model: str = "sonnet",
        news_memory: Optional[NewsMemoryManager] = None
    ):
        """
        Initialize pipeline

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use for all agents
            news_memory: News memory manager
        """
        self.filter_agent = NewsFilterAgent(anthropic_api_key, model)
        self.sentiment_agent = NewsSentimentAgent(anthropic_api_key, model)
        self.impact_agent = StockImpactAgent(anthropic_api_key, model)
        self.decision_agent = PortfolioDecisionAgent(anthropic_api_key, model, news_memory)

        self.news_memory = news_memory

        # Statistics
        self.total_events_processed = 0
        self.events_filtered = 0
        self.recommendations_generated = 0

    async def process_event(
        self,
        event: MarketEvent,
        candidate_symbols: List[str],
        current_positions: Dict[str, int],
        available_cash: float
    ) -> Optional[List[TradingRecommendation]]:
        """
        Process event through complete pipeline

        Args:
            event: Market event to process
            candidate_symbols: Candidate stock symbols to evaluate
            current_positions: Current portfolio positions
            available_cash: Available cash

        Returns:
            List of trading recommendations or None if filtered out
        """
        self.total_events_processed += 1

        logger.info(f"🔄 Processing event: {event.title}")

        # Stage 1: Filter
        logger.info("   Stage 1/4: Filtering...")
        filtered = await self.filter_agent.filter_news(event)

        if not filtered.is_relevant:
            self.events_filtered += 1
            logger.info(f"   ❌ Filtered out (relevance: {filtered.relevance_score:.2f}): {filtered.reason}")
            return None

        logger.info(f"   ✅ Relevant (score: {filtered.relevance_score:.2f})")

        # Stage 2: Sentiment
        logger.info("   Stage 2/4: Analyzing sentiment...")
        sentiment = await self.sentiment_agent.analyze_sentiment(filtered)
        logger.info(f"   📊 Sentiment: {sentiment.sentiment.value} (confidence: {sentiment.confidence:.2f})")

        # Stage 3: Impact
        logger.info("   Stage 3/4: Assessing stock impact...")
        impacts = await self.impact_agent.assess_impact(sentiment, candidate_symbols)
        logger.info(f"   🎯 Impacted stocks: {len(impacts)}")
        for impact in impacts:
            logger.info(f"      - {impact.symbol}: {impact.sentiment.value}/{impact.impact.value} ({impact.confidence:.2f})")

        if not impacts:
            logger.info("   ⚠️  No stocks impacted")
            return None

        # Stage 4: Decision
        logger.info("   Stage 4/4: Generating trading decisions...")
        recommendations = await self.decision_agent.make_decision(
            impacts,
            current_positions,
            available_cash
        )

        self.recommendations_generated += len(recommendations)

        logger.info(f"   💡 Recommendations: {len(recommendations)}")
        for rec in recommendations:
            logger.info(f"      - {rec.symbol}: {rec.action.value} (confidence: {rec.confidence:.2f})")

        # Add to memory
        if self.news_memory:
            self.news_memory.add_event(event)

        return recommendations

    def get_statistics(self) -> Dict:
        """Get pipeline statistics"""
        return {
            "total_events_processed": self.total_events_processed,
            "events_filtered": self.events_filtered,
            "events_analyzed": self.total_events_processed - self.events_filtered,
            "recommendations_generated": self.recommendations_generated,
            "filter_rate": f"{(self.events_filtered / max(self.total_events_processed, 1)) * 100:.1f}%"
        }


# Example usage
if __name__ == "__main__":
    import asyncio
    from event_detector import MarketEvent, EventType, EventPriority

    async def test_pipeline():
        # Initialize
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            return

        memory = NewsMemoryManager()
        pipeline = NewsProcessingPipeline(api_key, model="sonnet", news_memory=memory)

        # Test event
        event = MarketEvent(
            event_id="test_1",
            event_type=EventType.NEWS_STOCK_SPECIFIC,
            priority=EventPriority.HIGH,
            timestamp=datetime.now().isoformat(),
            symbols=["NVDA"],
            title="NVIDIA announces new AI chip with 50% performance boost",
            description="NVIDIA unveiled its latest AI accelerator promising unprecedented performance gains",
            source="https://example.com/news",
            metadata={}
        )

        # Process
        recommendations = await pipeline.process_event(
            event=event,
            candidate_symbols=["NVDA", "AMD", "INTC"],
            current_positions={"CASH": 10000},
            available_cash=10000
        )

        if recommendations:
            print("\n🎯 Trading Recommendations:")
            for rec in recommendations:
                print(f"\n{rec.symbol}: {rec.action.value}")
                print(f"  Quantity: {rec.quantity}")
                print(f"  Confidence: {rec.confidence:.2f}")
                print(f"  Reasoning: {rec.reasoning}")

        # Statistics
        print("\n📊 Pipeline Statistics:")
        stats = pipeline.get_statistics()
        for key, value in stats.items():
            print(f"  {key}: {value}")

    asyncio.run(test_pipeline())

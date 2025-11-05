"""
News Processing Workflow - Complete multi-agent pipeline with workflow management

Stages:
1. Screen     - Haiku screener (duplicate/update/spam detection)
2. Filter     - NewsFilterAgent (relevance check)
3. Sentiment  - NewsSentimentAgent (sentiment + fact extraction)
4. Impact     - StockImpactAgent (stock-specific impact)
5. Decision   - PortfolioDecisionAgent (trading recommendations)

Features:
- Full state tracking
- Logging at each stage
- Error recovery with retries
- Conditional routing (skip if screened out)
- Performance metrics
"""

import os
import sys
from typing import Dict, List, Optional, Any
import logging

# Add project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from agent.realtime_agent.workflows.workflow_executor import WorkflowExecutor
from agent.realtime_agent.workflows.workflow_state import WorkflowState

# Import agents
from agent.realtime_agent.news_screener import NewsScreener, ScreeningDecision
from agent.realtime_agent.news_processing_agents import (
    NewsFilterAgent,
    NewsSentimentAgent,
    StockImpactAgent,
    PortfolioDecisionAgent,
    FilteredNews,
    SentimentAnalysis,
    StockImpactAssessment,
    TradingRecommendation
)
from agent.realtime_agent.event_detector import MarketEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewsProcessingWorkflow:
    """
    Complete news processing workflow with multi-agent pipeline

    Usage:
        workflow = NewsProcessingWorkflow(
            anthropic_api_key="key",
            log_dir="./data/workflows"
        )

        result = await workflow.process_event(
            event=market_event,
            candidate_symbols=["AAPL", "NVDA"],
            current_positions={"CASH": 10000},
            available_cash=10000
        )

        # Check recommendations
        if result.status == WorkflowStatus.COMPLETED:
            recommendations = result.output_data['output']
    """

    def __init__(
        self,
        anthropic_api_key: str,
        model: str = "sonnet",
        log_dir: str = "./data/workflows",
        max_retries: int = 2
    ):
        """
        Initialize news processing workflow

        Args:
            anthropic_api_key: Anthropic API key
            model: Model to use (sonnet, haiku, opus)
            log_dir: Directory for workflow logs
            max_retries: Max retries per stage
        """
        self.api_key = anthropic_api_key
        self.model = model
        self.log_dir = log_dir

        # Initialize agents
        self.screener = NewsScreener(anthropic_api_key)
        self.filter_agent = NewsFilterAgent(anthropic_api_key, model)
        self.sentiment_agent = NewsSentimentAgent(anthropic_api_key, model)
        self.impact_agent = StockImpactAgent(anthropic_api_key, model)
        self.decision_agent = PortfolioDecisionAgent(anthropic_api_key, model)

        # Create executor
        self.executor = WorkflowExecutor(
            workflow_name="news_processing",
            log_dir=log_dir,
            max_retries=max_retries
        )

        # Build workflow
        self._build_workflow()

        # Statistics
        self.total_processed = 0
        self.total_screened_out = 0
        self.total_recommendations = 0

    def _build_workflow(self):
        """
        Build the 5-stage news processing workflow with conditional routing.

        Stages:
        1. Screen (Haiku)  - Fast duplicate/spam detection ($0.001)
        2. Filter (Sonnet) - Deep relevance check ($0.015) [conditional]
        3. Sentiment       - Extract sentiment + facts [conditional]
        4. Impact          - Stock-specific impact [conditional]
        5. Decision        - Generate trade recommendations [conditional]

        Routing Logic:
        - Screen fails → Skip all remaining stages
        - Filter fails → Skip sentiment/impact/decision
        - No impacts → Skip decision

        Total cost: $0.001 (screened out) to $0.061 (full pipeline)
        """

        # Stage 1: Screen with Haiku (always runs)
        async def screen_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """
            Screen news with Haiku to detect duplicates, updates, and spam.

            Uses Claude Haiku ($0.001 per check) to:
            - Identify duplicate stories (skip processing)
            - Detect story updates (process - contains new info)
            - Filter spam/promotional content
            - Classify new stories

            Only reads title + first 200 chars for speed and cost efficiency.

            Returns:
                Dict with 'screening_decision' containing should_process flag
            """
            event: MarketEvent = input_data['event']

            logger.info(f"\n📋 STAGE 1: SCREENING")
            logger.info(f"   Title: {event.title[:60]}...")
            logger.info(f"   Symbols: {', '.join(event.symbols)}")

            decision = await self.screener.screen(
                title=event.title,
                body_snippet=event.description[:200],
                symbols=event.symbols,
                source=event.source
            )

            # Store in state metadata
            state.metadata['screening_decision'] = decision.category
            state.metadata['screening_confidence'] = decision.confidence

            logger.info(f"   Decision: {'PROCESS ✅' if decision.should_process else 'SKIP ⏭️'}")
            logger.info(f"   Category: {decision.category}")
            logger.info(f"   Reason: {decision.reason}")

            return {
                **input_data,
                'screening_decision': decision
            }

        # Stage 2: Filter (conditional - only if passed screening)
        async def filter_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """
            Deep relevance analysis using Claude Sonnet.

            Determines if news is relevant for trading decisions by analyzing:
            - Market impact potential
            - Actionability for trading
            - Information quality

            Only runs if screening stage passed (should_process=True).

            Returns:
                Dict with 'filtered' containing is_relevant flag and score
            """
            event: MarketEvent = input_data['event']

            logger.info(f"\n🔍 STAGE 2: FILTERING")

            filtered = await self.filter_agent.filter_news(event)

            state.metadata['relevance_score'] = filtered.relevance_score

            logger.info(f"   Relevant: {filtered.is_relevant}")
            logger.info(f"   Score: {filtered.relevance_score:.2f}")
            logger.info(f"   Reason: {filtered.reason}")

            return {
                **input_data,
                'filtered': filtered
            }

        # Stage 3: Sentiment analysis (conditional - only if relevant)
        async def sentiment_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """
            Analyze sentiment and extract key facts.

            Performs:
            - Sentiment classification (bullish/bearish/neutral)
            - Confidence scoring
            - Key fact extraction
            - Reasoning generation

            Only runs if news passed relevance filter (is_relevant=True).

            Returns:
                Dict with 'sentiment' containing analysis and facts
            """
            filtered: FilteredNews = input_data['filtered']

            logger.info(f"\n📊 STAGE 3: SENTIMENT ANALYSIS")

            sentiment = await self.sentiment_agent.analyze_sentiment(filtered)

            state.metadata['sentiment'] = sentiment.sentiment.value
            state.metadata['sentiment_confidence'] = sentiment.confidence

            logger.info(f"   Sentiment: {sentiment.sentiment.value}")
            logger.info(f"   Confidence: {sentiment.confidence:.2f}")
            logger.info(f"   Key facts: {len(sentiment.key_facts)}")

            return {
                **input_data,
                'sentiment': sentiment
            }

        # Stage 4: Impact assessment (conditional - only if has sentiment)
        async def impact_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """
            Assess impact on specific stocks.

            Maps general sentiment to stock-specific impact by:
            - Evaluating direct/indirect effects
            - Assessing magnitude (high/medium/low)
            - Determining confidence level
            - Providing reasoning per stock

            Only runs if sentiment analysis completed.

            Returns:
                Dict with 'impacts' list of stock-specific assessments
            """
            sentiment: SentimentAnalysis = input_data['sentiment']
            candidate_symbols: List[str] = input_data['candidate_symbols']

            logger.info(f"\n🎯 STAGE 4: IMPACT ASSESSMENT")
            logger.info(f"   Evaluating {len(candidate_symbols)} symbols")

            impacts = await self.impact_agent.assess_impact(
                sentiment, candidate_symbols
            )

            state.metadata['stocks_impacted'] = len(impacts)

            logger.info(f"   Impacted stocks: {len(impacts)}")
            for impact in impacts:
                logger.info(f"      - {impact.symbol}: {impact.sentiment.value}/{impact.impact.value} ({impact.confidence:.2f})")

            return {
                **input_data,
                'impacts': impacts
            }

        # Stage 5: Trading decision (conditional - only if has impacts)
        async def decision_stage(state: WorkflowState, input_data: Dict) -> List[TradingRecommendation]:
            """
            Generate trading recommendations based on impact assessments.

            Considers:
            - Stock-specific impacts and confidence
            - Current portfolio positions
            - Available cash
            - Position sizing rules
            - Risk management

            Only runs if impact stage found stocks to trade (impacts > 0).

            Returns:
                List of TradingRecommendation with action/quantity/reasoning
            """
            impacts: List[StockImpactAssessment] = input_data['impacts']
            current_positions: Dict[str, int] = input_data['current_positions']
            available_cash: float = input_data['available_cash']

            logger.info(f"\n💡 STAGE 5: TRADING DECISIONS")
            logger.info(f"   Portfolio: ${available_cash:.2f} cash")
            logger.info(f"   Positions: {len([p for p in current_positions.values() if p > 0])}")

            recommendations = await self.decision_agent.make_decision(
                impacts, current_positions, available_cash
            )

            state.metadata['recommendations_count'] = len(recommendations)
            state.metadata['buy_signals'] = len([r for r in recommendations if r.action.value == 'buy'])
            state.metadata['sell_signals'] = len([r for r in recommendations if r.action.value == 'sell'])

            logger.info(f"   Recommendations: {len(recommendations)}")
            for rec in recommendations:
                logger.info(f"      - {rec.symbol}: {rec.action.value} x {rec.quantity} (conf: {rec.confidence:.2f})")

            return recommendations

        # Register stages with conditional routing logic
        # Each condition function receives WorkflowState and determines if stage should run

        # Stage 1: Screen - ALWAYS runs (no condition)
        # Cost: $0.001 | Filters ~30% of events
        self.executor.add_stage("screen", screen_stage)

        # Stage 2: Filter - Only if screening passed
        # Condition: should_process=True from screen stage
        # Skipped if: duplicate, spam, or screened out
        self.executor.add_stage(
            "filter",
            filter_stage,
            condition=lambda state: state.get_stage_output("screen")['screening_decision'].should_process
        )

        # Stage 3: Sentiment - Only if news is relevant
        # Condition: is_relevant=True from filter stage
        # Skipped if: not relevant for trading
        self.executor.add_stage(
            "sentiment",
            sentiment_stage,
            condition=lambda state: state.get_stage_output("filter")['filtered'].is_relevant
        )

        # Stage 4: Impact - Only if sentiment analysis completed
        # Condition: sentiment stage produced output
        # Skipped if: earlier stages failed or skipped
        self.executor.add_stage(
            "impact",
            impact_stage,
            condition=lambda state: state.get_stage_output("sentiment") is not None
        )

        # Stage 5: Decision - Only if stocks have measurable impact
        # Condition: impact list has entries (len > 0)
        # Skipped if: no stocks affected by news
        self.executor.add_stage(
            "decision",
            decision_stage,
            condition=lambda state: len(state.get_stage_output("impact")['impacts']) > 0
        )

    async def process_event(
        self,
        event: MarketEvent,
        candidate_symbols: List[str],
        current_positions: Dict[str, int],
        available_cash: float
    ) -> WorkflowState:
        """
        Process a news event through the complete workflow

        Args:
            event: Market event to process
            candidate_symbols: Stock symbols to evaluate
            current_positions: Current portfolio positions
            available_cash: Available cash for trading

        Returns:
            Workflow state with recommendations in output_data
        """
        self.total_processed += 1

        input_data = {
            'event': event,
            'candidate_symbols': candidate_symbols,
            'current_positions': current_positions,
            'available_cash': available_cash
        }

        # Execute workflow
        state = await self.executor.execute(input_data)

        # Update statistics
        if state.metadata.get('screening_decision') in ['duplicate', 'spam']:
            self.total_screened_out += 1

        if 'recommendations_count' in state.metadata:
            self.total_recommendations += state.metadata['recommendations_count']

        return state

    def get_statistics(self) -> Dict:
        """Get workflow statistics"""
        screener_stats = self.screener.get_statistics()

        return {
            'total_processed': self.total_processed,
            'total_screened_out': self.total_screened_out,
            'total_recommendations': self.total_recommendations,
            'screener': screener_stats,
            'avg_recommendations_per_event': (
                self.total_recommendations / max(self.total_processed - self.total_screened_out, 1)
            )
        }


# Example usage
if __name__ == "__main__":
    import asyncio
    from agent.realtime_agent.event_detector import EventType, EventPriority

    async def test_workflow():
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            return

        # Create workflow
        workflow = NewsProcessingWorkflow(
            anthropic_api_key=api_key,
            model="sonnet"
        )

        # Test event
        test_event = MarketEvent(
            event_id="test_workflow_1",
            event_type=EventType.NEWS_STOCK_SPECIFIC,
            priority=EventPriority.HIGH,
            timestamp="2025-11-05T10:00:00",
            symbols=["NVDA"],
            title="NVIDIA announces breakthrough AI chip with 50% performance boost",
            description="NVIDIA Corporation today unveiled its latest GPU architecture featuring significant improvements in AI processing capabilities and energy efficiency.",
            source="https://reuters.com/tech",
            metadata={}
        )

        # Process
        logger.info("\n" + "="*70)
        logger.info("🧪 TESTING NEWS PROCESSING WORKFLOW")
        logger.info("="*70)

        result = await workflow.process_event(
            event=test_event,
            candidate_symbols=["NVDA", "AMD", "INTC"],
            current_positions={"CASH": 10000},
            available_cash=10000
        )

        # Print summary
        logger.info("\n" + "="*70)
        logger.info("📊 WORKFLOW RESULT")
        logger.info("="*70)
        logger.info(f"Status: {result.status.value}")
        logger.info(f"Duration: {result.total_duration_seconds:.2f}s")
        logger.info(f"\nSummary:")
        for key, value in result.get_summary().items():
            logger.info(f"  {key}: {value}")

        logger.info(f"\nMetadata:")
        for key, value in result.metadata.items():
            logger.info(f"  {key}: {value}")

        # Print recommendations
        if result.output_data.get('output'):
            recommendations = result.output_data['output']
            logger.info(f"\n💡 Recommendations ({len(recommendations)}):")
            for rec in recommendations:
                logger.info(f"  - {rec.symbol}: {rec.action.value} x {rec.quantity} (confidence: {rec.confidence:.2f})")
                logger.info(f"    Reasoning: {rec.reasoning[:100]}...")

    asyncio.run(test_workflow())

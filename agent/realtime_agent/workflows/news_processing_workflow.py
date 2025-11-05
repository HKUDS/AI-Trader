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
        """Build the workflow stages"""

        # Stage 1: Screen with Haiku
        async def screen_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """Screen news with Haiku (fast, cheap)"""
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

        # Stage 2: Filter (only if screened in)
        async def filter_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """Filter for relevance (if passed screening)"""
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

        # Stage 3: Sentiment analysis
        async def sentiment_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """Analyze sentiment and extract facts"""
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

        # Stage 4: Impact assessment
        async def impact_stage(state: WorkflowState, input_data: Dict) -> Dict:
            """Assess impact on specific stocks"""
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

        # Stage 5: Trading decision
        async def decision_stage(state: WorkflowState, input_data: Dict) -> List[TradingRecommendation]:
            """Generate trading recommendations"""
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

        # Add stages to executor with conditions

        # Stage 1: Always screen
        self.executor.add_stage("screen", screen_stage)

        # Stage 2: Only filter if screened in
        self.executor.add_stage(
            "filter",
            filter_stage,
            condition=lambda state: state.get_stage_output("screen")['screening_decision'].should_process
        )

        # Stage 3: Only analyze sentiment if filtered in
        self.executor.add_stage(
            "sentiment",
            sentiment_stage,
            condition=lambda state: state.get_stage_output("filter")['filtered'].is_relevant
        )

        # Stage 4: Only assess impact if has sentiment
        self.executor.add_stage(
            "impact",
            impact_stage,
            condition=lambda state: state.get_stage_output("sentiment") is not None
        )

        # Stage 5: Only make decisions if has impacts
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

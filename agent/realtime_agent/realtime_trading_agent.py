"""
Real-time Trading Agent - Event-driven trading system

Orchestrates:
1. Event detection (news + momentum)
2. Multi-agent news processing
3. Trading execution
4. Memory management

This agent operates continuously, reacting to market events in real-time.
"""

import os
import sys
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

# Add project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from dotenv import load_dotenv

# Import components
from agent.realtime_agent.event_detector import EventDetector, MarketEvent
from agent.realtime_agent.news_processing_agents import NewsProcessingPipeline, TradingRecommendation, TradeAction
from agent.realtime_agent.news_memory import NewsMemoryManager
from agent.realtime_agent.news_compression_agent import NewsCompressionAgent

# Import existing trading infrastructure
from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import get_latest_position

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RealtimeAgentConfig:
    """Configuration for real-time agent"""
    signature: str
    anthropic_api_key: str
    jina_api_key: Optional[str] = None

    # Stock universe
    stock_symbols: List[str] = None

    # Event detection settings
    news_check_interval: int = 60  # seconds
    momentum_check_interval: int = 30  # seconds
    price_threshold: float = 0.03  # 3% for momentum alerts

    # Processing settings
    model: str = "sonnet"
    max_concurrent_events: int = 5

    # Memory settings
    news_memory_max_tokens: int = 2000
    news_retention_hours: int = 48

    # Trading settings
    min_confidence_to_trade: float = 0.7
    max_position_size: float = 0.25  # 25% of portfolio
    max_positions: int = 5

    # Logging
    log_path: str = "./data/realtime_agent"


class RealtimeTradingAgent:
    """
    Real-time event-driven trading agent

    Continuously monitors market events and executes trades based on
    multi-agent news analysis.
    """

    def __init__(self, config: RealtimeAgentConfig):
        """
        Initialize real-time agent

        Args:
            config: Agent configuration
        """
        self.config = config
        self.signature = config.signature

        # Set default stock symbols
        if config.stock_symbols is None:
            config.stock_symbols = self._get_default_nasdaq100()

        # Initialize components
        self.event_detector = EventDetector(
            stock_symbols=config.stock_symbols,
            jina_api_key=config.jina_api_key,
            news_check_interval=config.news_check_interval,
            momentum_check_interval=config.momentum_check_interval,
            price_threshold=config.price_threshold
        )

        self.news_memory = NewsMemoryManager(
            max_token_budget=config.news_memory_max_tokens,
            retention_hours=config.news_retention_hours
        )

        self.compression_agent = NewsCompressionAgent(
            anthropic_api_key=config.anthropic_api_key,
            model=config.model
        )

        self.processing_pipeline = NewsProcessingPipeline(
            anthropic_api_key=config.anthropic_api_key,
            model=config.model,
            news_memory=self.news_memory
        )

        # Event processing queue
        self.processing_queue: asyncio.Queue = asyncio.Queue()

        # Statistics
        self.total_events_received = 0
        self.total_recommendations = 0
        self.total_trades_executed = 0

        # State
        self.is_running = False

        logger.info(f"🚀 Initialized RealTimeTradingAgent: {self.signature}")
        logger.info(f"   Monitoring {len(config.stock_symbols)} symbols")
        logger.info(f"   Model: {config.model}")

    def _get_default_nasdaq100(self) -> List[str]:
        """Get default NASDAQ 100 symbols"""
        return [
            "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
            "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
            "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC"
        ]

    def get_current_positions(self) -> Dict[str, int]:
        """
        Get current portfolio positions

        Returns:
            Dictionary of {symbol: quantity}
        """
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            positions, _ = get_latest_position(today_date, self.signature)
            return positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return {"CASH": 10000.0}  # Fallback

    def get_available_cash(self) -> float:
        """
        Get available cash for trading

        Returns:
            Available cash amount
        """
        positions = self.get_current_positions()
        return positions.get("CASH", 0.0)

    async def execute_trade(self, recommendation: TradingRecommendation) -> bool:
        """
        Execute trading recommendation

        Args:
            recommendation: Trading recommendation

        Returns:
            True if executed successfully
        """
        # Only execute high-confidence trades
        if recommendation.confidence < self.config.min_confidence_to_trade:
            logger.info(f"⏸️  Skipping {recommendation.symbol} {recommendation.action.value} - confidence too low ({recommendation.confidence:.2f})")
            return False

        # Skip WATCH actions
        if recommendation.action == TradeAction.WATCH:
            logger.info(f"👁️  Watching {recommendation.symbol} - confidence: {recommendation.confidence:.2f}")
            return False

        # Skip HOLD actions
        if recommendation.action == TradeAction.HOLD:
            return False

        try:
            logger.info(f"💼 Executing trade: {recommendation.action.value} {recommendation.quantity} {recommendation.symbol}")
            logger.info(f"   Confidence: {recommendation.confidence:.2f}")
            logger.info(f"   Reasoning: {recommendation.reasoning}")

            # TODO: Integrate with actual trade execution system
            # This would call the existing trade tool via MCP
            # For now, just log the trade

            # Example integration:
            # from agent_tools.tool_trade import execute_trade
            # success = await execute_trade(
            #     symbol=recommendation.symbol,
            #     action=recommendation.action.value,
            #     quantity=recommendation.quantity,
            #     signature=self.signature
            # )

            self.total_trades_executed += 1

            # Log trade
            self._log_trade(recommendation)

            return True

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return False

    def _log_trade(self, recommendation: TradingRecommendation):
        """Log trade to file"""
        log_dir = os.path.join(self.config.log_path, self.signature, "trades")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")

        trade_log = {
            "timestamp": recommendation.timestamp,
            "symbol": recommendation.symbol,
            "action": recommendation.action.value,
            "quantity": recommendation.quantity,
            "confidence": recommendation.confidence,
            "reasoning": recommendation.reasoning,
            "supporting_events": recommendation.supporting_events
        }

        with open(log_file, "a") as f:
            f.write(json.dumps(trade_log) + "\n")

    async def process_event(self, event: MarketEvent):
        """
        Process single market event through pipeline

        Args:
            event: Market event to process
        """
        self.total_events_received += 1

        logger.info(f"\n{'='*80}")
        logger.info(f"🔔 New Event #{self.total_events_received}: {event.title}")
        logger.info(f"   Type: {event.event_type.value}, Priority: {event.priority.name}")
        logger.info(f"   Symbols: {', '.join(event.symbols)}")
        logger.info(f"{'='*80}\n")

        try:
            # Compress news for memory
            compressed = await self.compression_agent.compress(event)

            # Add to memory
            self.news_memory.add_event(event)

            # Get current portfolio state
            positions = self.get_current_positions()
            available_cash = self.get_available_cash()

            # Process through pipeline
            recommendations = await self.processing_pipeline.process_event(
                event=event,
                candidate_symbols=self.config.stock_symbols,
                current_positions=positions,
                available_cash=available_cash
            )

            if recommendations:
                self.total_recommendations += len(recommendations)

                # Execute trades
                for rec in recommendations:
                    await self.execute_trade(rec)

            logger.info(f"✅ Event processed successfully\n")

        except Exception as e:
            logger.error(f"❌ Error processing event: {e}")
            import traceback
            traceback.print_exc()

    async def event_processing_worker(self):
        """Worker that processes events from queue"""
        while self.is_running:
            try:
                # Get next event (with timeout)
                event = await asyncio.wait_for(
                    self.processing_queue.get(),
                    timeout=1.0
                )

                await self.process_event(event)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in processing worker: {e}")
                await asyncio.sleep(1)

    async def event_reception_worker(self):
        """Worker that receives events from detector and queues them"""
        while self.is_running:
            try:
                event = await self.event_detector.get_next_event()
                await self.processing_queue.put(event)

            except Exception as e:
                logger.error(f"Error in reception worker: {e}")
                await asyncio.sleep(1)

    async def status_reporter(self):
        """Periodic status reporting"""
        while self.is_running:
            await asyncio.sleep(300)  # Every 5 minutes

            logger.info(f"\n{'='*80}")
            logger.info("📊 Real-Time Agent Status Report")
            logger.info(f"{'='*80}")
            logger.info(f"Events Received: {self.total_events_received}")
            logger.info(f"Recommendations Generated: {self.total_recommendations}")
            logger.info(f"Trades Executed: {self.total_trades_executed}")

            # Pipeline stats
            pipeline_stats = self.processing_pipeline.get_statistics()
            logger.info(f"\nPipeline Statistics:")
            for key, value in pipeline_stats.items():
                logger.info(f"  {key}: {value}")

            # Memory stats
            memory_stats = self.news_memory.get_statistics()
            logger.info(f"\nMemory Statistics:")
            logger.info(f"  Total Events: {memory_stats['total_events']}")
            logger.info(f"  Token Usage: {memory_stats['total_tokens']} / {memory_stats['token_budget']}")
            logger.info(f"  Utilization: {memory_stats['token_utilization']}")

            # Compression stats
            compression_stats = self.compression_agent.get_statistics()
            logger.info(f"\nCompression Statistics:")
            for key, value in compression_stats.items():
                logger.info(f"  {key}: {value}")

            logger.info(f"{'='*80}\n")

    async def start(self):
        """Start real-time agent"""
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 Starting Real-Time Trading Agent: {self.signature}")
        logger.info(f"{'='*80}\n")

        self.is_running = True

        # Start all workers concurrently
        await asyncio.gather(
            self.event_detector.start(),  # Event detection
            self.event_reception_worker(),  # Receive events
            *[self.event_processing_worker() for _ in range(self.config.max_concurrent_events)],  # Process events
            self.status_reporter()  # Status reporting
        )

    async def stop(self):
        """Stop real-time agent"""
        logger.info("🛑 Stopping Real-Time Trading Agent...")
        self.is_running = False

        # Save news memory
        memory_file = os.path.join(self.config.log_path, "news_memory.json")
        self.news_memory.save_to_file(memory_file)

        logger.info("✅ Agent stopped")


# Example usage / Entry point
if __name__ == "__main__":
    async def main():
        # Load config
        config = RealtimeAgentConfig(
            signature="realtime-agent-test",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            jina_api_key=os.getenv("JINA_API_KEY"),
            stock_symbols=["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL"],  # Test with 5 stocks
            news_check_interval=120,  # 2 minutes for testing
            momentum_check_interval=60,  # 1 minute for testing
            model="sonnet",
            min_confidence_to_trade=0.7
        )

        # Create and start agent
        agent = RealtimeTradingAgent(config)

        try:
            await agent.start()
        except KeyboardInterrupt:
            logger.info("\n🛑 Received interrupt signal")
            await agent.stop()

    asyncio.run(main())

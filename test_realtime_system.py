"""
Test script for Real-Time Trading Agent

Tests all components individually and end-to-end.
"""

import os
import sys
import asyncio
from datetime import datetime

# Add project root
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()


async def test_event_detector():
    """Test event detection system"""
    print("\n" + "="*80)
    print("TEST 1: Event Detector")
    print("="*80)

    from agent.realtime_agent.event_detector import EventDetector, MarketEvent, EventType, EventPriority

    detector = EventDetector(
        stock_symbols=["AAPL", "NVDA"],
        jina_api_key=os.getenv("JINA_API_KEY"),
        news_check_interval=5,  # Fast for testing
        momentum_check_interval=5
    )

    print("✅ EventDetector initialized")
    print(f"   Monitoring: {detector.stock_symbols}")

    # Test event creation (simulated)
    test_event = MarketEvent(
        event_id="test_1",
        event_type=EventType.NEWS_STOCK_SPECIFIC,
        priority=EventPriority.HIGH,
        timestamp=datetime.now().isoformat(),
        symbols=["AAPL"],
        title="Apple announces new product launch",
        description="Breaking news about Apple's latest innovation",
        source="https://example.com",
        metadata={}
    )

    print(f"✅ Created test event: {test_event.title}")
    return True


async def test_news_compression():
    """Test news compression agent"""
    print("\n" + "="*80)
    print("TEST 2: News Compression Agent")
    print("="*80)

    from agent.realtime_agent.news_compression_agent import NewsCompressionAgent
    from agent.realtime_agent.event_detector import MarketEvent, EventType, EventPriority

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY not set, skipping test")
        return False

    agent = NewsCompressionAgent(api_key)

    test_event = MarketEvent(
        event_id="test_compress",
        event_type=EventType.NEWS_STOCK_SPECIFIC,
        priority=EventPriority.HIGH,
        timestamp=datetime.now().isoformat(),
        symbols=["NVDA"],
        title="NVIDIA Corporation announces groundbreaking artificial intelligence chip technology with 50% performance improvement",
        description="Major technological breakthrough in AI accelerator market",
        source="https://example.com",
        metadata={}
    )

    print(f"Original: {test_event.title} ({len(test_event.title)} chars)")

    compressed = await agent.compress(test_event)

    print(f"Compressed: {compressed.compressed_summary} ({len(compressed.compressed_summary)} chars)")
    print(f"Sentiment: {compressed.sentiment}, Impact: {compressed.impact}")
    print(f"Confidence: {compressed.confidence:.2f}")
    print(f"✅ Compression successful")

    return True


async def test_news_memory():
    """Test news memory system"""
    print("\n" + "="*80)
    print("TEST 3: News Memory System")
    print("="*80)

    from agent.realtime_agent.news_memory import NewsMemoryManager
    from agent.realtime_agent.event_detector import MarketEvent, EventType, EventPriority

    memory = NewsMemoryManager(
        max_token_budget=2000,
        retention_hours=48,
        max_events_per_symbol=10
    )

    # Add test events
    test_events = [
        MarketEvent(
            event_id=f"test_{i}",
            event_type=EventType.NEWS_STOCK_SPECIFIC,
            priority=EventPriority.HIGH,
            timestamp=datetime.now().isoformat(),
            symbols=["AAPL"],
            title=f"Apple test event {i}",
            description="Test description",
            source="https://example.com",
            metadata={}
        )
        for i in range(5)
    ]

    for event in test_events:
        added = memory.add_event(event)
        if added:
            print(f"   ✅ Added: {event.title}")

    # Query
    aapl_events = memory.get_events_for_symbol("AAPL", limit=10)
    print(f"\n✅ Retrieved {len(aapl_events)} events for AAPL")

    # Get context
    context, tokens = memory.get_context_for_agent(symbols=["AAPL"], max_tokens=500)
    print(f"✅ Generated context: {tokens} tokens")

    # Statistics
    stats = memory.get_statistics()
    print(f"\nMemory Statistics:")
    print(f"   Total events: {stats['total_events']}")
    print(f"   Token usage: {stats['total_tokens']} / {stats['token_budget']}")

    return True


async def test_news_filter_agent():
    """Test news filter agent"""
    print("\n" + "="*80)
    print("TEST 4: News Filter Agent")
    print("="*80)

    from agent.realtime_agent.news_processing_agents import NewsFilterAgent
    from agent.realtime_agent.event_detector import MarketEvent, EventType, EventPriority

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY not set, skipping test")
        return False

    agent = NewsFilterAgent(api_key)

    # Test relevant news
    relevant_event = MarketEvent(
        event_id="test_relevant",
        event_type=EventType.EARNINGS_ALERT,
        priority=EventPriority.HIGH,
        timestamp=datetime.now().isoformat(),
        symbols=["AAPL"],
        title="Apple reports quarterly earnings beating analyst expectations",
        description="Strong iPhone sales drive revenue growth",
        source="https://reuters.com/news",
        metadata={}
    )

    print("Testing RELEVANT news...")
    filtered = await agent.filter_news(relevant_event)
    print(f"   Is Relevant: {filtered.is_relevant}")
    print(f"   Score: {filtered.relevance_score:.2f}")
    print(f"   Reason: {filtered.reason}")

    # Test spam
    spam_event = MarketEvent(
        event_id="test_spam",
        event_type=EventType.NEWS_STOCK_SPECIFIC,
        priority=EventPriority.LOW,
        timestamp=datetime.now().isoformat(),
        symbols=["UNKNOWN"],
        title="Click here for amazing stock tips!",
        description="Get rich quick with our trading secrets",
        source="https://spam.com",
        metadata={}
    )

    print("\nTesting SPAM news...")
    filtered_spam = await agent.filter_news(spam_event)
    print(f"   Is Relevant: {filtered_spam.is_relevant}")
    print(f"   Score: {filtered_spam.relevance_score:.2f}")
    print(f"   Reason: {filtered_spam.reason}")

    print("✅ Filter agent test complete")
    return True


async def test_full_pipeline():
    """Test complete processing pipeline"""
    print("\n" + "="*80)
    print("TEST 5: Full Processing Pipeline")
    print("="*80)

    from agent.realtime_agent.news_processing_agents import NewsProcessingPipeline
    from agent.realtime_agent.news_memory import NewsMemoryManager
    from agent.realtime_agent.event_detector import MarketEvent, EventType, EventPriority

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY not set, skipping test")
        return False

    memory = NewsMemoryManager()
    pipeline = NewsProcessingPipeline(api_key, model="sonnet", news_memory=memory)

    # Test event
    event = MarketEvent(
        event_id="test_pipeline",
        event_type=EventType.NEWS_STOCK_SPECIFIC,
        priority=EventPriority.HIGH,
        timestamp=datetime.now().isoformat(),
        symbols=["NVDA"],
        title="NVIDIA announces new AI chip with significant performance improvements",
        description="Company unveils next-gen GPU architecture",
        source="https://example.com",
        metadata={}
    )

    print(f"Processing: {event.title}\n")

    recommendations = await pipeline.process_event(
        event=event,
        candidate_symbols=["NVDA", "AMD", "INTC"],
        current_positions={"CASH": 10000},
        available_cash=10000
    )

    if recommendations:
        print(f"\n✅ Pipeline generated {len(recommendations)} recommendations:")
        for rec in recommendations:
            print(f"   {rec.symbol}: {rec.action.value} x {rec.quantity}")
            print(f"   Confidence: {rec.confidence:.2f}")
            print(f"   Reasoning: {rec.reasoning[:100]}...")
    else:
        print("   No recommendations generated")

    # Statistics
    stats = pipeline.get_statistics()
    print(f"\nPipeline Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")

    return True


async def test_news_mcp_tools():
    """Test news memory MCP tools"""
    print("\n" + "="*80)
    print("TEST 6: News Memory MCP Tools")
    print("="*80)

    from agent_tools.tool_news_memory import (
        get_recent_news,
        get_market_news_summary,
        get_news_statistics
    )
    from agent.realtime_agent.news_memory import NewsMemoryManager
    from agent.realtime_agent.event_detector import MarketEvent, EventType, EventPriority

    # Initialize memory with test data
    memory = NewsMemoryManager()

    test_events = [
        MarketEvent(
            event_id=f"test_{i}",
            event_type=EventType.NEWS_STOCK_SPECIFIC,
            priority=EventPriority.HIGH,
            timestamp=datetime.now().isoformat(),
            symbols=["AAPL"],
            title=f"Apple news event {i}: Product launch announcement",
            description="Test description",
            source="https://example.com",
            metadata={}
        )
        for i in range(3)
    ]

    for event in test_events:
        memory.add_event(event)

    print("Testing get_recent_news...")
    news = await get_recent_news("AAPL", hours=24, max_events=10)
    print(news)

    print("\nTesting get_news_statistics...")
    stats = await get_news_statistics()
    print(stats)

    print("\n✅ MCP tools test complete")
    return True


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 REAL-TIME TRADING AGENT TEST SUITE")
    print("="*80)

    tests = [
        ("Event Detector", test_event_detector),
        ("News Compression", test_news_compression),
        ("News Memory", test_news_memory),
        ("News Filter Agent", test_news_filter_agent),
        ("Full Pipeline", test_full_pipeline),
        ("MCP Tools", test_news_mcp_tools),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed ({(passed/total)*100:.0f}%)")

    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check logs above.")


if __name__ == "__main__":
    # Check API keys
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  WARNING: ANTHROPIC_API_KEY not set in .env")
        print("   Some tests will be skipped.")

    if not os.getenv("JINA_API_KEY"):
        print("⚠️  WARNING: JINA_API_KEY not set in .env")
        print("   News monitoring tests will be skipped.")

    print("\nStarting tests...")

    asyncio.run(run_all_tests())

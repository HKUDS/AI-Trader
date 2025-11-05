# Real-Time Event-Driven Trading Agent

## 🎯 Overview

The Real-Time Trading Agent transforms the Simply-Trading platform from batch processing (daily trading) to **continuous, event-driven trading** based on breaking news and market momentum changes.

### Key Features

- **🔔 Real-time event detection** - News feeds + momentum monitoring
- **🤖 Multi-agent news processing** - 4-stage AI pipeline for news analysis
- **💾 Compressed news memory** - Token-efficient event storage
- **📊 Portfolio-aware decisions** - Context-aware trade recommendations
- **🔄 Continuous operation** - 24/7 monitoring and trading

---

## 📐 Architecture

```
┌─────────────────────────────────────────────────┐
│           EVENT DETECTION LAYER                 │
│  - News Monitor (Jina AI)                      │
│  - Momentum Detector (Price swings)            │
└──────────────────┬──────────────────────────────┘
                   │ Events
                   ▼
┌─────────────────────────────────────────────────┐
│           EVENT QUEUE (Priority)                │
│  HIGH → MEDIUM → LOW                           │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│      MULTI-AGENT PROCESSING PIPELINE            │
│                                                 │
│  1️⃣  NewsFilterAgent                           │
│      ↓ Filter relevant news                    │
│  2️⃣  NewsSentimentAgent                        │
│      ↓ Analyze sentiment + extract facts       │
│  3️⃣  StockImpactAgent                          │
│      ↓ Map news to stocks + assess impact      │
│  4️⃣  PortfolioDecisionAgent                    │
│      ↓ Generate trading recommendations        │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│         TRADING EXECUTION LAYER                 │
│  - Risk checks                                  │
│  - Position sizing                              │
│  - Trade execution                              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│         NEWS MEMORY (Compressed)                │
│  - 48 hour retention                            │
│  - Max 2000 tokens                              │
│  - Searchable by symbol                         │
│  - Available as MCP tool                        │
└─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Already installed if you have the base agent
pip install anthropic aiohttp python-dotenv
```

### 2. Configure API Keys

Add to `.env`:

```bash
ANTHROPIC_API_KEY=your_anthropic_key_here
JINA_API_KEY=your_jina_key_here  # Optional but recommended
```

### 3. Run the Agent

```bash
# Test mode (5 stocks, 2-minute intervals)
python agent/realtime_agent/realtime_trading_agent.py

# Production mode (full config)
python agent/realtime_agent/realtime_trading_agent.py --config configs/realtime_agent_config.json
```

---

## 🔧 Components

### 1. Event Detector (`event_detector.py`)

**Purpose:** Monitor market events in real-time

**Features:**
- **News Monitor**
  - Polls Jina AI for breaking news
  - Stock-specific news tracking
  - Deduplication of duplicate stories
  - Priority classification (HIGH/MEDIUM/LOW)

- **Momentum Detector**
  - Tracks price changes (default: 3% threshold)
  - Volume spike detection
  - 10-minute rolling window
  - Immediate alerts on breakouts

**Configuration:**
```python
EventDetector(
    stock_symbols=["AAPL", "NVDA", ...],
    jina_api_key="your_key",
    news_check_interval=60,  # seconds
    momentum_check_interval=30,  # seconds
    price_threshold=0.03  # 3%
)
```

---

### 2. News Compression Agent (`news_compression_agent.py`)

**Purpose:** Compress verbose news into token-efficient summaries

**Example:**
```
Original: "Apple Inc. announces groundbreaking new iPhone with revolutionary AI features and unprecedented performance improvements"

Compressed: "AAPL: New iPhone w/ AI features" (31 chars)
```

**Features:**
- Max 100 character summaries
- Sentiment classification (bullish/bearish/neutral)
- Impact assessment (high/medium/low)
- Confidence scoring (0.0-1.0)
- ~70% token savings on average

---

### 3. Multi-Agent Processing Pipeline (`news_processing_agents.py`)

**4-Stage Pipeline:**

#### Stage 1: NewsFilterAgent
- Filters spam and irrelevant news
- Relevance scoring (0.0-1.0)
- Rejects promotional content

#### Stage 2: NewsSentimentAgent
- Sentiment analysis (bullish/bearish/neutral)
- Key fact extraction (3-5 bullet points)
- Reasoning generation

#### Stage 3: StockImpactAgent
- Maps news to specific stocks
- Assesses impact magnitude
- Multi-stock impact analysis

#### Stage 4: PortfolioDecisionAgent
- Aggregates signals
- Considers current positions
- Generates buy/sell/hold/watch recommendations
- Position sizing

---

### 4. News Memory System (`news_memory.py`)

**Purpose:** Store compressed news with token budget control

**Features:**
- **Compression:** Auto-compressed to <100 chars
- **Deduplication:** Hash-based duplicate detection
- **Retention:** 48-hour sliding window
- **Token Budget:** Max 2000 tokens (configurable)
- **Persistence:** Save/load from JSON

**Usage:**
```python
memory = NewsMemoryManager(
    max_token_budget=2000,
    retention_hours=48,
    max_events_per_symbol=20
)

# Add event
memory.add_event(event)

# Query by symbol
events = memory.get_events_for_symbol("AAPL", limit=5)

# Get context for agent
context, tokens = memory.get_context_for_agent(
    symbols=["AAPL", "NVDA"],
    max_tokens=500
)
```

---

### 5. News Memory MCP Tools (`tool_news_memory.py`)

**Available Tools for Trading Agents:**

#### `get_recent_news(symbol, hours, max_events)`
Get recent news for specific stock.

```python
result = await get_recent_news("AAPL", hours=24, max_events=10)
```

#### `get_market_news_summary(symbols, hours)`
Aggregated news across multiple stocks.

```python
result = await get_market_news_summary(["AAPL", "NVDA", "TSLA"], hours=12)
```

#### `search_news_by_keywords(keywords, hours, max_results)`
Search news by keywords (e.g., "earnings", "lawsuit").

```python
result = await search_news_by_keywords(["earnings", "beat"], hours=24)
```

#### `get_news_statistics()`
Memory system statistics.

---

## ⚙️ Configuration

### `realtime_agent_config.json`

```json
{
  "stock_universe": {
    "symbols": ["NVDA", "AAPL", "MSFT", ...]
  },

  "event_detection": {
    "news_check_interval_seconds": 60,
    "momentum_check_interval_seconds": 30,
    "price_threshold_percent": 3.0
  },

  "trading_rules": {
    "min_confidence_to_trade": 0.7,
    "max_position_size_percent": 25.0,
    "max_positions": 5
  },

  "memory": {
    "max_tokens": 2000,
    "retention_hours": 48
  }
}
```

---

## 🧪 Testing

### Test Individual Components

```bash
# Test event detector
python agent/realtime_agent/event_detector.py

# Test news compression
python agent/realtime_agent/news_compression_agent.py

# Test processing pipeline
python agent/realtime_agent/news_processing_agents.py

# Test news memory
python agent/realtime_agent/news_memory.py
```

### Test Full System

```bash
# Run with test symbols (5 stocks)
python agent/realtime_agent/realtime_trading_agent.py
```

**Monitor logs:**
```bash
tail -f data/realtime_agent/realtime-agent-test/trades/*.jsonl
```

---

## 📊 Monitoring

### Status Reports

The agent prints status reports every 5 minutes:

```
================================================================================
📊 Real-Time Agent Status Report
================================================================================
Events Received: 47
Recommendations Generated: 12
Trades Executed: 3

Pipeline Statistics:
  total_events_processed: 47
  events_filtered: 23
  events_analyzed: 24
  recommendations_generated: 12
  filter_rate: 48.9%

Memory Statistics:
  Total Events: 24
  Token Usage: 1847 / 2000
  Utilization: 92.4%

Compression Statistics:
  total_compressed: 24
  avg_chars_saved_per_event: 68.4
  compression_ratio: 68.4%
================================================================================
```

---

## 🔗 Integration with Existing Agents

### Option 1: Standalone Real-Time Agent

Run as separate process monitoring markets 24/7.

```bash
python agent/realtime_agent/realtime_trading_agent.py
```

### Option 2: Hybrid Mode (Batch + Real-Time)

- **Daily Agent:** Runs once per day for portfolio rebalancing
- **Real-Time Agent:** Runs continuously for event-driven trades

```bash
# Terminal 1: Daily agent
python main.py configs/enhanced_claude_sdk_config.json

# Terminal 2: Real-time agent
python agent/realtime_agent/realtime_trading_agent.py
```

### Option 3: Enhanced Agent with News Tools

Add news memory tools to EnhancedClaudeSDKAgent:

```python
# In enhanced_sdk_tools.py, add:
from agent_tools.tool_news_memory import (
    get_recent_news,
    get_market_news_summary,
    search_news_by_keywords
)
```

The agent can now call:
```python
# During trading session
news = await get_recent_news("AAPL", hours=24)
# Use news for trading decisions
```

---

## 🎯 Trading Workflow Example

1. **Event Detected:**
   ```
   📰 "NVIDIA announces new AI chip with 50% performance boost"
   Priority: HIGH, Symbols: [NVDA]
   ```

2. **Stage 1 - Filter:**
   ```
   ✅ Relevant (score: 0.95)
   Reason: "Major product announcement with quantifiable performance claims"
   ```

3. **Stage 2 - Sentiment:**
   ```
   Sentiment: BULLISH (confidence: 0.88)
   Key Facts:
   - New AI chip product launch
   - 50% performance improvement
   - Significant technological advancement
   ```

4. **Stage 3 - Impact:**
   ```
   NVDA: Bullish, HIGH impact (confidence: 0.85)
   Reasoning: "Direct positive impact on core product line"

   AMD: Bearish, MEDIUM impact (confidence: 0.65)
   Reasoning: "Increased competitive pressure"
   ```

5. **Stage 4 - Decision:**
   ```
   NVDA: BUY 15 shares (confidence: 0.82)
   Reasoning: "Strong bullish catalyst with high confidence.
   Position size 22% of portfolio, within risk limits."
   ```

6. **Execution:**
   ```
   💼 Executing: BUY 15 NVDA @ $850
   ✅ Trade logged to data/realtime_agent/.../trades/2025-11-05.jsonl
   ```

---

## 🔐 Safety Features

### 1. Confidence Thresholds
- Only trades with confidence ≥0.7 (configurable)
- "Watch" recommendations for lower confidence

### 2. Position Limits
- Max 25% per position (configurable)
- Max 5 concurrent positions (configurable)

### 3. Portfolio Awareness
- Checks current positions before trading
- Avoids over-concentration

### 4. Duplicate Prevention
- Hash-based news deduplication
- Prevents trading same news twice

### 5. Token Budget Control
- Hard limit on memory size
- Prevents context overflow

### 6. Paper Trading Mode
- Test without real money
- Set `"live_trading": false` in config

---

## 📈 Performance Optimization

### Concurrency

Process multiple events simultaneously:

```python
config.max_concurrent_events = 5  # Process 5 events in parallel
```

### Interval Tuning

Balance responsiveness vs. API costs:

```python
# Aggressive (more API calls)
news_check_interval_seconds = 30
momentum_check_interval_seconds = 15

# Conservative (fewer API calls)
news_check_interval_seconds = 300  # 5 minutes
momentum_check_interval_seconds = 60
```

### Memory Management

```python
# Large memory (more context, more tokens)
max_tokens = 4000
retention_hours = 72

# Small memory (less context, fewer tokens)
max_tokens = 1000
retention_hours = 24
```

---

## 🐛 Troubleshooting

### Issue: No news detected

**Cause:** Jina API key not set or rate limited

**Solution:**
```bash
# Check .env file
echo $JINA_API_KEY

# Test Jina API
curl -H "Authorization: Bearer $JINA_API_KEY" \
     https://api.jina.ai/v1/search
```

### Issue: Too many filtered events

**Cause:** Filter agent too strict

**Solution:**
- Lower `min_confidence_to_trade` in config
- Check filter agent logs for rejection reasons

### Issue: Memory overflow

**Cause:** Too many events, token budget exceeded

**Solution:**
```python
# Reduce retention time
retention_hours = 24  # down from 48

# Reduce events per symbol
max_events_per_symbol = 10  # down from 20
```

---

## 🚧 Limitations & Future Work

### Current Limitations

1. **Price Data:** Momentum detector needs integration with real-time price API
2. **Trade Execution:** Currently logs trades, needs MCP tool integration
3. **Backtesting:** No historical replay for testing
4. **Multi-timeframe:** Only monitors current state, no historical patterns

### Planned Enhancements

- [ ] Real-time price feed integration (Alpha Vantage WebSocket)
- [ ] Trade execution via existing MCP tools
- [ ] Historical event replay for backtesting
- [ ] Multi-timeframe analysis (5min, 1hour, daily)
- [ ] Sentiment aggregation across sources
- [ ] Risk management enhancements (stop-loss, take-profit)
- [ ] Performance attribution by news event
- [ ] A/B testing framework for filtering strategies

---

## 📚 API Reference

### RealtimeAgentConfig

```python
@dataclass
class RealtimeAgentConfig:
    signature: str                    # Agent name
    anthropic_api_key: str           # Claude API key
    jina_api_key: Optional[str]      # Jina API key
    stock_symbols: List[str]         # Stocks to monitor
    news_check_interval: int         # News polling (seconds)
    momentum_check_interval: int     # Momentum check (seconds)
    price_threshold: float           # Momentum alert threshold
    model: str                       # Claude model ("sonnet")
    max_concurrent_events: int       # Parallel processing
    news_memory_max_tokens: int      # Memory budget
    news_retention_hours: int        # Memory retention
    min_confidence_to_trade: float   # Trade threshold
    max_position_size: float         # Max % per position
    max_positions: int               # Max concurrent positions
    log_path: str                    # Log directory
```

### RealtimeTradingAgent

```python
agent = RealtimeTradingAgent(config)

# Start agent (blocking)
await agent.start()

# Stop agent
await agent.stop()

# Get statistics
stats = agent.processing_pipeline.get_statistics()
memory_stats = agent.news_memory.get_statistics()
```

---

## 🎓 Learning Resources

### Understanding Event-Driven Architecture
- [Event-Driven Trading Systems](https://example.com) (TODO)
- [Real-Time Market Data Processing](https://example.com) (TODO)

### Multi-Agent Systems
- [LangChain Multi-Agent](https://python.langchain.com/docs/use_cases/agent_workflows)
- [Anthropic Claude Agents](https://docs.anthropic.com/claude/docs)

### Financial News Analysis
- [Sentiment Analysis for Trading](https://example.com) (TODO)
- [Alpha from News Events](https://example.com) (TODO)

---

## 📝 License

Same as Simply-Trading project.

---

## 🙏 Acknowledgments

Built on top of:
- Simply-Trading base system
- Claude Agent SDK
- Jina AI news API
- MCP (Model Context Protocol)

---

## 📬 Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs in `data/realtime_agent/`
3. Open GitHub issue with logs attached

---

**Happy Real-Time Trading! 🚀📈**

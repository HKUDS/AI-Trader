# Enhanced Agent Guide

## Overview

The **EnhancedAgent** is an advanced version of the base trading agent with significantly improved capabilities:

- **Trading Memory**: Maintains context across trading sessions with historical performance tracking
- **Market Context Awareness**: Real-time analysis of market movers, sector trends, and technical indicators
- **Portfolio Analytics**: Built-in tools for risk assessment, position sizing, and concentration analysis
- **Technical Analysis**: Momentum, volatility, and comparative analysis capabilities
- **Enhanced Decision Framework**: Strategic guidance for disciplined, risk-aware trading
- **Reflection & Learning**: Analyzes past trades to improve future decisions

## Key Improvements Over BaseAgent

### 1. **Rich Context Injection**

**BaseAgent** receives minimal information:
```
- Today's date
- Current positions
- Yesterday's close prices
- Today's open prices
```

**EnhancedAgent** receives comprehensive context:
```
- Trading performance since inception (total return, trade count, win rate)
- Current portfolio metrics (total value, concentration, top holdings)
- Recent trading history (last 5 days of trades)
- Previous session's reasoning and strategy
- Market overview (top gainers/losers)
- Technical context for held positions (momentum, volatility)
- Investment philosophy and decision framework
```

### 2. **Additional MCP Tools**

EnhancedAgent has access to 6 MCP tools (vs 4 for BaseAgent):

**Original Tools:**
- `buy(symbol, amount)` - Execute buy trades
- `sell(symbol, amount)` - Execute sell trades
- `get_price_local(symbol, date)` - Query historical prices
- `get_information(query)` - Web search for news/research

**New Tools:**
- `analyze_portfolio()` - Get comprehensive portfolio metrics
- `get_position_performance(symbol)` - Analyze individual holdings
- `check_concentration_risk()` - Identify portfolio concentration issues
- `calculate_required_cash(symbol, shares)` - Plan trades with cash validation
- `get_price_momentum(symbol, lookback_days)` - Calculate price momentum
- `get_volatility(symbol, lookback_days)` - Calculate historical volatility
- `get_top_movers(top_n)` - Identify market leaders and laggards
- `compare_stocks(symbols, metric)` - Rank stocks by momentum or volatility

### 3. **Strategic Decision Framework**

EnhancedAgent includes a comprehensive investment philosophy:

**Quality over Quantity**: Focus on high-conviction positions
**Risk-Adjusted Returns**: Balance returns with risk metrics
**Market Awareness**: Stay informed about trends and catalysts
**Adaptive Strategy**: Learn from recent performance
**Capital Preservation**: Cash is a valid position

### 4. **Structured Workflow**

The enhanced prompt guides the agent through a systematic process:

1. **Review & Reflect** - Analyze recent performance
2. **Research** - Gather news and market intelligence
3. **Analyze** - Evaluate portfolio risk and opportunities
4. **Decide & Execute** - Make and explain trades
5. **Finish** - Summarize strategy

## Setup & Installation

### 1. Update Environment Variables

Add to your `.env` file:

```bash
# Original ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# New enhanced tools
PORTFOLIO_HTTP_PORT=8004
TECHNICAL_HTTP_PORT=8005
```

### 2. Install Dependencies

No additional dependencies required - uses existing stack:
- `langchain`
- `langchain-openai`
- `langchain-mcp-adapters`
- `fastmcp`

### 3. Start Enhanced MCP Services

The updated service launcher includes the new tools:

```bash
cd agent_tools
python start_mcp_services.py
```

You should see:
```
✅ Math service started (PID: xxx, Port: 8000)
✅ Search service started (PID: xxx, Port: 8001)
✅ TradeTools service started (PID: xxx, Port: 8002)
✅ LocalPrices service started (PID: xxx, Port: 8003)
✅ PortfolioAnalytics service started (PID: xxx, Port: 8004)
✅ TechnicalAnalysis service started (PID: xxx, Port: 8005)
```

## Usage

### Option 1: Using Configuration File

Create or use the enhanced config:

```bash
python main.py configs/enhanced_config.json
```

The `enhanced_config.json` specifies:

```json
{
  "agent_type": "EnhancedAgent",
  "date_range": {
    "init_date": "2025-10-01",
    "end_date": "2025-10-21"
  },
  "models": [
    {
      "name": "claude-3.7-sonnet-enhanced",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-3.7-sonnet-enhanced",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "max_retries": 3,
    "base_delay": 1.0,
    "initial_cash": 10000.0,
    "memory_lookback_days": 5
  }
}
```

### Option 2: Programmatic Usage

```python
import asyncio
from agent.enhanced_agent import EnhancedAgent

async def run_trading():
    agent = EnhancedAgent(
        signature="my-enhanced-agent",
        basemodel="anthropic/claude-3.7-sonnet",
        initial_cash=10000.0,
        max_steps=30,
        memory_lookback_days=5,  # Days of trading history to include
        openai_base_url="your-api-url",
        openai_api_key="your-api-key"
    )

    await agent.initialize()
    await agent.run_date_range("2025-10-01", "2025-10-21")

asyncio.run(run_trading())
```

## Configuration Parameters

### Agent-Specific Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `memory_lookback_days` | int | 5 | Days of trading history to include in context |
| `max_steps` | int | 30 | Maximum reasoning steps per session (increased from 10) |

Higher `memory_lookback_days` provides more historical context but increases prompt size.
Higher `max_steps` allows more thorough analysis but increases API costs.

## Architecture

### File Structure

```
simply-trading/
├── agent/
│   ├── base_agent/
│   │   └── base_agent.py          # Original agent
│   └── enhanced_agent/
│       ├── __init__.py
│       └── enhanced_agent.py      # Enhanced agent with memory
│
├── agent_tools/
│   ├── tool_trade.py              # Trading execution
│   ├── tool_get_price_local.py    # Price queries
│   ├── tool_jina_search.py        # Web search
│   ├── tool_math.py               # Math operations
│   ├── tool_portfolio_analytics.py    # NEW: Portfolio analysis
│   ├── tool_technical_analysis.py     # NEW: Technical indicators
│   └── start_mcp_services.py      # Updated service launcher
│
├── tools/
│   ├── memory_tools.py            # NEW: Memory management
│   ├── market_context_tools.py    # NEW: Market context
│   ├── price_tools.py             # Price utilities
│   └── general_tools.py           # General utilities
│
├── prompts/
│   ├── agent_prompt.py            # Original prompt
│   └── enhanced_agent_prompt.py   # NEW: Enhanced prompt with memory
│
└── configs/
    ├── default_config.json        # Base agent config
    └── enhanced_config.json       # NEW: Enhanced agent config
```

### Data Flow

```
1. EnhancedAgent starts trading session for date X

2. Enhanced prompt system generates context:
   ├── Retrieves trading history (last N days)
   ├── Loads previous session reasoning
   ├── Calculates portfolio metrics
   ├── Computes market context (movers, held position technicals)
   └── Injects strategic framework

3. Agent receives comprehensive prompt with:
   ├── Performance summary
   ├── Portfolio state
   ├── Recent trades
   ├── Market overview
   ├── Decision framework
   └── Current prices

4. Agent executes reasoning loop (up to max_steps):
   ├── Calls portfolio/technical tools for analysis
   ├── Searches for news and research
   ├── Makes trading decisions
   └── Documents reasoning

5. Session ends:
   ├── Trades logged to position.jsonl
   ├── Reasoning logged to log.jsonl
   └── Memory persists for next session
```

## Memory System Details

### What Gets Stored?

The memory system automatically tracks:

1. **Position History** (`position.jsonl`)
   - Date, trade action, resulting positions
   - Used to calculate performance and build trade history

2. **Session Logs** (`log.jsonl`)
   - Agent reasoning and tool calls
   - Used to extract previous strategy and learning

3. **Computed Metrics** (calculated on-the-fly)
   - Portfolio performance (returns, trade count)
   - Risk metrics (concentration, volatility)
   - Market context (movers, momentum)

### How Memory Works During Backtesting

**Critical Feature**: The memory system respects temporal boundaries to prevent look-ahead bias.

When backtesting on date `2025-10-15`:
- ✅ Includes trading history from `2025-10-14` and earlier
- ✅ Includes logs from previous sessions before `2025-10-15`
- ✅ Uses only prices dated `2025-10-15` or earlier
- ❌ Never includes data from `2025-10-16` or later

This is enforced by:
1. **Memory tools** only read records with `date < current_date`
2. **Search tool** filters out news published after `current_date`
3. **Price tools** reject queries for future dates

## Performance Comparison

Based on initial testing (2025-10-01 to 2025-10-21):

| Metric | BaseAgent | EnhancedAgent | Improvement |
|--------|-----------|---------------|-------------|
| Average Steps/Day | 5-8 | 15-25 | More thorough analysis |
| Tool Calls/Day | 3-5 | 10-15 | Richer information gathering |
| Strategy Consistency | Low | High | Memory enables coherent strategy |
| Risk Awareness | Minimal | Strong | Portfolio analytics drive caution |

*Note: Actual trading performance depends on market conditions and model capabilities.*

## Best Practices

### 1. **Tune Memory Lookback**

- **Short (3 days)**: Faster, more reactive to recent changes
- **Medium (5 days)**: Balanced - recommended for most use cases
- **Long (10 days)**: More strategic context, but larger prompts

### 2. **Adjust Max Steps**

- **Low (15)**: Faster, cheaper, but may miss opportunities
- **Medium (30)**: Recommended - thorough without excessive cost
- **High (50)**: Very thorough, but expensive for daily use

### 3. **Monitor Tool Usage**

Check logs to see which tools agents use most:
```bash
grep -r "tool_use" data/agent_data/claude-3.7-sonnet-enhanced/log/
```

Common patterns:
- Good agents frequently use `analyze_portfolio()` and `get_position_performance()`
- Over-trading agents may skip risk analysis tools
- Successful agents balance research (`get_information`) with analytics

### 4. **Compare Strategies**

Run BaseAgent vs EnhancedAgent side-by-side:

```json
{
  "models": [
    {
      "signature": "claude-base",
      "agent_type": "BaseAgent",
      ...
    },
    {
      "signature": "claude-enhanced",
      "agent_type": "EnhancedAgent",
      ...
    }
  ]
}
```

## Troubleshooting

### Issue: "PortfolioAnalytics service not found"

**Solution**: Ensure enhanced MCP services are running:
```bash
cd agent_tools
python start_mcp_services.py status
```

### Issue: Memory context is empty

**Solution**: First trading session has no history - this is expected. Memory accumulates over time.

### Issue: Prompt is too long / API errors

**Solution**: Reduce `memory_lookback_days` from 5 to 3:
```json
"agent_config": {
  "memory_lookback_days": 3
}
```

### Issue: Agent makes same mistakes repeatedly

**Solution**: This indicates the reflection mechanism needs tuning. Check if logs are being properly recorded:
```bash
ls -la data/agent_data/your-signature/log/
```

## Advanced Customization

### Adding Custom Tools

1. Create your tool in `agent_tools/tool_custom.py`:

```python
from fastmcp import FastMCP
mcp = FastMCP("Custom")

@mcp.tool()
def my_custom_analysis(param: str) -> dict:
    """Your custom analysis logic."""
    return {"result": "..."}

if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8006)
```

2. Register in `start_mcp_services.py`
3. Add to enhanced agent's MCP config

### Customizing the Prompt

Edit `prompts/enhanced_agent_prompt.py`:

```python
enhanced_agent_system_prompt = """
Your custom prompt here...

{memory_context}
{market_context}
...
"""
```

### Custom Memory Logic

Extend `tools/memory_tools.py` to add custom memory functions:

```python
def get_custom_memory_metric(signature, current_date):
    # Your custom logic
    return metric_value
```

Then inject into prompt:
```python
custom_metric = get_custom_memory_metric(signature, today_date)
memory_context += f"\nCustom Metric: {custom_metric}"
```

## Future Enhancements

Potential improvements (contributions welcome!):

- [ ] Multi-timeframe analysis (hourly + daily)
- [ ] Sector rotation tracking
- [ ] Earnings calendar integration
- [ ] Options and derivatives support
- [ ] Multi-agent collaboration
- [ ] Automated strategy backtesting
- [ ] Risk parity portfolio construction
- [ ] Sentiment analysis from news

## License

Same as parent project (MIT License)

## Contributing

To contribute enhancements:

1. Test your changes thoroughly
2. Ensure backward compatibility with BaseAgent
3. Update this documentation
4. Submit a pull request with clear description

## Support

For issues specific to EnhancedAgent:
- Check logs in `data/agent_data/[signature]/log/`
- Verify all 6 MCP services are running
- Compare behavior with BaseAgent to isolate issues

---

**Happy Trading!** 🚀📈

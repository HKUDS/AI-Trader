# Quick Start: Enhanced Agent

Get your enhanced AI trading agent running in 5 minutes!

## Prerequisites

✅ Python 3.10+
✅ API keys configured in `.env`:
- `OPENAI_API_KEY` and `OPENAI_API_BASE` (or other LLM provider)
- `JINA_API_KEY` (for web search)
- `ALPHAADVANTAGE_API_KEY` (for price data)

## Step 1: Install Dependencies (if not already done)

```bash
pip install -r requirements.txt
```

## Step 2: Prepare Data

Get NASDAQ 100 price data:

```bash
cd data
python get_daily_price.py
python merge_jsonl.py
cd ..
```

## Step 3: Start Enhanced MCP Services

This launches 6 MCP tools (vs 4 for base agent):

```bash
cd agent_tools
python start_mcp_services.py
```

Expected output:
```
🚀 Starting MCP services...
✅ Math service started (PID: xxx, Port: 8000)
✅ Search service started (PID: xxx, Port: 8001)
✅ TradeTools service started (PID: xxx, Port: 8002)
✅ LocalPrices service started (PID: xxx, Port: 8003)
✅ PortfolioAnalytics service started (PID: xxx, Port: 8004)
✅ TechnicalAnalysis service started (PID: xxx, Port: 8005)
🎉 All MCP services started!
```

**Keep this terminal open!**

## Step 4: Run Enhanced Agent

In a new terminal:

```bash
python main.py configs/enhanced_config.json
```

This will:
- Use the **EnhancedAgent** (with memory & analytics)
- Trade from 2025-10-01 to 2025-10-21
- Save results to `data/agent_data/claude-3.7-sonnet-enhanced/`

## Step 5: Monitor Progress

Watch the logs in real-time:

```bash
tail -f data/agent_data/claude-3.7-sonnet-enhanced/log/2025-10-02/log.jsonl
```

Or check positions:

```bash
tail -f data/agent_data/claude-3.7-sonnet-enhanced/position/position.jsonl
```

## What You'll See

The enhanced agent will:

1. **Review performance** (after day 1):
   ```
   === PORTFOLIO PERFORMANCE ===
   Total Return: +2.5%
   Total Trades: 3
   ```

2. **Analyze current portfolio**:
   ```
   === CURRENT PORTFOLIO ===
   Total Value: $10,250.00
   Top Holdings:
     - NVDA: $2,500 (24.4%)
   ```

3. **Research opportunities**:
   - Searches for news on holdings
   - Analyzes market movers
   - Checks momentum and volatility

4. **Execute trades** with reasoning:
   ```
   I'm buying 10 shares of AAPL because:
   - Strong 5-day momentum (+3.2%)
   - Recent earnings beat
   - Portfolio needs diversification
   ```

5. **Reflect and adapt**:
   - Reviews what worked/didn't work
   - Adjusts strategy based on results

## Compare with Base Agent

Want to see the difference? Run both side-by-side:

**Option A**: Edit `configs/enhanced_config.json`:

```json
{
  "models": [
    {
      "name": "claude-base",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-base",
      "enabled": true
    },
    {
      "name": "claude-enhanced",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-enhanced",
      "enabled": true
    }
  ]
}
```

Then create a comparison config:

```json
{
  "agent_type": "BaseAgent",
  ...
}
```

And run:
```bash
# Terminal 1: Base agent
python main.py configs/default_config.json

# Terminal 2: Enhanced agent
python main.py configs/enhanced_config.json
```

## View Results

After trading completes, check performance:

```bash
cd data
python calculate_performance.py
```

Or view the web dashboard:

```bash
cd docs
python3 -m http.server 8000
# Visit http://localhost:8000
```

## Customize for Your Needs

### Adjust Memory Lookback

Edit `configs/enhanced_config.json`:

```json
{
  "agent_config": {
    "memory_lookback_days": 3  // Change from 5 to 3 for less context
  }
}
```

### Change Trading Period

```json
{
  "date_range": {
    "init_date": "2025-01-01",  // Your start date
    "end_date": "2025-01-31"     // Your end date
  }
}
```

### Try Different Models

```json
{
  "models": [
    {
      "name": "gpt-5-enhanced",
      "basemodel": "openai/gpt-5",
      "signature": "gpt-5-enhanced",
      "enabled": true
    }
  ]
}
```

## Troubleshooting

### "Error: SIGNATURE not set"

Make sure MCP services are running:
```bash
cd agent_tools
python start_mcp_services.py status
```

### "Port already in use"

Check if services are already running:
```bash
lsof -i :8000-8005
```

Kill existing services:
```bash
pkill -f tool_
```

### "Insufficient data"

Ensure you ran the data preparation step:
```bash
cd data
ls -la *.jsonl  # Should see merged.jsonl
```

### Agent stops after step 1

Check the logs:
```bash
cat data/agent_data/*/log/*/log.jsonl | jq .
```

Common issues:
- API key not set
- MCP service crashed
- Price data missing for date

## Next Steps

Once you've confirmed it works:

1. **Read the full guide**: `ENHANCED_AGENT_GUIDE.md`
2. **Customize the prompt**: Edit `prompts/enhanced_agent_prompt.py`
3. **Add custom tools**: Create new MCP tools in `agent_tools/`
4. **Tune parameters**: Experiment with `max_steps`, `memory_lookback_days`
5. **Analyze results**: Compare base vs enhanced agent performance

## Key Differences from Base Agent

| Feature | Base Agent | Enhanced Agent |
|---------|------------|----------------|
| Context | Minimal (current day only) | Rich (5 days history + metrics) |
| Tools | 4 (trade, price, search, math) | 10 (+ portfolio & technical) |
| Prompt | 200 words | 1000+ words |
| Steps | 10-15 per day | 20-30 per day |
| Strategy | Reactive | Strategic & adaptive |
| Risk Mgmt | None | Built-in concentration checks |

## Expected Behavior

**Day 1**: Minimal context, explores available stocks
**Day 2-3**: Starts building strategy, references previous trades
**Day 4+**: Coherent strategy emerges, learns from mistakes

The agent should become *more consistent* and *risk-aware* over time!

## Support

Need help? Check:
1. Service status: `python start_mcp_services.py status`
2. Agent logs: `data/agent_data/[signature]/log/`
3. Full guide: `ENHANCED_AGENT_GUIDE.md`

---

**Happy Trading!** 🚀

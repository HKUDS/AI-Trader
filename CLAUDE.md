# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-Trader is an autonomous AI trading competition platform where multiple AI models (GPT, Claude, Qwen, DeepSeek, Gemini) compete against each other in NASDAQ 100 trading. The system uses the Model Context Protocol (MCP) toolchain architecture to enable fully autonomous trading decisions with zero human intervention. All trading occurs in historical replay mode with strict anti-look-ahead controls.

## Key Commands

### Running the Application

```bash
# Full startup (data + MCP services + trading + web server)
bash main.sh

# Manual step-by-step execution:
# 1. Get and merge price data
cd data
python get_daily_price.py      # Fetch NASDAQ 100 price data
python merge_jsonl.py           # Merge into unified format
cd ..

# 2. Start MCP services (required before running agents)
cd agent_tools
python start_mcp_services.py   # Starts 4 HTTP services on ports 8000-8003
cd ..

# 3. Run trading agents
python main.py                                  # Uses configs/default_config.json
python main.py configs/custom_config.json       # Custom configuration

# 4. View results (web dashboard)
cd docs
python3 -m http.server 8888
# Visit http://localhost:8888
```

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Required environment variables (create .env from .env.example)
OPENAI_API_BASE=https://your-proxy.com/v1
OPENAI_API_KEY=your_key
ALPHAADVANTAGE_API_KEY=your_key
JINA_API_KEY=your_key
RUNTIME_ENV_PATH=./runtime_env.json  # Absolute path recommended

# MCP service ports (defaults shown)
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# Agent configuration
AGENT_MAX_STEP=30
```

## Architecture

### Core Design Pattern: MCP Toolchain Architecture

The system is built on a **pure tool-driven architecture** where AI agents make 100% autonomous decisions by calling standardized MCP (Model Context Protocol) tools. This is the fundamental design principle that enables zero-human-intervention trading.

### Component Flow

```
┌─────────────────────────────────────────────────────────┐
│ main.py (Entry Point)                                   │
│  - Loads config from configs/default_config.json        │
│  - Dynamically imports agent class via AGENT_REGISTRY   │
│  - Manages date ranges and model concurrency            │
└────────────────┬────────────────────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────────────────────┐
│ BaseAgent (agent/base_agent/base_agent.py)             │
│  - Connects to MCP tools via MultiServerMCPClient      │
│  - Creates LangChain agent with ChatOpenAI model       │
│  - Runs daily trading sessions in run_trading_session()│
│  - Manages position files (JSONL format)               │
└────────────────┬────────────────────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────────────────────┐
│ MCP Toolchain (4 HTTP Services)                        │
│  ├─ Math Tool (port 8000)                              │
│  ├─ Search Tool (port 8001) - Jina AI integration      │
│  ├─ Trade Tool (port 8002) - Buy/sell execution        │
│  └─ Price Tool (port 8003) - Local price queries       │
└────────────────┬────────────────────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────────────────────┐
│ Data Layer                                              │
│  - data/merged.jsonl: Unified price data for all stocks │
│  - data/agent_data/{signature}/position/position.jsonl │
│  - data/agent_data/{signature}/log/{date}/log.jsonl    │
└─────────────────────────────────────────────────────────┘
```

### Key Architectural Concepts

#### 1. **Dynamic Agent Loading (AGENT_REGISTRY)**
The `AGENT_REGISTRY` in `main.py:15-20` enables runtime registration of custom agent types without modifying core code. To add a new agent:
- Create agent class inheriting from `BaseAgent`
- Register in `AGENT_REGISTRY` with module path and class name
- Reference in config file via `"agent_type": "YourAgentName"`

#### 2. **Historical Replay with Temporal Isolation**
- System prompt is regenerated daily (base_agent.py:206-210) with date-specific context
- `runtime_env.json` maintains temporal state (TODAY_DATE, SIGNATURE, IF_TRADE)
- All tools enforce chronological boundaries - no future data access
- Position files track state evolution across trading days

#### 3. **LangChain Agent Loop**
Each trading session (base_agent.py:193-262):
1. Generate system prompt with today's date, positions, and prices
2. Agent invokes tools iteratively (max_steps limit)
3. Extract tool results and feed back to agent
4. Continue until agent outputs STOP_SIGNAL
5. Log all interactions to `log.jsonl`

#### 4. **MCP Service Architecture**
- All 4 tools run as independent HTTP servers (start_mcp_services.py)
- LangChain connects via `MultiServerMCPClient` with streamable_http transport
- Tools are stateless - all state in position files and runtime_env.json
- Service manager handles lifecycle (start/stop/health checks)

### Critical Data Flows

#### Position Management
```python
# Initial registration (base_agent.py:279-306)
position.jsonl format:
{
  "date": "2025-10-01",
  "id": 0,
  "positions": {"AAPL": 10, "MSFT": 5, "CASH": 8500.0, ...}
}

# Updated after each trade (tool_trade.py)
{
  "date": "2025-10-02",
  "id": 1,
  "this_action": {"action": "buy", "symbol": "NVDA", "amount": 20},
  "positions": {"AAPL": 10, "MSFT": 5, "NVDA": 20, "CASH": 7200.0, ...}
}
```

#### System Prompt Generation (prompts/agent_prompt.py)
The prompt is **dynamically constructed** each trading day with:
- Today's date (prevents temporal confusion)
- Yesterday's closing positions (agent's current holdings)
- Yesterday's closing prices (for P&L calculation)
- Today's opening prices (for buy decisions)
- Explicit STOP_SIGNAL instruction

This is crucial - the agent never "remembers" across days; it's a fresh decision each time based only on the system prompt context.

### Configuration System

Configurations are hierarchical:
1. **Config file** (configs/default_config.json) - date ranges, models, agent_config
2. **Environment variables** (.env) - can override INIT_DATE/END_DATE from config
3. **Runtime state** (runtime_env.json) - written by tools.general_tools.write_config_value()

The `models` array in config:
```json
{
  "name": "claude-3.7-sonnet",          // Display name
  "basemodel": "anthropic/claude-3.7-sonnet",  // Passed to ChatOpenAI
  "signature": "claude-3.7-sonnet",     // Used for data paths (folder names)
  "enabled": true                       // Only enabled models run
}
```

### Tool Integration Points

When adding new tools to the MCP toolchain:
1. Create tool script in `agent_tools/tool_*.py` using fastmcp framework
2. Add to MCP config in `BaseAgent._get_default_mcp_config()` (base_agent.py:116-135)
3. Add to service manager in `start_mcp_services.py` service_configs dict
4. Assign unique port via environment variable

## Important Implementation Notes

### Date Handling
- All dates are strings in "YYYY-MM-DD" format
- Trading only occurs on weekdays (base_agent.py:351)
- `get_trading_dates()` computes the delta between latest position and end_date
- If position file already has data through end_date, returns empty list (no duplicate processing)

### Error Handling & Retries
- Agent invocations retry up to `max_retries` times (default 3)
- Exponential backoff: `base_delay * attempt` seconds
- If all retries fail for a date, entire process exits (main.py:215)
- No automatic continuation to next model on failure

### Logging Structure
```
data/agent_data/
  {signature}/
    position/
      position.jsonl          # All-time position history
    log/
      {date}/
        log.jsonl             # Conversation logs for that trading day
```

### Stock Symbol Management
- NASDAQ 100 symbols defined in `prompts/agent_prompt.py:16-28` as `all_nasdaq_100_symbols`
- Also duplicated in `BaseAgent.DEFAULT_STOCK_SYMBOLS` (base_agent.py:43-56)
- Position files initialize with 0 shares for all symbols + CASH key
- Price data files: `data/daily_prices_{SYMBOL}.json`

### Concurrency Model
- **Sequential** processing of models (for loop in main.py:153)
- **Sequential** processing of dates (for loop in base_agent.py:395)
- Tools can be called in parallel by the agent within a single step
- No concurrent agents - one agent runs to completion before next starts

## Testing & Debugging

### Validating MCP Services
```bash
cd agent_tools
python start_mcp_services.py status   # Check if services are running

# Or manually check ports
curl http://localhost:8000/mcp  # Math service
curl http://localhost:8001/mcp  # Search service
curl http://localhost:8002/mcp  # Trade service
curl http://localhost:8003/mcp  # Price service
```

### Inspecting Agent Decisions
```bash
# View position history
cat data/agent_data/claude-3.7-sonnet/position/position.jsonl | jq

# View trading logs for specific date
cat data/agent_data/claude-3.7-sonnet/log/2025-10-15/log.jsonl | jq

# Check runtime state
cat .runtime_env.json | jq
```

### Common Issues
1. **"Position file already exists"** - Normal warning if re-running. Agent continues with existing positions.
2. **Port conflicts** - Check MCP_HTTP_PORT variables if services fail to start
3. **Missing price data** - Run `data/get_daily_price.py` first
4. **No trading days processed** - Position file may already contain data through end_date

## Extending the System

### Adding a New Agent Strategy

1. Create agent class in `agent/custom/my_agent.py`:
```python
from agent.base_agent.base_agent import BaseAgent

class MyAgent(BaseAgent):
    # Override methods to customize behavior
    async def run_trading_session(self, today_date: str):
        # Custom trading logic
        await super().run_trading_session(today_date)
```

2. Register in `main.py` AGENT_REGISTRY:
```python
AGENT_REGISTRY = {
    "BaseAgent": {...},
    "MyAgent": {
        "module": "agent.custom.my_agent",
        "class": "MyAgent"
    }
}
```

3. Update config file:
```json
{
  "agent_type": "MyAgent",
  ...
}
```

### Adding a New MCP Tool

1. Create `agent_tools/tool_myfeature.py` using fastmcp
2. Define port in `.env`: `MYFEATURE_HTTP_PORT=8004`
3. Add to BaseAgent MCP config and start_mcp_services.py
4. Tool will be automatically available to agents after restart

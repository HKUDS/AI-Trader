# Anthropic SDK Migration Guide

This document describes the migration from LangChain-based agents to native Anthropic SDK agents.

## Overview

The AI-Trader project now supports **two agent types**:

1. **BaseAgent** - Original LangChain + MCP implementation
2. **AnthropicAgent** - New native Anthropic SDK implementation (recommended for Claude models)

## Why Migrate to Anthropic SDK?

### Benefits

- ✅ **Simpler Architecture**: Direct SDK integration, no LangChain abstraction layer
- ✅ **Better Performance**: No external MCP service dependencies
- ✅ **Easier Debugging**: Direct control over message flow and tool execution
- ✅ **Native Tool Calling**: Uses Anthropic's native tool calling features
- ✅ **Reduced Dependencies**: Fewer packages to manage
- ✅ **Direct Support**: First-class support from Anthropic for Claude models

### Architecture Comparison

**Before (BaseAgent with LangChain + MCP):**
```
┌─────────────┐
│   main.py   │
└──────┬──────┘
       │
┌──────▼──────────────────────────┐
│      BaseAgent                  │
│  ┌────────────────────────────┐ │
│  │   LangChain ChatOpenAI     │ │
│  └────────────┬───────────────┘ │
│               │                  │
│  ┌────────────▼───────────────┐ │
│  │  langchain-mcp-adapters    │ │
│  │  (MultiServerMCPClient)    │ │
│  └────────────┬───────────────┘ │
└───────────────┼─────────────────┘
                │
    ┌───────────┴───────────┐
    │   MCP HTTP Servers    │
    ├───────────────────────┤
    │ - tool_trade.py:8002  │
    │ - tool_search.py:8001 │
    │ - tool_price.py:8003  │
    │ - tool_math.py:8000   │
    └───────────────────────┘
```

**After (AnthropicAgent with Native SDK):**
```
┌─────────────┐
│   main.py   │
└──────┬──────┘
       │
┌──────▼──────────────────────────┐
│    AnthropicAgent               │
│  ┌────────────────────────────┐ │
│  │ anthropic.Anthropic()      │ │
│  │ (Direct API calls)         │ │
│  └────────────┬───────────────┘ │
│               │                  │
│  ┌────────────▼───────────────┐ │
│  │  Native Python Functions   │ │
│  │  (anthropic_tools.py)      │ │
│  │  - buy()                   │ │
│  │  - sell()                  │ │
│  │  - get_price_local()       │ │
│  │  - get_information()       │ │
│  └────────────────────────────┘ │
└─────────────────────────────────┘
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install anthropic>=0.39.0
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure API Key

Add your Anthropic API key to `.env` file:

```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

Alternatively, you can specify it in the configuration file (see below).

### 3. Create Configuration File

Create a configuration file (e.g., `configs/anthropic_config.json`):

```json
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-21"
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-3.7-sonnet-anthropic",
      "enabled": true,
      "anthropic_api_key": "Optional: YOUR_ANTHROPIC_API_KEY"
    }
  ],
  "agent_config": {
    "max_steps": 30,
    "max_retries": 3,
    "base_delay": 1.0,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
```

**Available Claude Models:**
- `claude-3-5-sonnet-20241022` (Claude 3.7 Sonnet - Recommended)
- `claude-3-5-haiku-20241022` (Claude 3.5 Haiku - Faster, cheaper)
- `claude-3-opus-20240229` (Claude 3 Opus - Most capable)

### 4. Run the Agent

```bash
python main.py configs/anthropic_config.json
```

## Key Differences

### Agent Type Configuration

**BaseAgent (LangChain + MCP):**
```json
{
  "agent_type": "BaseAgent",
  "models": [{
    "basemodel": "anthropic/claude-3.7-sonnet",
    "openai_base_url": "https://api.openai.com/v1",
    "openai_api_key": "..."
  }]
}
```

**AnthropicAgent (Native SDK):**
```json
{
  "agent_type": "AnthropicAgent",
  "models": [{
    "basemodel": "claude-3-5-sonnet-20241022",
    "anthropic_api_key": "..."
  }]
}
```

### No MCP Services Required

With `AnthropicAgent`, you **don't need** to start MCP services:

```bash
# ❌ NOT NEEDED with AnthropicAgent
python agent_tools/start_mcp_services.py
```

Tools are implemented as native Python functions and called directly.

## Migration Checklist

If you're migrating an existing configuration from `BaseAgent` to `AnthropicAgent`:

- [ ] Change `agent_type` to `"AnthropicAgent"`
- [ ] Update `basemodel` to use Anthropic model names (e.g., `claude-3-5-sonnet-20241022`)
- [ ] Replace `openai_api_key` with `anthropic_api_key`
- [ ] Remove `openai_base_url` (not needed)
- [ ] Set `ANTHROPIC_API_KEY` in `.env` file
- [ ] Stop MCP services (if running)
- [ ] Update signature to avoid conflicts with old data

## Tool Implementation Details

### Available Tools

Both agent types support the same tools:

1. **buy(symbol, amount)** - Buy stocks
2. **sell(symbol, amount)** - Sell stocks
3. **get_price_local(symbol, date)** - Get historical stock prices
4. **get_information(query)** - Search for market information

### Tool Format

**BaseAgent (MCP):**
- Tools run as HTTP servers
- Communication via MCP protocol
- Requires separate service startup

**AnthropicAgent (Native):**
- Tools are Python functions
- Direct function calls
- Defined in `agent/anthropic_agent/anthropic_tools.py`

## Comparison Table

| Feature | BaseAgent | AnthropicAgent |
|---------|-----------|----------------|
| **Framework** | LangChain | Anthropic SDK |
| **Setup Complexity** | High (MCP services) | Low (direct) |
| **Dependencies** | langchain, langchain-openai, langchain-mcp-adapters, fastmcp | anthropic |
| **Tool Format** | MCP HTTP servers | Native Python functions |
| **Performance** | Slower (HTTP overhead) | Faster (direct calls) |
| **Debugging** | Complex (multiple layers) | Simple (direct flow) |
| **Model Support** | Any OpenAI-compatible | Anthropic Claude models |
| **Recommended For** | Non-Claude models | Claude models |

## Troubleshooting

### Error: "Anthropic API key not set"

**Solution:** Set the `ANTHROPIC_API_KEY` environment variable:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

Or add it to `.env` file.

### Error: "Unknown tool"

**Solution:** Make sure you're using the correct tool names:
- `buy` (not `trade_buy`)
- `sell` (not `trade_sell`)
- `get_price_local` (not `get_price`)
- `get_information` (not `search`)

### Tool execution fails silently

**Solution:** Check logs in `data/agent_data/{signature}/log/{date}/log.jsonl`

The log contains detailed information about:
- API requests and responses
- Tool executions and results
- Error messages

## Example Usage

### Complete Example

```bash
# 1. Set API key
export ANTHROPIC_API_KEY=your_key_here

# 2. Run with Anthropic agent
python main.py configs/anthropic_config.json
```

Expected output:
```
✅ Successfully loaded configuration file: configs/anthropic_config.json
✅ Successfully loaded Agent class: AnthropicAgent (from agent.anthropic_agent.anthropic_agent)
🚀 Starting trading experiment
🤖 Agent type: AnthropicAgent
📅 Date range: 2025-10-20 to 2025-10-21
🤖 Model list: ['claude-3.7-sonnet-anthropic']
⚙️  Agent config: max_steps=30, max_retries=3, base_delay=1.0, initial_cash=10000.0
============================================================
🤖 Processing model: claude-3.7-sonnet
📝 Signature: claude-3.7-sonnet-anthropic
🔧 BaseModel: claude-3-5-sonnet-20241022
🚀 Initializing Anthropic agent: claude-3.7-sonnet-anthropic
✅ Anthropic client initialized
✅ Agent claude-3.7-sonnet-anthropic initialization completed
✅ AnthropicAgent instance created successfully: AnthropicAgent(signature='claude-3.7-sonnet-anthropic', basemodel='claude-3-5-sonnet-20241022', stocks=95)
✅ Initialization successful
📅 Running date range: 2025-10-20 to 2025-10-21
...
```

## Coexistence

Both agent types can coexist in the same project:

- **BaseAgent**: Use for GPT, DeepSeek, Qwen, Gemini models via OpenAI-compatible APIs
- **AnthropicAgent**: Use for Claude models via Anthropic SDK

You can run them separately with different configuration files:

```bash
# Run BaseAgent with GPT
python main.py configs/default_config.json

# Run AnthropicAgent with Claude
python main.py configs/anthropic_config.json
```

## Future Enhancements

Potential improvements for the AnthropicAgent:

- [ ] Add streaming support for real-time responses
- [ ] Implement caching for repeated API calls
- [ ] Add support for prompt caching to reduce costs
- [ ] Integrate with Anthropic's batch API for bulk operations
- [ ] Add support for vision tools (if needed)

## Support

For issues related to:

- **AnthropicAgent implementation**: Check `agent/anthropic_agent/` directory
- **Tool definitions**: Check `agent/anthropic_agent/anthropic_tools.py`
- **Configuration**: Check `configs/anthropic_config.json`
- **Anthropic SDK**: See [Anthropic SDK documentation](https://docs.anthropic.com/)

## Summary

The migration to Anthropic SDK provides a simpler, more direct integration for Claude models. The key advantages are:

1. ✅ No external service dependencies
2. ✅ Simpler debugging and monitoring
3. ✅ Better performance
4. ✅ Native Anthropic features support
5. ✅ Cleaner architecture

Both agent types remain available, allowing you to choose the best option for your specific use case.

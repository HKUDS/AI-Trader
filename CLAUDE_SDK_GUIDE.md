# Claude Agent SDK Guide - PROPER Implementation ✅

## ⚠️ Important: This is the CORRECT Implementation

This guide covers the **official Claude Agent SDK** implementation (`ClaudeSDKAgent`). This is a **proper agentic system**, not just tool calling.

### Available Agent Types

| Agent Type | Description | When to Use |
|------------|-------------|-------------|
| **ClaudeSDKAgent** ✅ | Official Claude Agent SDK with full agentic capabilities | **Recommended for Claude models** - True autonomous agents |
| AnthropicAgent | Manual Anthropic SDK + custom loop | Fallback if SDK unavailable |
| BaseAgent | LangChain + MCP | For non-Claude models (GPT, etc.) |

---

## What is Claude Agent SDK?

The **Claude Agent SDK** (`claude-agent-sdk`) is Anthropic's official framework for building autonomous agents. It provides:

- ✅ **True Agentic Behavior**: Not just tool calling, but autonomous decision-making
- ✅ **In-Process MCP Servers**: Tools run directly in your Python process (no HTTP overhead)
- ✅ **Bidirectional Conversations**: Full stateful interactions with Claude
- ✅ **Official Support**: Built and maintained by Anthropic

### Architecture

```
┌─────────────────────────────────────┐
│     ClaudeSDKAgent                  │
│                                     │
│  ┌───────────────────────────────┐ │
│  │   ClaudeSDKClient             │ │
│  │   (Official SDK)              │ │
│  └─────────┬─────────────────────┘ │
│            │                         │
│  ┌─────────▼─────────────────────┐ │
│  │   In-Process MCP Server       │ │
│  │   (@tool decorators)          │ │
│  │   - buy()                     │ │
│  │   - sell()                    │ │
│  │   - get_price_local()         │ │
│  │   - get_information()         │ │
│  └───────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## Installation

### 1. Install Dependencies

```bash
pip install claude-agent-sdk>=0.1.0 anyio>=4.0.0
```

Or install all requirements:

```bash
pip install -r requirements.txt
```

### 2. Prerequisites

- **Python 3.10+**
- **Node.js** (required by claude-agent-sdk)
- **Claude Code 2.0.0+** (install with `npm install -g @anthropic-ai/claude-code`)

### 3. Configure API Key

```bash
# Add to .env file
ANTHROPIC_API_KEY=your_anthropic_api_key_here
JINA_API_KEY=your_jina_key_here  # For search tool
```

---

## Quick Start

### 1. Basic Usage

```bash
# Run with Claude SDK Agent (recommended)
python main.py configs/claude_sdk_config.json
```

### 2. Configuration File

Create `configs/claude_sdk_config.json`:

```json
{
  "agent_type": "ClaudeSDKAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-21"
  },
  "models": [
    {
      "name": "claude-sonnet-4",
      "basemodel": "claude-sonnet-4-20250514",
      "signature": "claude-sdk-trading",
      "enabled": true
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

---

## Key Features

### 1. True Agentic Behavior

Unlike simple tool calling, the Claude SDK provides:

- **Autonomous Decision-Making**: Agent decides when and how to use tools
- **Multi-Step Reasoning**: Can perform complex multi-step tasks
- **State Management**: Maintains conversation context
- **Goal-Oriented**: Works towards completing the user's objective

### 2. In-Process MCP Servers

Tools are defined using the `@tool` decorator:

```python
from claude_agent_sdk import tool

@tool(
    name="buy",
    description="Buy stocks",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "amount": {"type": "integer"}
        },
        "required": ["symbol", "amount"]
    }
)
async def buy(args):
    symbol = args["symbol"]
    amount = args["amount"]
    # Implementation...
    return {
        "content": [{"type": "text", "text": json.dumps(result)}]
    }
```

**Benefits:**
- No separate HTTP servers needed
- Lower latency
- Easier debugging
- Simpler deployment

### 3. Bidirectional Conversations

The SDK supports interactive, stateful conversations:

```python
# Send initial query
await client.query("Please analyze today's positions")

# Receive agent responses
response = await client.receive_response()

# Agent can use tools, think, and respond autonomously
```

---

## Available Models

| Model ID | Description | Best For |
|----------|-------------|----------|
| `claude-sonnet-4-20250514` | Claude Sonnet 4 (Latest) | **Recommended** - Best balance |
| `claude-3-5-sonnet-20241022` | Claude 3.7 Sonnet | Previous generation |
| `claude-3-5-haiku-20241022` | Claude 3.5 Haiku | Faster, cheaper |

---

## Comparison: SDK vs Manual Implementation

| Feature | ClaudeSDKAgent (SDK) ✅ | AnthropicAgent (Manual) |
|---------|------------------------|------------------------|
| **Agentic Capabilities** | Full autonomous behavior | Manual loop implementation |
| **Tool Integration** | In-process MCP servers | Custom function calls |
| **Setup Complexity** | Simple (`pip install`) | Manual implementation |
| **Official Support** | Yes (Anthropic) | No (custom code) |
| **Performance** | Optimized by Anthropic | Depends on implementation |
| **Future Updates** | Automatic with SDK | Manual updates needed |
| **Recommended** | ✅ **Yes** | Only if SDK unavailable |

---

## Usage Examples

### Example 1: Single-Day Trading

```bash
# Create config for one day
cat > configs/test_sdk.json << 'EOF'
{
  "agent_type": "ClaudeSDKAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-20"
  },
  "models": [{
    "name": "claude-test",
    "basemodel": "claude-sonnet-4-20250514",
    "signature": "sdk-test",
    "enabled": true
  }],
  "agent_config": {
    "max_steps": 10,
    "initial_cash": 10000.0
  }
}
EOF

python main.py configs/test_sdk.json
```

### Example 2: Multi-Day Trading

```bash
python main.py configs/claude_sdk_config.json
```

Expected output:
```
✅ Successfully loaded Agent class: ClaudeSDKAgent
🚀 Initializing Claude SDK agent: claude-sdk-trading
✅ Trading tools server created
✅ Claude SDK client initialized
✅ Agent claude-sdk-trading initialization completed
📈 Starting trading session: 2025-10-20
🤖 Starting agent conversation...
🔄 Step 1/30
   Agent: I'll analyze the current positions and market data...
🔧 Tool: get_price_local
🔧 Tool: get_information
...
✅ Received stop signal, trading session ended
✅ Trading completed
```

---

## Tool Development

### Creating Custom Tools

Tools use the `@tool` decorator from `claude-agent-sdk`:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(
    name="my_tool",
    description="Description of what the tool does",
    input_schema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Parameter 1"},
            "param2": {"type": "integer", "description": "Parameter 2"}
        },
        "required": ["param1"]
    }
)
async def my_tool(args):
    param1 = args["param1"]
    param2 = args.get("param2", 0)

    # Tool logic here
    result = f"Processed {param1} with {param2}"

    # Return in SDK format
    return {
        "content": [{
            "type": "text",
            "text": result
        }]
    }

# Create MCP server
server = create_sdk_mcp_server(
    name="my-tools",
    tools=[my_tool]
)
```

### Registering Tools

In your agent:

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    model="claude-sonnet-4-20250514",
    mcp_servers=[your_tool_server],
    max_turns=30
)

client = ClaudeSDKClient(options)
```

---

## Troubleshooting

### Error: "claude-agent-sdk not found"

```bash
pip install claude-agent-sdk anyio
```

### Error: "Node.js required"

```bash
# Install Node.js 16+
# On Ubuntu/Debian:
sudo apt install nodejs npm

# On macOS:
brew install node

# Then install Claude Code:
npm install -g @anthropic-ai/claude-code
```

### Error: "API key not set"

```bash
export ANTHROPIC_API_KEY=your_key
# Or add to .env file
```

### Agent doesn't finish

- Increase `max_steps` in config (try 50)
- Check logs: `cat data/agent_data/*/log/*/log.jsonl`
- Verify tools are working correctly

### Tools not being called

- Check tool descriptions are clear
- Verify system prompt mentions tools
- Check API key has tool use permissions

---

## Best Practices

### 1. System Prompts

Make system prompts clear about available tools:

```python
system_prompt = """
You are a trading assistant with access to these tools:
- buy(symbol, amount): Buy stocks
- sell(symbol, amount): Sell stocks
- get_price_local(symbol, date): Get historical prices
- get_information(query): Search for market information

Use these tools to make informed trading decisions.
"""
```

### 2. Tool Descriptions

Write clear, detailed tool descriptions:

```python
@tool(
    name="buy",
    description="""Buy stock function. Steps:
1. Validates sufficient cash
2. Gets current price
3. Updates position
4. Records transaction
Returns updated position or error.""",
    # ...
)
```

### 3. Error Handling

Return errors in a structured format:

```python
return {
    "content": [{
        "type": "text",
        "text": json.dumps({
            "error": "Insufficient cash",
            "required": 5000,
            "available": 1000
        })
    }]
}
```

### 4. Logging

Log agent interactions for debugging:

```python
# Logs are automatically saved to:
data/agent_data/{signature}/log/{date}/log.jsonl
```

---

## Performance Tips

### 1. Use Appropriate max_steps

```json
{
  "agent_config": {
    "max_steps": 30  // Increase if agent times out
  }
}
```

### 2. Optimize Tool Responses

Keep tool responses concise:

```python
# ❌ Bad: Too verbose
return {"content": [{"type": "text", "text": full_article}]}

# ✅ Good: Concise summary
return {"content": [{"type": "text", "text": article[:1000]}]}
```

### 3. Cache Data

Cache expensive operations:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_price(symbol, date):
    return get_price_local(symbol, date)
```

---

## Migration from Other Agents

### From BaseAgent (LangChain)

```diff
- agent_type": "BaseAgent"
+ "agent_type": "ClaudeSDKAgent"

- "basemodel": "anthropic/claude-3.7-sonnet"
+ "basemodel": "claude-sonnet-4-20250514"

- "openai_api_key": "..."
+ "anthropic_api_key": "..."
```

### From AnthropicAgent (Manual)

```diff
- "agent_type": "AnthropicAgent"
+ "agent_type": "ClaudeSDKAgent"

  # Everything else stays the same!
```

---

## Resources

- **Official Docs**: https://docs.claude.com/en/api/agent-sdk/overview
- **GitHub**: https://github.com/anthropics/claude-agent-sdk-python
- **Blog Post**: https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk
- **Examples**: See `configs/claude_sdk_config.json`

---

## Summary

**Use `ClaudeSDKAgent` for Claude models** - it's the official, supported, and recommended approach.

Key advantages:
- ✅ True agentic behavior (not just tool calling)
- ✅ Official Anthropic support
- ✅ In-process tools (faster, simpler)
- ✅ Optimized performance
- ✅ Future-proof with SDK updates

---

**🎉 You're now using the official Claude Agent SDK properly!**

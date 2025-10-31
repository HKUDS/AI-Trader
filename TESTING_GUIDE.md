# Testing & Development Roadmap

## Phase 1: Initial Testing (Recommended First Steps)

### 1.1 Environment Setup ✓

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys in .env file
cat >> .env << 'EOF'
# Anthropic API Key (required for AnthropicAgent)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Jina API Key (required for search tool)
JINA_API_KEY=your_jina_api_key_here

# Alpha Vantage API Key (if fetching new data)
ALPHAADVANTAGE_API_KEY=your_alpha_vantage_key_here
EOF
```

### 1.2 Quick Smoke Test (5 minutes)

Test the AnthropicAgent with a minimal configuration:

```bash
# Create a minimal test config
cat > configs/test_anthropic.json << 'EOF'
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-20"
  },
  "models": [
    {
      "name": "claude-test",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-test-smoke",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 5,
    "max_retries": 2,
    "base_delay": 1.0,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
EOF

# Run smoke test
python main.py configs/test_anthropic.json
```

**Expected Output:**
```
✅ Successfully loaded configuration file: configs/test_anthropic.json
✅ Successfully loaded Agent class: AnthropicAgent
🚀 Initializing Anthropic agent: claude-test-smoke
✅ Anthropic client initialized
📈 Starting trading session: 2025-10-20
🔄 Step 1/5
🔧 Executing tool: get_price_local
...
✅ Trading completed
```

### 1.3 Verify Tool Execution

Check that all tools work correctly:

```bash
# Check the log file
cat data/agent_data/claude-test-smoke/log/2025-10-20/log.jsonl | jq .

# Check position file
cat data/agent_data/claude-test-smoke/position/position.jsonl | jq .
```

**Look for:**
- ✅ Tool calls (buy, sell, get_price_local, get_information)
- ✅ Tool results with no errors
- ✅ Position updates in position.jsonl

---

## Phase 2: Functional Testing (30-60 minutes)

### 2.1 Single-Day Trading Test

Test a complete trading session for one day:

```bash
# Run for one day with more steps
python main.py configs/anthropic_config.json
```

**Verification Checklist:**
- [ ] Agent initializes without errors
- [ ] System prompt includes position and price data
- [ ] Agent calls tools (at least 2-3 tool calls)
- [ ] Position file updates correctly
- [ ] Log file contains complete conversation
- [ ] Session ends with stop signal

### 2.2 Multi-Day Trading Test

Test across multiple trading days:

```bash
# Create multi-day config
cat > configs/test_multiday.json << 'EOF'
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-23"
  },
  "models": [
    {
      "name": "claude-multiday",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-multiday-test",
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
EOF

python main.py configs/test_multiday.json
```

**Verification:**
- [ ] Positions carry over between days
- [ ] Cash balance updates correctly
- [ ] No duplicate trades on same day
- [ ] Logs generated for each day

### 2.3 Tool-Specific Tests

Test each tool individually:

**A. Price Tool Test:**
```bash
# Test in Python shell
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from agent.anthropic_agent.anthropic_tools import get_price_local

# Test valid request
result = get_price_local("AAPL", "2025-10-20")
print("✅ Price tool test:", result)

# Test invalid date
result = get_price_local("AAPL", "2099-12-31")
print("✅ Invalid date test:", result)

# Test invalid symbol
result = get_price_local("INVALID", "2025-10-20")
print("✅ Invalid symbol test:", result)
EOF
```

**B. Search Tool Test:**
```bash
# Test search (requires JINA_API_KEY)
python3 << 'EOF'
import sys
import os
sys.path.insert(0, '.')
from tools.general_tools import write_config_value
write_config_value("TODAY_DATE", "2025-10-21")

from agent.anthropic_agent.anthropic_tools import get_information

result = get_information("Apple stock news")
print("✅ Search tool test:", result[:500])
EOF
```

**C. Trading Tools Test:**
```bash
# Test buy/sell (requires setup)
python3 << 'EOF'
import sys
import os
sys.path.insert(0, '.')
from tools.general_tools import write_config_value

# Set up test environment
write_config_value("TODAY_DATE", "2025-10-20")
write_config_value("SIGNATURE", "test-trade")

from agent.anthropic_agent.anthropic_tools import buy, sell

# This will test the logic but may fail if position file doesn't exist
# That's expected - just checking no import/syntax errors
print("✅ Trading tools imported successfully")
EOF
```

### 2.4 Error Handling Tests

Test how the agent handles errors:

**A. Insufficient Cash Test:**
```bash
# Create config with low initial cash
cat > configs/test_errors.json << 'EOF'
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-20"
  },
  "models": [
    {
      "name": "claude-error-test",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-error-test",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 10,
    "max_retries": 2,
    "base_delay": 1.0,
    "initial_cash": 100.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
EOF

python main.py configs/test_errors.json
```

**Check logs for:**
- [ ] "Insufficient cash" error message
- [ ] Agent handles error gracefully
- [ ] Agent continues making decisions

**B. API Rate Limit Test:**
```bash
# Run multiple times quickly to test retry logic
for i in {1..3}; do
  echo "Run $i"
  python main.py configs/test_anthropic.json
  sleep 2
done
```

---

## Phase 3: Comparison Testing (1-2 hours)

### 3.1 Side-by-Side Comparison

Compare BaseAgent vs AnthropicAgent:

```bash
# Create comparison configs
cat > configs/compare_base.json << 'EOF'
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-21"
  },
  "models": [
    {
      "name": "claude-base",
      "basemodel": "anthropic/claude-3.7-sonnet",
      "signature": "claude-base-compare",
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
EOF

cat > configs/compare_anthropic.json << 'EOF'
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-21"
  },
  "models": [
    {
      "name": "claude-anthropic",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-anthropic-compare",
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
EOF

# Start MCP services for BaseAgent
cd agent_tools
python start_mcp_services.py &
MCP_PID=$!
cd ..
sleep 5

# Run BaseAgent
echo "Running BaseAgent..."
time python main.py configs/compare_base.json

# Run AnthropicAgent
echo "Running AnthropicAgent..."
time python main.py configs/compare_anthropic.json

# Stop MCP services
kill $MCP_PID
```

### 3.2 Performance Metrics

Create a script to compare performance:

```bash
cat > scripts/compare_agents.py << 'EOF'
#!/usr/bin/env python3
import json
import os
from datetime import datetime

def analyze_logs(signature, date):
    """Analyze log file for performance metrics"""
    log_file = f"data/agent_data/{signature}/log/{date}/log.jsonl"

    if not os.path.exists(log_file):
        return None

    metrics = {
        "total_steps": 0,
        "tool_calls": 0,
        "tools_used": set(),
        "errors": 0,
        "start_time": None,
        "end_time": None
    }

    with open(log_file, 'r') as f:
        for line in f:
            entry = json.loads(line)
            timestamp = entry.get("timestamp")
            message = entry.get("message", {})

            if metrics["start_time"] is None:
                metrics["start_time"] = timestamp
            metrics["end_time"] = timestamp

            metrics["total_steps"] += 1

            # Count tool calls
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            metrics["tool_calls"] += 1

    # Calculate duration
    if metrics["start_time"] and metrics["end_time"]:
        start = datetime.fromisoformat(metrics["start_time"])
        end = datetime.fromisoformat(metrics["end_time"])
        metrics["duration_seconds"] = (end - start).total_seconds()

    return metrics

def compare_agents():
    """Compare BaseAgent vs AnthropicAgent"""
    base_metrics = analyze_logs("claude-base-compare", "2025-10-20")
    anthropic_metrics = analyze_logs("claude-anthropic-compare", "2025-10-20")

    print("=" * 60)
    print("AGENT COMPARISON")
    print("=" * 60)

    if base_metrics:
        print("\n📊 BaseAgent (LangChain + MCP):")
        print(f"   Steps: {base_metrics['total_steps']}")
        print(f"   Tool Calls: {base_metrics['tool_calls']}")
        print(f"   Duration: {base_metrics.get('duration_seconds', 'N/A')}s")

    if anthropic_metrics:
        print("\n📊 AnthropicAgent (Native SDK):")
        print(f"   Steps: {anthropic_metrics['total_steps']}")
        print(f"   Tool Calls: {anthropic_metrics['tool_calls']}")
        print(f"   Duration: {anthropic_metrics.get('duration_seconds', 'N/A')}s")

    if base_metrics and anthropic_metrics:
        print("\n📈 Performance Improvement:")
        if base_metrics.get('duration_seconds') and anthropic_metrics.get('duration_seconds'):
            speedup = (base_metrics['duration_seconds'] - anthropic_metrics['duration_seconds']) / base_metrics['duration_seconds'] * 100
            print(f"   Speed: {speedup:.1f}% faster")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    compare_agents()
EOF

chmod +x scripts/compare_agents.py
python scripts/compare_agents.py
```

---

## Phase 4: Integration Testing (1-2 hours)

### 4.1 Full Trading Cycle Test

Run a complete trading cycle with multiple models:

```bash
# Create comprehensive config
cat > configs/test_full_cycle.json << 'EOF'
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-01",
    "end_date": "2025-10-05"
  },
  "models": [
    {
      "name": "claude-3.7-sonnet",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-full-cycle",
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
EOF

python main.py configs/test_full_cycle.json
```

### 4.2 Calculate Performance

Run the performance calculation script:

```bash
# Calculate trading performance
bash calc_perf.sh

# View results
cat data/agent_data/claude-full-cycle/performance.json | jq .
```

### 4.3 Visualize Results

```bash
# Generate visualization
cd docs
python3 -m http.server 8000 &
echo "Open http://localhost:8000 to view results"
```

---

## Phase 5: Production Readiness (2-4 hours)

### 5.1 Configuration Validation

Create a config validator:

```bash
cat > scripts/validate_config.py << 'EOF'
#!/usr/bin/env python3
import json
import sys

def validate_config(config_path):
    """Validate configuration file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        errors = []

        # Check required fields
        if "agent_type" not in config:
            errors.append("Missing 'agent_type'")

        if "models" not in config or not config["models"]:
            errors.append("Missing or empty 'models'")

        if "date_range" not in config:
            errors.append("Missing 'date_range'")

        # Validate agent type
        agent_type = config.get("agent_type")
        if agent_type not in ["BaseAgent", "AnthropicAgent"]:
            errors.append(f"Invalid agent_type: {agent_type}")

        # Validate models
        for i, model in enumerate(config.get("models", [])):
            if "signature" not in model:
                errors.append(f"Model {i}: missing 'signature'")
            if "basemodel" not in model:
                errors.append(f"Model {i}: missing 'basemodel'")

        # Validate date range
        date_range = config.get("date_range", {})
        if "init_date" not in date_range:
            errors.append("Missing 'init_date' in date_range")
        if "end_date" not in date_range:
            errors.append("Missing 'end_date' in date_range")

        if errors:
            print("❌ Configuration validation failed:")
            for error in errors:
                print(f"   - {error}")
            return False
        else:
            print("✅ Configuration is valid")
            return True

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ File not found: {config_path}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_config.py <config_file>")
        sys.exit(1)

    valid = validate_config(sys.argv[1])
    sys.exit(0 if valid else 1)
EOF

chmod +x scripts/validate_config.py

# Test validation
python scripts/validate_config.py configs/anthropic_config.json
```

### 5.2 Error Recovery Test

Test how the system handles crashes:

```bash
# Run agent and kill it mid-execution
python main.py configs/test_anthropic.json &
PID=$!
sleep 5
kill $PID

# Try to resume - should handle gracefully
python main.py configs/test_anthropic.json
```

### 5.3 Load Testing

Test with multiple models in parallel:

```bash
cat > configs/test_parallel.json << 'EOF'
{
  "agent_type": "AnthropicAgent",
  "date_range": {
    "init_date": "2025-10-20",
    "end_date": "2025-10-20"
  },
  "models": [
    {
      "name": "claude-1",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-parallel-1",
      "enabled": true
    },
    {
      "name": "claude-2",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-parallel-2",
      "enabled": true
    },
    {
      "name": "claude-3",
      "basemodel": "claude-3-5-sonnet-20241022",
      "signature": "claude-parallel-3",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 10,
    "max_retries": 3,
    "base_delay": 1.0,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
EOF

python main.py configs/test_parallel.json
```

---

## Phase 6: Development Tasks

### Priority 1: Critical Improvements

#### 6.1 Add Streaming Support

```python
# In anthropic_agent.py, add streaming method:

async def _call_claude_with_streaming(
    self,
    messages: List[Dict[str, Any]],
    system_prompt: str
) -> None:
    """Call Claude API with streaming"""
    with self.client.messages.stream(
        model=self.basemodel,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
        tools=TOOL_DEFINITIONS
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)

        # Get final message
        message = stream.get_final_message()
        return message
```

#### 6.2 Add Prompt Caching

```python
# Modify system prompt to use caching:

response = self.client.messages.create(
    model=self.basemodel,
    max_tokens=4096,
    system=[
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=messages,
    tools=TOOL_DEFINITIONS
)
```

#### 6.3 Add Better Error Messages

```python
# Create custom exceptions:

class TradingError(Exception):
    """Base exception for trading errors"""
    pass

class InsufficientCashError(TradingError):
    """Raised when there's insufficient cash"""
    pass

class InvalidSymbolError(TradingError):
    """Raised when stock symbol is invalid"""
    pass
```

### Priority 2: Feature Enhancements

#### 6.4 Add Resume Capability

```python
# Add to AnthropicAgent:

def can_resume(self, date: str) -> bool:
    """Check if session can be resumed"""
    log_file = self._setup_logging(date)
    return os.path.exists(log_file)

async def resume_trading_session(self, date: str) -> None:
    """Resume interrupted trading session"""
    # Load previous messages from log
    # Continue from last state
    pass
```

#### 6.5 Add Model Comparison Tool

```bash
cat > scripts/compare_models.py << 'EOF'
#!/usr/bin/env python3
"""Compare different Claude model variants"""

# Compare claude-3-5-sonnet vs claude-3-5-haiku
# Track: speed, cost, performance, decision quality
EOF
```

#### 6.6 Add Real-time Monitoring

```python
# Add monitoring endpoint:

from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/status/{signature}")
async def get_agent_status(signature: str):
    """Get real-time agent status"""
    # Return current position, last action, etc.
    pass

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### Priority 3: Optimization

#### 6.7 Reduce API Costs

```python
# Implement request caching:

import hashlib
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_get_price(symbol: str, date: str):
    """Cache price lookups"""
    return get_price_local(symbol, date)
```

#### 6.8 Batch Operations

```python
# Add batch trading:

def batch_execute_trades(trades: List[Dict]) -> List[Dict]:
    """Execute multiple trades efficiently"""
    results = []
    for trade in trades:
        if trade['action'] == 'buy':
            results.append(buy(trade['symbol'], trade['amount']))
        elif trade['action'] == 'sell':
            results.append(sell(trade['symbol'], trade['amount']))
    return results
```

#### 6.9 Add Telemetry

```python
# Track metrics:

import time
from dataclasses import dataclass

@dataclass
class SessionMetrics:
    start_time: float
    end_time: float
    api_calls: int
    tool_calls: int
    tokens_used: int
    cost_usd: float

    def duration(self) -> float:
        return self.end_time - self.start_time
```

---

## Phase 7: Documentation & Testing

### 7.1 Unit Tests

Create unit tests:

```bash
mkdir -p tests
cat > tests/test_anthropic_tools.py << 'EOF'
import unittest
from agent.anthropic_agent.anthropic_tools import buy, sell, get_price_local

class TestAnthropicTools(unittest.TestCase):
    def test_buy_insufficient_cash(self):
        # Test buy with insufficient cash
        pass

    def test_sell_no_position(self):
        # Test sell without position
        pass

    def test_get_price_invalid_date(self):
        # Test invalid date
        result = get_price_local("AAPL", "invalid-date")
        self.assertIn("error", result)

    def test_get_price_valid(self):
        # Test valid price lookup
        result = get_price_local("AAPL", "2025-10-20")
        # Should return price data
        pass

if __name__ == '__main__':
    unittest.main()
EOF

python -m pytest tests/
```

### 7.2 Integration Tests

```bash
cat > tests/test_integration.py << 'EOF'
import unittest
import asyncio
from agent.anthropic_agent.anthropic_agent import AnthropicAgent

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.agent = AnthropicAgent(
            signature="test-agent",
            basemodel="claude-3-5-sonnet-20241022",
            initial_cash=10000.0,
            init_date="2025-10-20"
        )

    def test_agent_initialization(self):
        asyncio.run(self.agent.initialize())
        self.assertIsNotNone(self.agent.client)

    def test_trading_session(self):
        asyncio.run(self.agent.initialize())
        asyncio.run(self.agent.run_trading_session("2025-10-20"))
        # Verify position file exists

if __name__ == '__main__':
    unittest.main()
EOF
```

### 7.3 Performance Benchmarks

```bash
cat > scripts/benchmark.py << 'EOF'
#!/usr/bin/env python3
"""Benchmark agent performance"""
import time
import asyncio
from agent.anthropic_agent.anthropic_agent import AnthropicAgent

async def benchmark():
    agent = AnthropicAgent(
        signature="benchmark",
        basemodel="claude-3-5-sonnet-20241022",
        initial_cash=10000.0,
        init_date="2025-10-20"
    )

    await agent.initialize()

    start = time.time()
    await agent.run_trading_session("2025-10-20")
    duration = time.time() - start

    print(f"Benchmark completed in {duration:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(benchmark())
EOF
```

---

## Quick Reference: Common Commands

```bash
# 1. Quick test
python main.py configs/test_anthropic.json

# 2. Full run with performance calculation
python main.py configs/anthropic_config.json && bash calc_perf.sh

# 3. Compare agents
python scripts/compare_agents.py

# 4. Validate config
python scripts/validate_config.py configs/anthropic_config.json

# 5. View logs
tail -f data/agent_data/*/log/*/log.jsonl

# 6. Check positions
cat data/agent_data/*/position/position.jsonl | jq .

# 7. Monitor in real-time
watch -n 1 'ls -lht data/agent_data/*/log/*/ | head -20'
```

---

## Troubleshooting Guide

### Issue: "Anthropic API key not set"
```bash
# Solution:
export ANTHROPIC_API_KEY=your_key
# or add to .env file
```

### Issue: "No data found for date"
```bash
# Solution: Check data exists
ls -la data/merged.jsonl
# If missing, fetch data:
cd data && python get_daily_price.py && python merge_jsonl.py
```

### Issue: Tool execution fails
```bash
# Solution: Check logs
cat data/agent_data/*/log/*/log.jsonl | jq '.message.content[] | select(.type=="tool_result")'
```

### Issue: Session times out
```bash
# Solution: Increase max_steps in config
# Edit agent_config.max_steps to higher value (e.g., 50)
```

---

## Success Criteria

Your testing is complete when:

- [ ] ✅ Smoke test passes
- [ ] ✅ All 4 tools execute without errors
- [ ] ✅ Multi-day trading works
- [ ] ✅ Position file updates correctly
- [ ] ✅ Logs are readable and complete
- [ ] ✅ Error handling works gracefully
- [ ] ✅ Performance metrics show improvement over BaseAgent
- [ ] ✅ System recovers from interruptions
- [ ] ✅ Documentation is complete

---

## Next Milestone: Production Deployment

Once testing is complete, consider:

1. **Set up CI/CD pipeline**
2. **Add monitoring and alerting**
3. **Configure auto-scaling**
4. **Set up data backup**
5. **Create operational runbook**

Good luck with your testing! 🚀

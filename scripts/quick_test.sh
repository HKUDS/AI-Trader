#!/bin/bash
# Quick test script for AnthropicAgent

set -e  # Exit on error

echo "🧪 Quick Test Script for AnthropicAgent"
echo "========================================"

# Check if ANTHROPIC_API_KEY is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ANTHROPIC_API_KEY not set!"
    echo "Please set it in .env file or export it:"
    echo "  export ANTHROPIC_API_KEY=your_key_here"
    exit 1
fi

echo "✅ API key found"

# Create test config if it doesn't exist
if [ ! -f "configs/test_anthropic.json" ]; then
    echo "📝 Creating test configuration..."
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
      "signature": "claude-quick-test",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 10,
    "max_retries": 2,
    "base_delay": 1.0,
    "initial_cash": 10000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
EOF
fi

# Clean previous test data
echo "🧹 Cleaning previous test data..."
rm -rf data/agent_data/claude-quick-test

# Run test
echo "🚀 Running AnthropicAgent test..."
echo ""
python main.py configs/test_anthropic.json

# Check results
echo ""
echo "📊 Test Results:"
echo "================"

# Check if position file was created
if [ -f "data/agent_data/claude-quick-test/position/position.jsonl" ]; then
    echo "✅ Position file created"
    echo "   Last position:"
    tail -1 data/agent_data/claude-quick-test/position/position.jsonl | python3 -m json.tool
else
    echo "❌ Position file not found"
fi

# Check if log file was created
if [ -f "data/agent_data/claude-quick-test/log/2025-10-20/log.jsonl" ]; then
    echo "✅ Log file created"
    echo "   Total log entries: $(wc -l < data/agent_data/claude-quick-test/log/2025-10-20/log.jsonl)"
else
    echo "❌ Log file not found"
fi

echo ""
echo "🎉 Test complete!"
echo ""
echo "Next steps:"
echo "  1. View logs: cat data/agent_data/claude-quick-test/log/2025-10-20/log.jsonl | jq ."
echo "  2. View positions: cat data/agent_data/claude-quick-test/position/position.jsonl | jq ."
echo "  3. Run full test: python main.py configs/anthropic_config.json"

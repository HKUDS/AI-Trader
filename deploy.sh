#!/bin/bash
set -e

echo "🚀 AI-Trader Deployment Script"
echo "================================"

# Check Python version
echo "✓ Python: $(python3.11 --version)"

# Install dependencies
echo "📦 Installing dependencies..."
python3.11 -m pip install -q -r requirements.txt

# Setup environment
if [ ! -f .env ]; then
    echo "⚠️  .env not found, copying from .env.example"
    cp .env.example .env
fi

# Create necessary directories
mkdir -p logs data/agent_data data/agent_data_astock data/agent_data_crypto

# Start MCP Services
echo "🛠️  Starting MCP Services..."
python3.11 agent_tools/start_mcp_services.py &
MCP_PID=$!
sleep 3

# Check services
echo "🔍 Checking services..."
SERVICES=$(ps aux | grep "python3.11.*tool_" | grep -v grep | wc -l)
echo "   Running services: $SERVICES/5"

if [ $SERVICES -eq 5 ]; then
    echo "✅ All MCP services started successfully!"
    echo ""
    echo "📊 Service Ports:"
    echo "   - Math:   8000"
    echo "   - Search: 8001"
    echo "   - Trade:  8002"
    echo "   - Price:  8003"
    echo "   - Crypto: 8005"
    echo ""
    echo "🎯 Ready to trade! Run:"
    echo "   python3.11 main.py configs/default_config.json"
else
    echo "❌ Some services failed to start"
    exit 1
fi

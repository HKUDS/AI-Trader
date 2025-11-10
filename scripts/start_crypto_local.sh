#!/bin/bash
# Local Development Startup Script for Crypto Trading
# Usage: bash scripts/start_crypto_local.sh

set -e

echo "=========================================="
echo "🏠 AI-Trader Crypto - LOCAL DEVELOPMENT"
echo "=========================================="
echo ""

echo "🐍 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Python version: $python_version"
echo ""

if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

echo "🔌 Activating virtual environment..."
source venv/bin/activate
echo ""

echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q ccxt>=4.0.0 python-binance>=1.0.19 anthropic>=0.18.0
echo "✅ Dependencies installed"
echo ""

if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found!"
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your API keys!"
    read -p "Press Enter to continue..."
fi

export $(cat .env | grep -v '^#' | xargs)

echo "🔑 Checking API keys..."
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OPENAI_API_KEY not set in .env!"
    exit 1
fi
echo "✅ API keys configured"
echo ""

echo "📁 Creating data directories..."
mkdir -p data/crypto
mkdir -p data/agent_data_crypto
echo "✅ Directories created"
echo ""

echo "🤖 Starting Crypto Trading Agent..."
echo "   Config: configs/crypto_config_local.json"
echo "   Mode: TESTNET (No real money)"
echo ""

python main.py configs/crypto_config_local.json

echo "✅ Trading session completed"
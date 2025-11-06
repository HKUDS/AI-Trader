#!/bin/bash
# GitHub Codespaces Startup Script
# Auto-detects Codespaces environment

set -e

echo "=========================================="
echo "☁️  AI-Trader Crypto - GITHUB CODESPACES"
echo "=========================================="
echo ""

if [ "$CODESPACES" != "true" ]; then
    echo "⚠️  Warning: Not running in GitHub Codespaces!"
    read -p "Continue anyway? (y/N): " continue_choice
    if [[ ! "$continue_choice" =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

echo "✅ GitHub Codespaces detected"
echo "   Codespace name: $CODESPACE_NAME"
echo "   User: $GITHUB_USER"
echo ""

echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q ccxt>=4.0.0 python-binance>=1.0.19 anthropic>=0.18.0
echo "✅ Dependencies installed"
echo ""

echo "🔑 Checking GitHub secrets..."
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not found in secrets"
    echo "   Add it to repository secrets or Codespaces secrets"
fi

if [ -z "$BYBIT_API_KEY" ]; then
    echo "⚠️  BYBIT_API_KEY not found - testnet mode only"
fi
echo ""

echo "📁 Creating directories..."
mkdir -p /workspace/data/crypto
mkdir -p /workspace/data/agent_data_crypto
echo "✅ Directories created"
echo ""

echo "🤖 Starting Crypto Trading Agent (Codespaces mode)..."
echo "   Config: configs/crypto_config_codespaces.json"
echo "   Mode: LIVE (with testnet option in config)"
echo ""
echo "⏰ Codespaces hours tracking:"
echo "   Free tier: 120 hours/month"
echo "   Pro: 180 hours/month"
echo ""

python main.py configs/crypto_config_codespaces.json

echo "✅ Stopped"
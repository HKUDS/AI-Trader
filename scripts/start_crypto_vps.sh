#!/bin/bash
# VPS Production Startup Script
# For 24/7 live crypto trading

set -e

echo "=========================================="
echo "🖥️  AI-Trader Crypto - VPS PRODUCTION"
echo "=========================================="
echo ""

if [ "$EUID" -eq 0 ]; then 
    echo "⚠️  Running as root. Consider using a dedicated user."
fi

echo "🌐 Detecting VPS environment..."
python3 -c "from tools.environment_detector import print_environment_info; print_environment_info()" 2>/dev/null || echo "Environment detector not found"
echo ""

echo "💻 System Resources:"
echo "   CPU cores: $(nproc 2>/dev/null || echo 'N/A')"
echo "   RAM: $(free -h 2>/dev/null | awk '/^Mem:/ {print $2}' || echo 'N/A')"
echo "   Disk space: $(df -h / 2>/dev/null | awk 'NR==2 {print $4}' || echo 'N/A')"
echo ""

APP_DIR="/var/ai-trader"
if [ ! -d "$APP_DIR" ]; then
    echo "📁 Creating application directory..."
    sudo mkdir -p "$APP_DIR"
    sudo chown -R $USER:$USER "$APP_DIR"
fi

cd "$APP_DIR"

if [ ! -d "AI-Trader" ]; then
    echo "📦 Cloning repository..."
    git clone https://github.com/feherg78/AI-Trader.git
    cd AI-Trader
else
    echo "🔄 Updating repository..."
    cd AI-Trader
    git pull
fi

if [ ! -d "venv" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q ccxt>=4.0.0 python-binance>=1.0.19 anthropic>=0.18.0
echo "✅ Dependencies installed"
echo ""

if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "   Create .env file with your API keys"
    exit 1
fi

export $(cat .env | grep -v '^#' | xargs)

echo "🔑 Verifying API keys..."
critical_keys=("OPENAI_API_KEY" "BYBIT_API_KEY" "BYBIT_API_SECRET")
missing_keys=()

for key in "${critical_keys[@]}"; do
    if [ -z "${!key}" ]; then
        missing_keys+=("$key")
    fi
done

if [ ${#missing_keys[@]} -gt 0 ]; then
    echo "❌ Missing API keys: ${missing_keys[*]}"
    exit 1
fi
echo "✅ All API keys present"
echo ""

echo "📁 Creating data directories..."
mkdir -p "$APP_DIR/data/crypto"
mkdir -p "$APP_DIR/data/agent_data_crypto"
mkdir -p "$APP_DIR/logs"
echo "✅ Directories ready"
echo ""

echo "⚠️  =========================================="
echo "⚠️  WARNING: LIVE TRADING MODE"
echo "⚠️  =========================================="
echo "⚠️  This will trade with REAL MONEY"
echo "⚠️  Initial capital: \$10,000 USDT"
echo "⚠️  =========================================="
echo ""
read -p "Continue with LIVE trading? (yes/NO): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Aborted by user"
    exit 0
fi

echo ""
echo "🤖 Starting Crypto Trading Agent (VPS Production)..."
echo "   Config: configs/crypto_config_vps.json"
echo "   Mode: LIVE 24/7"
echo ""

nohup python main.py configs/crypto_config_vps.json >> "$APP_DIR/logs/trading.log" 2>&1 &
TRADING_PID=$!
echo $TRADING_PID > "$APP_DIR/trading.pid"

echo "✅ Trading agent started (PID: $TRADING_PID)"
echo ""
echo "📋 Management commands:"
echo "   View logs: tail -f $APP_DIR/logs/trading.log"
echo "   Stop trading: kill \$(cat $APP_DIR/trading.pid)"
echo ""
echo "=========================================="
echo "✅ VPS Production mode ACTIVE"
echo "=========================================="
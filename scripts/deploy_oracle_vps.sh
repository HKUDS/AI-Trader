#!/bin/bash
# Oracle Cloud Free Tier VPS Deployment Script
# Automated setup for Ubuntu 22.04 LTS

set -e

echo "=========================================="
echo "🏗️  Oracle Cloud VPS - Initial Setup"
echo "=========================================="
echo ""

echo "📋 System Information:"
echo "   OS: $(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')"
echo "   Kernel: $(uname -r)"
echo "   Architecture: $(uname -m)"
echo ""

echo "📥 Updating system packages..."
sudo apt update
sudo apt upgrade -y
echo "✅ System updated"
echo ""

echo "🐍 Installing Python 3.10..."
sudo apt install -y python3.10 python3.10-venv python3-pip
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
echo "✅ Python installed: $(python3 --version)"
echo ""

echo "📦 Installing Git..."
sudo apt install -y git
echo "✅ Git installed: $(git --version)"
echo ""

echo "📥 Installing system dependencies..."
sudo apt install -y build-essential libssl-dev libffi-dev curl wget htop
echo "✅ Dependencies installed"
echo ""

APP_USER="aitrader"
if ! id "$APP_USER" &>/dev/null; then
    echo "👤 Creating application user: $APP_USER"
    sudo useradd -m -s /bin/bash "$APP_USER"
    echo "✅ User created"
else
    echo "✅ User $APP_USER already exists"
fi
echo ""

echo "🔥 Configuring firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 8000:8003/tcp
sudo ufw --force enable
echo "✅ Firewall configured"
echo ""

APP_DIR="/var/ai-trader"
echo "📁 Creating application directory: $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
echo "✅ Directory created"
echo ""

echo "🔄 Switching to $APP_USER user..."
sudo -u "$APP_USER" bash << 'EOF'

cd /var/ai-trader

echo "📦 Cloning AI-Trader repository..."
git clone https://github.com/feherg78/AI-Trader.git
cd AI-Trader

echo "🐍 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install ccxt>=4.0.0 python-binance>=1.0.19 anthropic>=0.18.0

echo "✅ Python environment ready"

if [ ! -f ".env" ]; then
    echo "📝 Creating .env template..."
    cat > .env << 'ENVFILE'
# AI Model APIs
OPENAI_API_BASE=https://models.inference.ai.azure.com
OPENAI_API_KEY=ghp_YOUR_GITHUB_TOKEN_HERE
ANTHROPIC_API_KEY=sk-ant-YOUR_ANTHROPIC_KEY_HERE

# Crypto Exchange APIs (ByBit)
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
BYBIT_TESTNET=false

# Binance (optional)
BINANCE_API_KEY=YOUR_BINANCE_API_KEY
BINANCE_API_SECRET=YOUR_BINANCE_API_SECRET

# Service Ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# Agent Config
AGENT_MAX_STEP=50
RUNTIME_ENV_PATH=/var/ai-trader/runtime_env.json

# Environment
RUNTIME_ENV=vps
TESTNET_MODE=false
ENVFILE
    echo "✅ .env template created"
fi

EOF

echo ""
echo "=========================================="
echo "✅ Oracle Cloud VPS Setup Complete!"
echo "=========================================="
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Edit API keys:"
echo "   sudo -u $APP_USER nano $APP_DIR/AI-Trader/.env"
echo ""
echo "2. Get API keys:"
echo "   - GitHub Token: https://github.com/settings/tokens"
echo "   - ByBit API: https://www.bybit.com/app/user/api-management"
echo ""
echo "3. Start trading:"
echo "   sudo -u $APP_USER bash $APP_DIR/AI-Trader/scripts/start_crypto_vps.sh"
echo ""
echo "=========================================="
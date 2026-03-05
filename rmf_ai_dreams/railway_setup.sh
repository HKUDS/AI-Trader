#!/bin/bash

# 🚀 Railway.app Auto Setup Script for RMF AI Dreams
# Run this after connecting to Railway

echo "🔧 Setting up RMF AI Dreams on Railway..."

# Check if railway CLI is installed
if ! command -v railway &> /dev/null
then
    echo "📦 Installing Railway CLI..."
    npm i -g @railway/cli || curl -fsSL https://railway.app/install.sh | sh
fi

# Login to Railway
echo "🔐 Logging in to Railway..."
railway login

# Create new project or link existing
echo "🆕 Creating/Linking Railway project..."
railway init

# Set environment variables
echo "🔑 Setting environment variables..."
railway variables set OWNER_CODE=REEM_RMF_2026
railway variables set STREAMLIT_SERVER_PORT=8501
railway variables set STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Optional: Set API keys (uncomment and add your keys)
# railway variables set OPENAI_API_KEY=your_key_here
# railway variables set ANTHROPIC_API_KEY=your_key_here
# railway variables set GOOGLE_API_KEY=your_key_here
# railway variables set MISTRAL_API_KEY=your_key_here

# Deploy
echo "🚀 Deploying to Railway..."
railway up

echo "✅ Deployment complete!"
echo "🌐 Check your app at: https://railway.app"
echo ""
echo "📝 Next steps:"
echo "   1. Go to Railway dashboard"
echo "   2. Add your API keys in Settings → Variables"
echo "   3. Your app will auto-restart with new keys"
echo ""
echo "🎉 RMF AI Dreams is now LIVE 24/7!"

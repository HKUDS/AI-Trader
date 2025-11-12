#!/bin/bash
# Quick deployment script for AI-Trader authentication system

set -e

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║        AI-TRADER AUTHENTICATION SYSTEM - QUICK DEPLOY                ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed!"
    exit 1
fi

echo "🚀 Starting deployment..."
echo ""

# Run the Python deployment script
python3 deploy_auth_system.py "$@"

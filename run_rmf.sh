#!/bin/bash
# RMF AI Dreams - Launch Script

echo "🖤 Starting RMF AI DREAMS 💀🔥"
echo "================================"
echo ""

# Check if dependencies are installed
if ! command -v streamlit &> /dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements_rmf.txt -q
fi

# Launch the app
echo "🚀 Launching RMF AI Dreams..."
echo "📍 App will be available at: http://localhost:8501"
echo ""

streamlit run rmf_ai_app.py --server.port 8501 --server.headless true

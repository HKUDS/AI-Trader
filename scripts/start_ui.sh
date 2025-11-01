#!/bin/bash

# Start AI-Trader Web UI

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

echo "🌐 Starting Web UI server..."
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd docs
python3 -m http.server 8888


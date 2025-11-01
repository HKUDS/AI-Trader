#!/bin/bash

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

echo "🤖 Now starting the main trading agent..."
# python main.py configs/day_config.json #run daily config
python main.py configs/test_real_hour_config.json #run hour config

echo "✅ AI-Trader stopped"

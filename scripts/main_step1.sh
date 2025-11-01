#!/bin/bash

# prepare data

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

cd data
# python get_daily_price.py #run daily price data
python get_interdaily_price.py #run interdaily price data
python merge_jsonl.py
cd ..

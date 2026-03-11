#!/bin/bash

# A股数据准备

# 获取项目根目录（scripts/ 的父目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

cd data/A_stock

# for alphavantage
python get_daily_price_alphavantage.py
python merge_jsonl_alphavantage.py
# # for tushare
# python get_daily_price_tushare.py
# python merge_jsonl_tushare.py

cd ..

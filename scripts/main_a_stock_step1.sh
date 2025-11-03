#!/bin/bash

# A股数据准备

# 获取项目根目录（scripts/ 的父目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

cd data/A_stock

python get_daily_price_a_stock.py  # 运行A股价格数据获取（日度）
python merge_a_stock_jsonl.py  # 合并A股数据文件
cd ..

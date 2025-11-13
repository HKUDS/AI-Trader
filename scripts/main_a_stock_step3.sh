#!/bin/bash

# 获取项目根目录（scripts/ 的父目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

echo "🤖 正在启动主交易智能体（A股模式）..."

python main.py configs/astock_config.json  # 运行A股配置

echo "✅ AI-Trader 已停止"

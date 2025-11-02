#!/bin/bash
# 启动美股交易定时调度器

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 设置 Python 路径
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# 设置 Python 解释器路径（支持通过环境变量配置）
# 如果设置了 PYTHON_BIN，使用指定的 Python 路径
# 否则尝试常见的路径
if [ -n "$PYTHON_BIN" ]; then
    PYTHON="$PYTHON_BIN"
elif [ -f "/home/ec2-user/py310/bin/python" ]; then
    # Miniconda 环境
    PYTHON="/home/ec2-user/py310/bin/python"
elif [ -d "venv" ] && [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
elif [ -d ".venv" ] && [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    # 使用系统 Python
    PYTHON="python3"
fi

# 验证 Python 是否存在
if [ ! -f "$PYTHON" ] && ! command -v "$PYTHON" &> /dev/null; then
    echo "❌ 错误: 找不到 Python 解释器: $PYTHON"
    echo "💡 提示: 可以通过设置环境变量 PYTHON_BIN 指定 Python 路径"
    exit 1
fi

# 显示使用的 Python 版本
echo "🐍 使用 Python: $PYTHON"
echo "📌 Python 版本:"
$PYTHON --version

# 运行调度器
echo "🚀 启动美股交易定时调度器..."
"$PYTHON" "$SCRIPT_DIR/trading_scheduler.py"


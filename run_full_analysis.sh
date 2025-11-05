#!/bin/bash
# AI交易回测与基准对比 - 一键运行脚本

set -e

echo "======================================================================"
echo "🚀 AI交易回测系统 - 完整分析流程"
echo "======================================================================"

# 配置
CONFIG_FILE="${1:-configs/simple_config.json}"
POSITION_FILE="./data/agent_data/GLM-4.5-simple/position/position.jsonl"

echo ""
echo "📋 步骤 1/4: 检查依赖..."
python3 -c "import pandas, matplotlib" 2>/dev/null || {
    echo "⚠️  缺少依赖,正在安装..."
    pip install pandas matplotlib -q
    echo "✅ 依赖安装完成"
}

echo ""
echo "📋 步骤 2/4: 运行回测..."
if [ -f "$POSITION_FILE" ]; then
    echo "ℹ️  发现已有回测结果: $POSITION_FILE"
    read -p "是否重新运行回测? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python3 main_simple.py "$CONFIG_FILE"
    else
        echo "⏩ 跳过回测,使用现有结果"
    fi
else
    python3 main_simple.py "$CONFIG_FILE"
fi

echo ""
echo "📋 步骤 3/4: 基准对比分析..."
python3 analyze_with_benchmark.py "$POSITION_FILE"

echo ""
echo "📋 步骤 4/4: 生成可视化图表..."
CSV_FILE="${POSITION_FILE/position.jsonl/comparison.csv}"
python3 plot_comparison.py "$CSV_FILE"

echo ""
echo "======================================================================"
echo "✅ 分析完成!"
echo "======================================================================"
echo ""
echo "📁 生成的文件:"
echo "  1. 回测记录: $POSITION_FILE"
echo "  2. 对比数据: $CSV_FILE"
echo "  3. 可视化图: ${CSV_FILE/.csv/_chart.png}"
echo ""
echo "💡 使用方法:"
echo "  - 查看CSV: cat $CSV_FILE"
echo "  - 查看图表: open ${CSV_FILE/.csv/_chart.png}"
echo ""
echo "======================================================================"

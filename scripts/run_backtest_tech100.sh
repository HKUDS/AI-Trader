#!/bin/bash
# AI-Trader 美股科技100回测脚本
# 用于回测2025年上半年（1月-6月）的交易表现

set -e  # 遇到错误立即退出

echo "🚀 ===== AI-Trader 美股科技100回测系统 ====="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}📁 项目根目录: ${PROJECT_ROOT}${NC}"
echo ""

# ==================== 步骤 1: 数据准备 ====================
echo -e "${YELLOW}📊 步骤 1/3: 准备数据...${NC}"
cd "${PROJECT_ROOT}/data"

# 检查是否存在股票数据文件
if ls daily_prices_*.json 1> /dev/null 2>&1; then
    echo -e "${GREEN}✅ 发现股票数据文件${NC}"
    
    # 合并数据
    echo "🔄 正在合并数据为 merged.jsonl 格式..."
    python3 merge_tech100_data.py
    
    if [ -f "merged.jsonl" ]; then
        echo -e "${GREEN}✅ 数据合并成功！${NC}"
        # 显示统计信息
        line_count=$(wc -l < merged.jsonl)
        echo "   📈 共 ${line_count} 支股票数据"
    else
        echo -e "${RED}❌ 数据合并失败${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ 未找到 daily_prices_*.json 文件${NC}"
    echo "   请确保已将股票数据放置在 ${PROJECT_ROOT}/data/ 目录下"
    exit 1
fi

echo ""

# ==================== 步骤 2: 启动 MCP 服务 ====================
echo -e "${YELLOW}🛠️ 步骤 2/3: 启动 MCP 工具服务...${NC}"
cd "${PROJECT_ROOT}/agent_tools"

# 检查服务是否已运行
if pgrep -f "start_mcp_services.py" > /dev/null; then
    echo -e "${YELLOW}⚠️  MCP 服务已在运行中${NC}"
    echo "   如需重启，请先执行: pkill -f start_mcp_services.py"
else
    echo "🚀 启动 MCP 服务..."
    nohup python3 start_mcp_services.py > /tmp/mcp_services.log 2>&1 &
    MCP_PID=$!
    echo "   PID: ${MCP_PID}"
    
    # 等待服务启动
    echo "⏳ 等待服务初始化..."
    sleep 5
    
    # 检查服务是否成功启动
    if ps -p $MCP_PID > /dev/null; then
        echo -e "${GREEN}✅ MCP 服务启动成功${NC}"
        echo "   日志文件: /tmp/mcp_services.log"
    else
        echo -e "${RED}❌ MCP 服务启动失败${NC}"
        echo "   查看日志: cat /tmp/mcp_services.log"
        exit 1
    fi
fi

echo ""

# ==================== 步骤 3: 运行回测 ====================
echo -e "${YELLOW}🎯 步骤 3/3: 运行回测...${NC}"
cd "${PROJECT_ROOT}"

echo "📅 回测时间段: 2025-01-01 至 2025-06-30"
echo "💰 初始资金: $10,000"
echo "📊 交易标的: 100支美股科技股"
echo ""

# 检查配置文件
CONFIG_FILE="${PROJECT_ROOT}/configs/backtest_tech100_config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ 配置文件不存在: ${CONFIG_FILE}${NC}"
    exit 1
fi

# 显示将要运行的模型
echo -e "${BLUE}🤖 将要运行的 AI 模型:${NC}"
python3 -c "
import json
with open('${CONFIG_FILE}', 'r') as f:
    config = json.load(f)
    enabled_models = [m for m in config['models'] if m.get('enabled', True)]
    for i, model in enumerate(enabled_models, 1):
        print(f'   {i}. {model[\"name\"]} (signature: {model[\"signature\"]})')
"
echo ""

echo "🚀 开始回测..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 运行主程序
python3 main.py "${CONFIG_FILE}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ 回测完成！${NC}"
echo ""

# ==================== 结果展示 ====================
echo -e "${BLUE}📊 回测结果位置:${NC}"
echo "   - 持仓记录: ${PROJECT_ROOT}/data/agent_data/{model_signature}/position/position.jsonl"
echo "   - 交易日志: ${PROJECT_ROOT}/data/agent_data/{model_signature}/log/"
echo ""

# 显示生成的结果目录
if [ -d "${PROJECT_ROOT}/data/agent_data" ]; then
    echo -e "${BLUE}📁 生成的模型数据目录:${NC}"
    ls -d ${PROJECT_ROOT}/data/agent_data/*/ 2>/dev/null | while read dir; do
        model_name=$(basename "$dir")
        echo "   - ${model_name}"
        
        # 显示持仓统计
        position_file="${dir}position/position.jsonl"
        if [ -f "$position_file" ]; then
            last_line=$(tail -n 1 "$position_file")
            cash=$(echo "$last_line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('positions', {}).get('CASH', 0))")
            date=$(echo "$last_line" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('date', 'N/A'))")
            echo "     最后日期: ${date}, 现金余额: \$${cash}"
        fi
    done
fi

echo ""
echo -e "${YELLOW}💡 提示:${NC}"
echo "   - 查看详细日志: cat data/agent_data/{model_signature}/log/{date}/log.jsonl"
echo "   - 分析性能指标: python calculate_performance.py"
echo "   - 可视化结果: 访问 Web 界面 (bash scripts/start_ui.sh)"
echo ""

echo -e "${GREEN}🎉 回测流程全部完成！${NC}"

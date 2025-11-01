#!/bin/bash
# 修复项目目录权限的脚本
# 使用方法: bash scripts/fix_permissions.sh [username]
# 如果不指定用户名，默认使用 ec2-user

set -e

# 获取用户名，默认为 ec2-user
USERNAME="${1:-ec2-user}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "🔧 修复项目目录权限..."
echo "项目路径: $PROJECT_ROOT"
echo "目标用户: $USERNAME"
echo ""

# 检查用户是否存在
if ! id "$USERNAME" &>/dev/null; then
    echo "❌ 用户 $USERNAME 不存在！"
    exit 1
fi

# 获取用户组
USERGROUP=$(id -gn "$USERNAME")
echo "用户组: $USERGROUP"
echo ""

# 修复项目根目录权限
echo "📁 修复项目根目录权限..."
sudo chown -R "$USERNAME:$USERGROUP" "$PROJECT_ROOT"

# 确保 data 目录存在且有写权限
echo "📁 创建并修复 data 目录..."
sudo -u "$USERNAME" mkdir -p "$PROJECT_ROOT/data"
sudo -u "$USERNAME" mkdir -p "$PROJECT_ROOT/data/agent_data"
sudo -u "$USERNAME" mkdir -p "$PROJECT_ROOT/data/trading_calendar"
sudo chown -R "$USERNAME:$USERGROUP" "$PROJECT_ROOT/data"
sudo chmod -R 755 "$PROJECT_ROOT/data"

# 确保日志目录可写
sudo chmod -R 775 "$PROJECT_ROOT/data"

# 确保配置文件可读
if [ -f "$PROJECT_ROOT/.env" ]; then
    sudo chown "$USERNAME:$USERGROUP" "$PROJECT_ROOT/.env"
    sudo chmod 600 "$PROJECT_ROOT/.env"
    echo "✅ 已修复 .env 文件权限"
fi

if [ -f "$PROJECT_ROOT/.env_example" ]; then
    sudo chown "$USERNAME:$USERGROUP" "$PROJECT_ROOT/.env_example"
    sudo chmod 644 "$PROJECT_ROOT/.env_example"
fi

echo ""
echo "✅ 权限修复完成！"
echo ""
echo "📋 检查关键目录权限："
ls -ld "$PROJECT_ROOT" | awk '{print "项目根目录: " $1 " " $3 ":" $4 " " $9}'
ls -ld "$PROJECT_ROOT/data" | awk '{print "data目录: " $1 " " $3 ":" $4 " " $9}'
ls -ld "$PROJECT_ROOT/data/agent_data" 2>/dev/null | awk '{print "agent_data目录: " $1 " " $3 ":" $4 " " $9}' || echo "agent_data目录: 不存在（程序会自动创建）"


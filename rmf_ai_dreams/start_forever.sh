#!/bin/bash
set -e

echo "🔥 RMF AI Dreams - Setup Forever"
echo "================================="

# ألوان
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# المسار الحالي
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${YELLOW}1. فحص Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker غير مثبت!${NC}"
    echo "تثبيت Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}Docker Compose غير مثبت!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker جاهز${NC}"

echo -e "${YELLOW}2. بناء وتشغيل النظام...${NC}"
docker compose up --build -d

echo -e "${GREEN}✓ النظام يعمل${NC}"

echo -e "${YELLOW}3. إعداد Systemd Service (اختياري)...${NC}"
read -p "تريد تفعيل التشغيل التلقائي عند إعادة تشغيل السيرفر؟ (y/n): " ENABLE_SYSTEMD

if [ "$ENABLE_SYSTEMD" = "y" ]; then
    if [ -f "rmf-ai-dreams.service" ]; then
        sudo cp rmf-ai-dreams.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable rmf-ai-dreams.service
        sudo systemctl start rmf-ai-dreams.service
        echo -e "${GREEN}✓ Systemd service مفعّل${NC}"
    else
        echo -e "${RED}ملف rmf-ai-dreams.service غير موجود${NC}"
    fi
fi

echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}✅ النظام شغال دلوقتي!${NC}"
echo ""
echo "الوصول:"
echo "  • Local: http://localhost:8501"
echo "  • Network: http://$(hostname -I | awk '{print $1}'):8501"
echo ""
echo "الأوامر:"
echo "  • إيقاف: docker compose down"
echo "  • إعادة تشغيل: docker compose restart"
echo "  • اللوجز: docker compose logs -f"
echo "  • الحالة: docker compose ps"
echo ""
echo -e "${YELLOW}للنشر على Railway أو Render، شوفي DEPLOYMENT_GUIDE.md${NC}"
echo -e "${GREEN}=================================${NC}"

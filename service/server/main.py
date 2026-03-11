"""
AI-Trader Backend Server

项目结构：
- config.py   : 配置和环境变量
- database.py : 数据库初始化和连接
- utils.py    : 通用工具函数
- tasks.py    : 后台任务
- services.py : 业务逻辑服务
- routes.py   : API路由定义
- main.py     : 应用入口
"""

import secrets
import logging
import os
from logging.handlers import RotatingFileHandler

# Setup logging
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(
            os.path.join(LOG_DIR, "server.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

from database import init_database, get_db_connection
from routes import create_app
from tasks import update_position_prices, record_profit_history, _update_trending_cache

# Initialize database
init_database()

# Create app
app = create_app()


# ==================== Startup ====================

@app.on_event("startup")
async def startup_event():
    """Startup event - schedule background tasks."""
    import asyncio
    # Initialize trending cache
    logger.info("Initializing trending cache...")
    _update_trending_cache()
    # Start background task for updating position prices
    logger.info("Starting position price update background task...")
    asyncio.create_task(update_position_prices())
    # Start background task for recording profit history
    logger.info("Starting profit history recording task...")
    asyncio.create_task(record_profit_history())
    logger.info("All background tasks started")


# ==================== Run ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

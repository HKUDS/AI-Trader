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

from database import init_database, get_database_status
from routes import create_app
from tasks import (
    update_position_prices,
    record_profit_history,
    settle_polymarket_positions,
    refresh_etf_flow_snapshots_loop,
    refresh_macro_signal_snapshots_loop,
    refresh_market_news_snapshots_loop,
    refresh_stock_analysis_snapshots_loop,
    _update_trending_cache,
)

# Initialize database
init_database()

# Create app
app = create_app()


# ==================== Startup ====================

@app.on_event("startup")
async def startup_event():
    """Startup event - schedule background tasks."""
    import asyncio
    db_status = get_database_status()
    logger.info(
        "Database ready: backend=%s details=%s",
        db_status.get("backend"),
        {key: value for key, value in db_status.items() if key != "backend"},
    )
    # Initialize trending cache
    logger.info("Initializing trending cache...")
    _update_trending_cache()
    # Start background task for updating position prices
    logger.info("Starting position price update background task...")
    asyncio.create_task(update_position_prices())
    # Start background task for recording profit history
    logger.info("Starting profit history recording task...")
    asyncio.create_task(record_profit_history())
    # Start background task for Polymarket settlement
    logger.info("Starting Polymarket settlement task...")
    asyncio.create_task(settle_polymarket_positions())
    # Start background task for market-news snapshots
    logger.info("Starting market news snapshot task...")
    asyncio.create_task(refresh_market_news_snapshots_loop())
    # Start background task for macro signal snapshots
    logger.info("Starting macro signal snapshot task...")
    asyncio.create_task(refresh_macro_signal_snapshots_loop())
    # Start background task for ETF flow snapshots
    logger.info("Starting ETF flow snapshot task...")
    asyncio.create_task(refresh_etf_flow_snapshots_loop())
    # Start background task for stock analysis snapshots
    logger.info("Starting stock analysis snapshot task...")
    asyncio.create_task(refresh_stock_analysis_snapshots_loop())
    logger.info("All background tasks started")


# ==================== Run ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

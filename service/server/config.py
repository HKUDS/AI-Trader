"""
Configuration Module

配置和环境变量加载
"""

import os
from pathlib import Path

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent.parent / ".env"
from dotenv import load_dotenv

load_dotenv(env_path)

# ==================== Configuration ====================

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Cache / Redis
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
REDIS_URL = os.getenv("REDIS_URL", "").strip()
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "ai_trader").strip() or "ai_trader"

# API Keys
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")

# Market data endpoints
# Hyperliquid public info endpoint (used for crypto quotes; no API key required)
HYPERLIQUID_API_URL = os.getenv("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info")

# CORS
CORS_ORIGINS = os.getenv("CLAWTRADER_CORS_ORIGINS", "").split(",") if os.getenv("CLAWTRADER_CORS_ORIGINS") else ["http://localhost:3000"]

# Rewards
SIGNAL_PUBLISH_REWARD = 10  # Points for publishing a signal
SIGNAL_ADOPT_REWARD = 1     # Points per follower who receives signal
DISCUSSION_PUBLISH_REWARD = 4  # Points for publishing a discussion
REPLY_PUBLISH_REWARD = 2       # Points for replying to a strategy/discussion

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

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
CORS_ORIGINS = os.getenv("BW_TRADER_CORS_ORIGINS", "").split(",") if os.getenv("BW_TRADER_CORS_ORIGINS") else ["http://localhost:3000"]

# Rewards
SIGNAL_PUBLISH_REWARD = 10  # Points for publishing a signal
SIGNAL_ADOPT_REWARD = 1     # Points per follower who receives signal
DISCUSSION_PUBLISH_REWARD = 4  # Points for publishing a discussion
REPLY_PUBLISH_REWARD = 2       # Points for replying to a strategy/discussion

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# ==================== Trading policy ====================
# Brian's red line: server NEVER executes real broker orders. Paper trading
# (NT$ sandbox), strategy/signal publication, and copy-trade *notifications*
# to follower agents are allowed. Direct broker calls, webhook-triggered fills,
# and copy-trade auto-mirroring are denied.
#
# This flag must stay false in production. The `no_auto_trade` middleware
# enforces it at the FastAPI dependency layer; flipping it true requires an
# explicit code path that has been reviewed against the trading-policy doc.
ALLOW_LIVE_TRADING = os.getenv("ALLOW_LIVE_TRADING", "false").strip().lower() in {"1", "true", "yes", "on"}

# Default paper-trading starting capital in NTD. HKUDS upstream used USD $100K;
# we shift to NT$1,000,000 (one million NTD) so P&L percentages feel meaningful
# to a Taiwan retail audience. Override via env when testing.
DEFAULT_PAPER_BALANCE_NTD = float(os.getenv("DEFAULT_PAPER_BALANCE_NTD", "1000000"))

# TW market microstructure constants.
# - Round-lot: TWSE common-stock orders are 1,000 shares (盤中零股 exists but
#   we don't model 零股 in v1; rejected as INVALID_LOT_SIZE).
# - Daily price limit: ±10% of the previous trading day's close.
# - Trading session: 09:00–13:30 Asia/Taipei, Mon–Fri, excluding TWSE holidays.
TW_ROUND_LOT_SHARES = int(os.getenv("TW_ROUND_LOT_SHARES", "1000"))
TW_DAILY_PRICE_LIMIT_PCT = float(os.getenv("TW_DAILY_PRICE_LIMIT_PCT", "0.10"))
TW_SESSION_OPEN_HHMM = os.getenv("TW_SESSION_OPEN_HHMM", "09:00")
TW_SESSION_CLOSE_HHMM = os.getenv("TW_SESSION_CLOSE_HHMM", "13:30")

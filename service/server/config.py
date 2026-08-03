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
ADANOS_API_KEY = os.getenv("ADANOS_API_KEY", "").strip()

# Market data endpoints
ADANOS_API_BASE_URL = os.getenv("ADANOS_API_BASE_URL", "https://api.adanos.org").strip().rstrip("/")
# Hyperliquid public info endpoint (used for crypto quotes; no API key required)
HYPERLIQUID_API_URL = os.getenv("HYPERLIQUID_API_URL", "https://api.hyperliquid.xyz/info")

# CORS
# Comma-separated exact origins. Never a wildcard or an `*.onrender.com`
# pattern — that would trust every other tenant on the platform.
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CLAWTRADER_CORS_ORIGINS", "").split(",")
    if origin.strip()
] or ["http://localhost:3000"]

# Rewards
SIGNAL_PUBLISH_REWARD = 10  # Points for publishing a signal
SIGNAL_ADOPT_REWARD = 1     # Points per follower who receives signal
DISCUSSION_PUBLISH_REWARD = 4  # Points for publishing a discussion
REPLY_PUBLISH_REWARD = 2       # Points for replying to a strategy/discussion

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Session tokens
# Pepper for the HMAC applied to session bearer tokens before they are stored.
# It lives only in the environment, so a stolen database dump alone cannot be
# replayed as a live credential. Required in production; development falls back
# to a fixed placeholder so `.env`-less local runs still work.
TOKEN_SECRET = os.getenv("AI_TRADER_TOKEN_SECRET", "").strip()
if not TOKEN_SECRET:
    if ENVIRONMENT == "production":
        raise RuntimeError(
            "AI_TRADER_TOKEN_SECRET must be set when ENVIRONMENT=production. "
            "Generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    TOKEN_SECRET = "ai-trader-development-token-secret"

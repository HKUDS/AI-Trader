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
CORS_ORIGINS = os.getenv("CLAWTRADER_CORS_ORIGINS", "").split(",") if os.getenv("CLAWTRADER_CORS_ORIGINS") else ["http://localhost:3000"]

# Rewards
SIGNAL_PUBLISH_REWARD = 10  # Points for publishing a signal
SIGNAL_ADOPT_REWARD = 1     # Points per follower who receives signal
DISCUSSION_PUBLISH_REWARD = 4  # Points for publishing a discussion
REPLY_PUBLISH_REWARD = 2       # Points for replying to a strategy/discussion

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# ==================== LLM Token Pricing ====================
# USD per 1,000,000 tokens as (input_price, output_price).
# Ported from RadSim's MODEL_PRICING table (verified Jul 2026). Used to turn
# reported token counts into a cost estimate. Unknown models return None so
# callers can distinguish "unknown cost" from "genuinely free" — an unknown
# model must never be displayed as free.
MODEL_PRICING = {
    # Claude Series
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI GPT-5 Series
    "gpt-5.4": (5.00, 15.00),
    "gpt-5.3-codex": (5.00, 15.00),
    "gpt-5.2": (2.50, 10.00),
    "gpt-5.2-codex": (2.50, 10.00),
    "gpt-5-mini": (1.00, 4.00),
    # OpenRouter models (live pricing, verified Jul 2026)
    "minimax/minimax-m3": (0.30, 1.20),
    "deepseek/deepseek-v4-flash": (0.09, 0.18),
    "moonshotai/kimi-k2.5": (0.38, 2.02),
    "anthropic/claude-opus-4.8": (5.00, 25.00),
    "anthropic/claude-opus-4.6": (5.00, 25.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "openai/gpt-5.4": (2.50, 15.00),
    "openai/gpt-5.3-codex": (1.75, 14.00),
    "openai/gpt-5.2-codex": (1.75, 14.00),
    "minimax/minimax-m2.1": (0.30, 1.20),
    "z-ai/glm-5.2": (0.77, 2.42),
    "z-ai/glm-4.7": (0.40, 1.75),
}


def get_model_pricing(model):
    """Return (input, output) USD per 1M tokens for a model, or None when unknown.

    Returning None instead of zeros lets callers distinguish "unknown cost"
    from "genuinely free" — an unknown model must never display as free.
    """
    return MODEL_PRICING.get(model)

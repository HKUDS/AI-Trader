"""
RMF AI Dreams - Configuration Module
Centralized configuration for the entire platform
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / "rmf_ai_dreams.db"
THEME_PATH = BASE_DIR / "theme.css"

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "rmf-ai-dreams-super-secret-key-change-this")
OWNER_SECRET_CODE = os.getenv("OWNER_SECRET_CODE", "REEM_RMF_2026")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# AI Model APIs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", None)

# External Services
CAPTCHA_SOLVER_API_KEY = os.getenv("CAPTCHA_SOLVER_API_KEY", None)
PROXY_URL = os.getenv("PROXY_URL", None)

# Email Configuration
SMTP_CONFIG = {
    "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "port": int(os.getenv("SMTP_PORT", "587")),
    "user": os.getenv("SMTP_USER", ""),
    "password": os.getenv("SMTP_PASSWORD", "")
}

# Social Media APIs
TWITTER_CONFIG = {
    "api_key": os.getenv("TWITTER_API_KEY", ""),
    "api_secret": os.getenv("TWITTER_API_SECRET", "")
}

# Browser Automation
BROWSER_CONFIG = {
    "headless": os.getenv("HEADLESS_MODE", "true").lower() == "true",
    "executable_path": os.getenv("BROWSER_EXECUTABLE_PATH", None)
}

# Application Settings
APP_CONFIG = {
    "title": "RMF AI Dreams 🔮",
    "page_icon": "🔮",
    "layout": "wide",
    "initial_sidebar_state": "expanded"
}

# Theme Colors
THEME_COLORS = {
    "bg_black": "#000000",
    "neon_pink": "#FF00AA",
    "neon_purple": "#AA00FF",
    "neon_cyan": "#00FFFF",
    "success_glow": "#00FF88",
    "danger_glow": "#FF0055"
}

# Task Status
TASK_STATUS = {
    "PENDING": "pending",
    "PLANNING": "planning",
    "WAITING_APPROVAL": "waiting_approval",
    "EXECUTING": "executing",
    "COMPLETED": "completed",
    "CANCELLED": "cancelled",
    "FAILED": "failed"
}

# Risk Levels
RISK_LEVELS = {
    "LOW": "low",
    "MEDIUM": "medium",
    "HIGH": "high",
    "CRITICAL": "critical"
}

# Command Categories
COMMAND_CATEGORIES = {
    "ACCOUNT_CREATION": "account_creation",
    "CONTENT_POSTING": "content_posting",
    "RESEARCH": "research",
    "CREATIVE": "creative",
    "AUTOMATION": "automation",
    "STRATEGY": "strategy",
    "DATA_ANALYSIS": "data_analysis",
    "GENERAL": "general"
}

# Memory Categories
MEMORY_CATEGORIES = [
    "General",
    "Accounts",
    "Strategies",
    "Code Snippets",
    "Research",
    "API Keys",
    "Credentials",
    "Custom"
]

# Sensitive keywords (require approval)
SENSITIVE_KEYWORDS = [
    "create account",
    "sign up",
    "register",
    "post",
    "tweet",
    "publish",
    "delete",
    "payment",
    "credit card",
    "transfer money",
    "buy",
    "purchase",
    "automate",
    "selenium",
    "playwright",
    "scrape"
]

# Platform templates for account creation
PLATFORM_TEMPLATES = {
    "twitter": {
        "url": "https://twitter.com/i/flow/signup",
        "fields": ["name", "email", "username", "password", "birthdate"],
        "verification": "email"
    },
    "instagram": {
        "url": "https://www.instagram.com/accounts/emailsignup/",
        "fields": ["email", "fullname", "username", "password"],
        "verification": "email"
    },
    "linkedin": {
        "url": "https://www.linkedin.com/signup",
        "fields": ["email", "password", "firstname", "lastname"],
        "verification": "email"
    },
    "github": {
        "url": "https://github.com/signup",
        "fields": ["username", "email", "password"],
        "verification": "email"
    },
    "reddit": {
        "url": "https://www.reddit.com/register/",
        "fields": ["username", "password", "email"],
        "verification": "email"
    }
}

# Username generation patterns
USERNAME_PATTERNS = [
    "{adjective}_{noun}_{number}",
    "{name}_{tech_word}_{year}",
    "{name}_{profession}",
    "{cool_word}_{number}",
    "{name}_official",
    "{name}_{industry}"
]

# Adjectives for username generation
ADJECTIVES = [
    "ai", "digital", "cyber", "quantum", "neural", "smart", "tech",
    "future", "modern", "elite", "pro", "expert", "official", "real",
    "creative", "innovative", "advanced", "next_gen"
]

# Tech words for username generation
TECH_WORDS = [
    "ai", "tech", "digital", "cyber", "code", "dev", "labs", "systems",
    "solutions", "innovations", "ventures", "dynamics", "nexus", "hub"
]

# Default execution settings
EXECUTION_SETTINGS = {
    "max_retries": 3,
    "timeout_seconds": 300,
    "require_approval_for_sensitive": True,
    "auto_save_outputs": True,
    "log_all_actions": True,
    "enable_screenshots": True
}

# Export settings
EXPORT_FORMATS = ["PDF", "CSV", "JSON", "TXT", "XLSX"]

def get_config(key: str, default=None):
    """Get configuration value by key"""
    return globals().get(key, default)

def is_owner(role: str) -> bool:
    """Check if user role is owner"""
    return role.lower() == "owner"

def requires_approval(command: str) -> bool:
    """Check if command requires approval"""
    command_lower = command.lower()
    return any(keyword in command_lower for keyword in SENSITIVE_KEYWORDS)

"""
Centralized logging configuration for AI-Trader system.

This module provides a unified logging setup for all components of the trading system,
ensuring consistent log formatting, levels, and output destinations.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
import os
from datetime import datetime


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    Create and configure a logger instance.

    Args:
        name: Logger name (typically __name__ of the calling module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file. If None, logs only to console
        console_output: Whether to output logs to console (default: True)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if logger already configured
    if logger.hasHandlers():
        return logger

    logger.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_default_log_level() -> int:
    """
    Get logging level from environment variable or use default.

    Returns:
        Logging level (defaults to INFO)
    """
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_str, logging.INFO)


def get_logger_for_module(module_name: str) -> logging.Logger:
    """
    Convenience function to get a logger for a specific module.

    Args:
        module_name: Name of the module (typically __name__)

    Returns:
        Configured logger instance
    """
    level = get_default_log_level()

    # Determine if we should log to file based on environment
    log_to_file = os.getenv("LOG_TO_FILE", "false").lower() == "true"
    log_file = None

    if log_to_file:
        # Create log file in logs directory with timestamp
        project_root = Path(__file__).resolve().parents[1]
        logs_dir = project_root / "logs"
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = str(logs_dir / f"ai_trader_{timestamp}.log")

    return setup_logger(
        name=module_name,
        level=level,
        log_file=log_file,
        console_output=True
    )


# Create a default logger for the project
default_logger = get_logger_for_module("ai_trader")

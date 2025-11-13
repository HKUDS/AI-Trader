"""
Tests for logging configuration.
"""

import pytest
import logging
from pathlib import Path
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.logging_config import (
    setup_logger,
    get_default_log_level,
    get_logger_for_module
)


class TestLoggingSetup:
    """Tests for logging configuration."""

    @pytest.mark.unit
    def test_setup_logger_basic(self):
        """Test basic logger setup."""
        logger = setup_logger("test_logger", level=logging.INFO)

        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0

    @pytest.mark.unit
    def test_setup_logger_with_file(self, tmp_path):
        """Test logger setup with file handler."""
        log_file = tmp_path / "test.log"

        logger = setup_logger(
            "test_logger_file",
            level=logging.DEBUG,
            log_file=str(log_file)
        )

        assert len(logger.handlers) == 2  # Console + File
        assert log_file.exists()

    @pytest.mark.unit
    def test_setup_logger_no_console(self):
        """Test logger setup without console output."""
        logger = setup_logger(
            "test_logger_no_console",
            console_output=False
        )

        # Should have no handlers or only file handler
        console_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(console_handlers) == 0

    @pytest.mark.unit
    def test_logger_no_duplicate_handlers(self):
        """Test that re-calling setup doesn't add duplicate handlers."""
        logger1 = setup_logger("test_dup", level=logging.INFO)
        initial_count = len(logger1.handlers)

        logger2 = setup_logger("test_dup", level=logging.INFO)

        assert logger1 is logger2
        assert len(logger2.handlers) == initial_count

    @pytest.mark.unit
    def test_get_default_log_level_from_env(self, monkeypatch):
        """Test getting log level from environment variable."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        level = get_default_log_level()
        assert level == logging.DEBUG

        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        level = get_default_log_level()
        assert level == logging.WARNING

    @pytest.mark.unit
    def test_get_default_log_level_default(self, monkeypatch):
        """Test default log level when env var not set."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        level = get_default_log_level()
        assert level == logging.INFO

    @pytest.mark.unit
    def test_get_logger_for_module(self, monkeypatch):
        """Test convenience function for module logger."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_TO_FILE", "false")

        logger = get_logger_for_module("test_module")

        assert logger.name == "test_module"
        assert logger.level == logging.INFO

    @pytest.mark.unit
    def test_logger_formatting(self, tmp_path):
        """Test log message formatting."""
        log_file = tmp_path / "format_test.log"

        logger = setup_logger(
            "test_format",
            level=logging.INFO,
            log_file=str(log_file),
            console_output=False
        )

        test_message = "Test log message"
        logger.info(test_message)

        # Read log file and check format
        log_content = log_file.read_text()

        assert test_message in log_content
        assert "INFO" in log_content
        assert "test_format" in log_content
        # Check timestamp format (YYYY-MM-DD HH:MM:SS)
        assert "-" in log_content
        assert ":" in log_content

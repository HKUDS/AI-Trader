"""
Pytest configuration and shared fixtures for AI-Trader tests.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@pytest.fixture
def sample_nasdaq_symbols():
    """Return a small sample of NASDAQ 100 symbols for testing."""
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


@pytest.fixture
def sample_date():
    """Return a sample trading date."""
    return "2025-10-28"


@pytest.fixture
def sample_date_range():
    """Return a sample date range for testing."""
    return {
        "start": "2025-10-21",
        "end": "2025-10-28"
    }


@pytest.fixture
def sample_price_data():
    """Return sample OHLCV price data."""
    return {
        "AAPL": {
            "2025-10-28": {
                "1. buy price": "268.98",
                "2. high": "269.12",
                "3. low": "264.65",
                "4. sell price": "268.81",
                "5. volume": "44888152"
            },
            "2025-10-27": {
                "1. buy price": "264.88",
                "2. high": "269.12",
                "3. low": "264.65",
                "4. sell price": "268.81",
                "5. volume": "44888152"
            }
        },
        "MSFT": {
            "2025-10-28": {
                "1. buy price": "420.50",
                "2. high": "422.00",
                "3. low": "418.00",
                "4. sell price": "421.75",
                "5. volume": "20000000"
            },
            "2025-10-27": {
                "1. buy price": "418.00",
                "2. high": "422.00",
                "3. low": "417.00",
                "4. sell price": "420.50",
                "5. volume": "21000000"
            }
        }
    }


@pytest.fixture
def sample_position():
    """Return a sample position dictionary."""
    return {
        "AAPL": 10,
        "MSFT": 5,
        "GOOGL": 0,
        "CASH": 5000.0
    }


@pytest.fixture
def sample_position_record():
    """Return a sample position record from position.jsonl."""
    return {
        "date": "2025-10-28",
        "id": 1,
        "this_action": {
            "action": "buy",
            "symbol": "AAPL",
            "amount": 10
        },
        "positions": {
            "AAPL": 10,
            "MSFT": 0,
            "CASH": 7310.2
        }
    }


@pytest.fixture
def temp_merged_jsonl(sample_price_data, tmp_path):
    """Create a temporary merged.jsonl file with sample data."""
    merged_file = tmp_path / "merged.jsonl"

    for symbol, dates in sample_price_data.items():
        record = {
            "Meta Data": {
                "1. Information": "Daily Prices",
                "2. Symbol": symbol,
                "3. Last Refreshed": "2025-10-28"
            },
            "Time Series (Daily)": dates
        }
        with open(merged_file, "a") as f:
            f.write(json.dumps(record) + "\n")

    return merged_file


@pytest.fixture
def temp_position_file(sample_position_record, tmp_path):
    """Create a temporary position.jsonl file."""
    position_file = tmp_path / "position.jsonl"

    with open(position_file, "w") as f:
        f.write(json.dumps(sample_position_record) + "\n")

    return position_file


@pytest.fixture
def mock_env_vars(monkeypatch, sample_date):
    """Mock environment variables for testing."""
    monkeypatch.setenv("TODAY_DATE", sample_date)
    monkeypatch.setenv("SIGNATURE", "test-model")
    monkeypatch.setenv("IF_TRADE", "false")
    monkeypatch.setenv("LOG_LEVEL", "INFO")


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock .runtime_env.json file."""
    config_file = tmp_path / ".runtime_env.json"
    config_data = {
        "TODAY_DATE": "2025-10-28",
        "SIGNATURE": "test-model",
        "IF_TRADE": False
    }

    with open(config_file, "w") as f:
        json.dumps(config_data, f)

    return config_file


@pytest.fixture
def temp_agent_data_structure(tmp_path):
    """Create a temporary agent data directory structure."""
    model_name = "test-model"
    agent_dir = tmp_path / "data" / "agent_data" / model_name

    # Create directory structure
    (agent_dir / "position").mkdir(parents=True, exist_ok=True)
    (agent_dir / "log").mkdir(parents=True, exist_ok=True)

    # Create initial position file
    position_file = agent_dir / "position" / "position.jsonl"
    initial_position = {
        "date": "2025-10-27",
        "id": 0,
        "this_action": {"action": "init", "symbol": "", "amount": 0},
        "positions": {"CASH": 10000.0}
    }

    with open(position_file, "w") as f:
        f.write(json.dumps(initial_position) + "\n")

    return agent_dir


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests."""
    import logging
    # Clear all handlers from all loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    yield

    # Cleanup after test
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()

"""
Tests for price_tools.py functions.
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.price_tools import (
    get_yesterday_date,
    get_open_prices,
    get_yesterday_open_and_close_price,
    get_latest_position,
    get_yesterday_profit
)


class TestGetYesterdayDate:
    """Tests for get_yesterday_date function."""

    @pytest.mark.unit
    def test_regular_weekday(self):
        """Test yesterday date for regular weekday."""
        result = get_yesterday_date("2025-10-28")  # Tuesday
        assert result == "2025-10-27"  # Monday

    @pytest.mark.unit
    def test_monday_returns_friday(self):
        """Test Monday returns previous Friday."""
        result = get_yesterday_date("2025-10-27")  # Monday
        assert result == "2025-10-24"  # Friday

    @pytest.mark.unit
    def test_sunday_returns_friday(self):
        """Test Sunday skips to Friday."""
        result = get_yesterday_date("2025-10-26")  # Sunday
        assert result == "2025-10-24"  # Friday

    @pytest.mark.unit
    def test_saturday_returns_friday(self):
        """Test Saturday skips to Friday."""
        result = get_yesterday_date("2025-10-25")  # Saturday
        assert result == "2025-10-24"  # Friday


class TestGetOpenPrices:
    """Tests for get_open_prices function."""

    @pytest.mark.unit
    @pytest.mark.requires_data
    def test_get_prices_from_file(self, temp_merged_jsonl, sample_nasdaq_symbols, mock_env_vars):
        """Test retrieving opening prices from merged.jsonl."""
        result = get_open_prices(
            "2025-10-28",
            ["AAPL", "MSFT"],
            merged_path=str(temp_merged_jsonl)
        )

        assert "AAPL_price" in result
        assert "MSFT_price" in result
        assert result["AAPL_price"] == 268.98
        assert result["MSFT_price"] == 420.50

    @pytest.mark.unit
    def test_get_prices_missing_file(self, tmp_path):
        """Test behavior when merged.jsonl doesn't exist."""
        non_existent = tmp_path / "nonexistent.jsonl"
        result = get_open_prices(
            "2025-10-28",
            ["AAPL"],
            merged_path=str(non_existent)
        )

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.requires_data
    def test_get_prices_missing_symbol(self, temp_merged_jsonl, mock_env_vars):
        """Test retrieving price for symbol not in data."""
        result = get_open_prices(
            "2025-10-28",
            ["TSLA"],  # Not in our sample data
            merged_path=str(temp_merged_jsonl)
        )

        assert "TSLA_price" not in result

    @pytest.mark.unit
    @pytest.mark.requires_data
    def test_get_prices_missing_date(self, temp_merged_jsonl, mock_env_vars):
        """Test retrieving price for date not in data."""
        result = get_open_prices(
            "2025-12-31",  # Future date not in sample data
            ["AAPL"],
            merged_path=str(temp_merged_jsonl)
        )

        # Should return None for missing date
        assert result.get("AAPL_price") is None


class TestGetYesterdayOpenAndClosePrice:
    """Tests for get_yesterday_open_and_close_price function."""

    @pytest.mark.unit
    @pytest.mark.requires_data
    def test_get_yesterday_prices(self, temp_merged_jsonl, mock_env_vars):
        """Test retrieving yesterday's open and close prices."""
        buy_prices, sell_prices = get_yesterday_open_and_close_price(
            "2025-10-28",
            ["AAPL", "MSFT"],
            merged_path=str(temp_merged_jsonl)
        )

        assert "AAPL_price" in buy_prices
        assert "MSFT_price" in buy_prices
        assert buy_prices["AAPL_price"] == 264.88  # Yesterday's open
        assert sell_prices["AAPL_price"] == 268.81  # Yesterday's close

    @pytest.mark.unit
    @pytest.mark.requires_data
    def test_monday_gets_friday_prices(self, temp_merged_jsonl, mock_env_vars):
        """Test Monday correctly gets Friday's prices."""
        # Add Friday's data
        with open(temp_merged_jsonl, "a") as f:
            record = {
                "Meta Data": {
                    "1. Information": "Daily Prices",
                    "2. Symbol": "AAPL",
                    "3. Last Refreshed": "2025-10-24"
                },
                "Time Series (Daily)": {
                    "2025-10-24": {
                        "1. buy price": "260.00",
                        "4. sell price": "262.00"
                    }
                }
            }
            f.write(json.dumps(record) + "\n")

        # Test with Monday date
        buy_prices, sell_prices = get_yesterday_open_and_close_price(
            "2025-10-27",  # Monday
            ["AAPL"],
            merged_path=str(temp_merged_jsonl)
        )

        # Should get Friday's prices
        assert buy_prices["AAPL_price"] is not None


class TestGetYesterdayProfit:
    """Tests for get_yesterday_profit function."""

    @pytest.mark.unit
    def test_calculate_profit_basic(self):
        """Test basic profit calculation."""
        yesterday_buy = {"AAPL_price": 100.0}
        yesterday_sell = {"AAPL_price": 110.0}
        positions = {"AAPL": 10}

        profit = get_yesterday_profit(
            "2025-10-28",
            yesterday_buy,
            yesterday_sell,
            positions
        )

        assert "AAPL" in profit
        assert profit["AAPL"] == 100.0  # (110 - 100) * 10

    @pytest.mark.unit
    def test_calculate_profit_loss(self):
        """Test profit calculation with loss."""
        yesterday_buy = {"MSFT_price": 420.0}
        yesterday_sell = {"MSFT_price": 410.0}
        positions = {"MSFT": 5}

        profit = get_yesterday_profit(
            "2025-10-28",
            yesterday_buy,
            yesterday_sell,
            positions
        )

        assert profit["MSFT"] == -50.0  # (410 - 420) * 5

    @pytest.mark.unit
    def test_calculate_profit_no_position(self):
        """Test profit calculation when no position held."""
        yesterday_buy = {"AAPL_price": 100.0}
        yesterday_sell = {"AAPL_price": 110.0}
        positions = {"AAPL": 0}

        profit = get_yesterday_profit(
            "2025-10-28",
            yesterday_buy,
            yesterday_sell,
            positions
        )

        assert profit["AAPL"] == 0.0

    @pytest.mark.unit
    def test_calculate_profit_missing_price(self):
        """Test profit calculation with missing price data."""
        yesterday_buy = {"AAPL_price": None}
        yesterday_sell = {"AAPL_price": 110.0}
        positions = {"AAPL": 10}

        profit = get_yesterday_profit(
            "2025-10-28",
            yesterday_buy,
            yesterday_sell,
            positions
        )

        assert profit["AAPL"] == 0.0


class TestGetLatestPosition:
    """Tests for get_latest_position function."""

    @pytest.mark.unit
    @pytest.mark.requires_data
    def test_get_latest_position_same_day(self, temp_agent_data_structure, monkeypatch):
        """Test getting latest position from same day."""
        # Add a position for today
        position_file = temp_agent_data_structure / "position" / "position.jsonl"

        today_position = {
            "date": "2025-10-28",
            "id": 1,
            "this_action": {"action": "buy", "symbol": "AAPL", "amount": 10},
            "positions": {"AAPL": 10, "CASH": 7000.0}
        }

        with open(position_file, "a") as f:
            f.write(json.dumps(today_position) + "\n")

        # Mock the base_dir to use our temp structure
        from tools import price_tools
        original_file = price_tools.Path(__file__).resolve().parents[1]

        def mock_resolve():
            class MockPath:
                def parents(self):
                    return [temp_agent_data_structure.parent.parent]
            return MockPath()

        monkeypatch.setattr(Path, "resolve", lambda self: mock_resolve())

        # This test would require more complex mocking to work fully
        # Skipping for now as it requires significant refactoring
        pytest.skip("Requires refactoring for better testability")

    @pytest.mark.unit
    def test_get_latest_position_returns_highest_id(self):
        """Test that function returns position with highest ID."""
        # This would require mocking file I/O
        pytest.skip("Requires file I/O mocking")

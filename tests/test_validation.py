"""
Tests for input validation functions.
"""

import pytest
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from agent_tools.tool_trade import validate_trade_inputs
from tools.price_tools import validate_no_look_ahead, all_nasdaq_100_symbols


class TestTradeInputValidation:
    """Tests for trade input validation."""

    @pytest.mark.unit
    def test_valid_buy_inputs(self):
        """Test validation passes for valid buy inputs."""
        result = validate_trade_inputs("AAPL", 10, "buy")
        assert result is None

    @pytest.mark.unit
    def test_valid_sell_inputs(self):
        """Test validation passes for valid sell inputs."""
        result = validate_trade_inputs("MSFT", 5, "sell")
        assert result is None

    @pytest.mark.unit
    def test_invalid_symbol_empty(self):
        """Test validation fails for empty symbol."""
        result = validate_trade_inputs("", 10, "buy")
        assert result is not None
        assert "error" in result
        assert "non-empty string" in result["error"]

    @pytest.mark.unit
    def test_invalid_symbol_not_in_nasdaq100(self):
        """Test validation fails for symbol not in NASDAQ 100."""
        result = validate_trade_inputs("INVALID", 10, "buy")
        assert result is not None
        assert "error" in result
        assert "not in NASDAQ 100" in result["error"]

    @pytest.mark.unit
    def test_invalid_amount_negative(self):
        """Test validation fails for negative amount."""
        result = validate_trade_inputs("AAPL", -10, "buy")
        assert result is not None
        assert "error" in result
        assert "positive" in result["error"]

    @pytest.mark.unit
    def test_invalid_amount_zero(self):
        """Test validation fails for zero amount."""
        result = validate_trade_inputs("AAPL", 0, "buy")
        assert result is not None
        assert "error" in result
        assert "positive" in result["error"]

    @pytest.mark.unit
    def test_invalid_amount_type(self):
        """Test validation fails for non-integer amount."""
        result = validate_trade_inputs("AAPL", "10", "buy")
        assert result is not None
        assert "error" in result
        assert "integer" in result["error"]

    @pytest.mark.unit
    def test_all_nasdaq_symbols_valid(self):
        """Test all NASDAQ 100 symbols pass validation."""
        for symbol in all_nasdaq_100_symbols[:10]:  # Test first 10
            result = validate_trade_inputs(symbol, 1, "buy")
            assert result is None, f"Symbol {symbol} should be valid"


class TestLookAheadValidation:
    """Tests for look-ahead bias validation."""

    @pytest.mark.unit
    def test_no_look_ahead_same_date(self, mock_env_vars):
        """Test validation passes when dates are the same."""
        # Should not raise
        validate_no_look_ahead("2025-10-28", "test")

    @pytest.mark.unit
    def test_no_look_ahead_past_date(self, mock_env_vars):
        """Test validation passes for past dates."""
        # Should not raise
        validate_no_look_ahead("2025-10-27", "test")
        validate_no_look_ahead("2025-10-20", "test")

    @pytest.mark.unit
    def test_look_ahead_detected_future_date(self, mock_env_vars):
        """Test validation fails for future dates."""
        with pytest.raises(ValueError) as exc_info:
            validate_no_look_ahead("2025-10-29", "test")

        assert "Look-ahead bias detected" in str(exc_info.value)
        assert "2025-10-29" in str(exc_info.value)
        assert "2025-10-28" in str(exc_info.value)

    @pytest.mark.unit
    def test_look_ahead_no_today_date_set(self, monkeypatch):
        """Test validation passes when TODAY_DATE is not set."""
        # Remove TODAY_DATE env var
        monkeypatch.delenv("TODAY_DATE", raising=False)

        # Should not raise even for future date
        validate_no_look_ahead("2099-12-31", "test")

    @pytest.mark.unit
    def test_look_ahead_with_context(self, mock_env_vars):
        """Test context is included in error message."""
        with pytest.raises(ValueError) as exc_info:
            validate_no_look_ahead("2025-11-01", "get_price_data")

        assert "get_price_data" in str(exc_info.value)

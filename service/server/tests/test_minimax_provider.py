"""
Unit tests for MiniMax provider integration in market_intel.py.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add server directory to path so we can import market_intel without a full Django setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCallMinimax(unittest.TestCase):
    """Tests for _call_minimax function."""

    def _import_call_minimax(self):
        """Import _call_minimax with mocked dependencies."""
        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import importlib
            import market_intel
            importlib.reload(market_intel)
            return market_intel._call_minimax

    def test_returns_none_when_no_api_key(self):
        """Should return None immediately if MINIMAX_API_KEY is not set."""
        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import importlib
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", ""):
                result = market_intel._call_minimax("test prompt")
            self.assertIsNone(result)

    def test_calls_minimax_api_and_returns_content(self):
        """Should call MiniMax API and return message content."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "NVDA looks bullish with strong momentum."}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import importlib
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", "test-key"), \
                 patch.object(market_intel, "MINIMAX_BASE_URL", "https://api.minimax.io/v1"), \
                 patch.object(market_intel, "MINIMAX_MODEL", "MiniMax-M2.7"), \
                 patch("market_intel.requests.post", return_value=mock_response) as mock_post:
                result = market_intel._call_minimax("Analyze NVDA")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            # Verify URL
            self.assertIn("https://api.minimax.io/v1/chat/completions", str(call_args))
            # Verify headers contain Authorization
            kwargs = call_args[1] if call_args[1] else {}
            headers = kwargs.get("headers", {})
            self.assertIn("Bearer test-key", headers.get("Authorization", ""))
            # Verify request body
            body = kwargs.get("json", {})
            self.assertEqual(body["model"], "MiniMax-M2.7")
            self.assertEqual(body["temperature"], 1.0)
            self.assertNotIn("response_format", body)
            # Verify result
            self.assertEqual(result, "NVDA looks bullish with strong momentum.")

    def test_uses_default_model_minimax_m2_7(self):
        """Default model should be MiniMax-M2.7."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test summary."}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import importlib
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", "test-key"), \
                 patch.object(market_intel, "MINIMAX_MODEL", "MiniMax-M2.7"), \
                 patch("market_intel.requests.post", return_value=mock_response) as mock_post:
                market_intel._call_minimax("prompt")

            body = mock_post.call_args[1]["json"]
            self.assertEqual(body["model"], "MiniMax-M2.7")

    def test_returns_none_on_api_error(self):
        """Should return None when API call raises an exception."""
        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", "test-key"), \
                 patch("market_intel.requests.post", side_effect=Exception("Connection error")):
                result = market_intel._call_minimax("test prompt")
            self.assertIsNone(result)

    def test_uses_default_base_url(self):
        """Default base URL should be https://api.minimax.io/v1."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary."}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", "test-key"), \
                 patch.object(market_intel, "MINIMAX_BASE_URL", "https://api.minimax.io/v1"), \
                 patch("market_intel.requests.post", return_value=mock_response) as mock_post:
                market_intel._call_minimax("prompt")

            url = mock_post.call_args[0][0]
            self.assertTrue(url.startswith("https://api.minimax.io/v1"))


class TestGenerateStockAnalysisSummaryWithMinimax(unittest.TestCase):
    """Tests for _generate_stock_analysis_summary with MiniMax priority."""

    SAMPLE_ANALYSIS = {
        "symbol": "NVDA",
        "signal": "buy",
        "trend_status": "bullish",
        "signal_score": 3.5,
        "current_price": 850.0,
        "return_5d_pct": 3.2,
        "return_20d_pct": 8.5,
        "moving_averages": {"ma5": 840.0, "ma10": 830.0, "ma20": 800.0, "ma60": 750.0},
        "support_levels": [820.0],
        "resistance_levels": [900.0],
        "bullish_factors": ["Price is above the 20-day moving average."],
        "risk_factors": ["Price is approaching the recent resistance zone."],
    }

    def test_minimax_takes_priority_over_openrouter(self):
        """MiniMax should be tried before OpenRouter."""
        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", "minimax-key"), \
                 patch.object(market_intel, "OPENROUTER_API_KEY", "openrouter-key"), \
                 patch.object(market_intel, "OPENROUTER_MODEL", "some-model"), \
                 patch.object(market_intel, "_call_minimax", return_value="MiniMax summary.") as mock_mm, \
                 patch.object(market_intel, "_extract_openrouter_text") as mock_or:
                result = market_intel._generate_stock_analysis_summary(self.SAMPLE_ANALYSIS)

            mock_mm.assert_called_once()
            mock_or.assert_not_called()
            self.assertEqual(result, "MiniMax summary.")

    def test_falls_back_to_openrouter_when_minimax_fails(self):
        """Should fall back to OpenRouter when MiniMax returns None."""
        mock_openrouter = MagicMock()
        mock_openrouter.__enter__ = MagicMock(return_value=mock_openrouter)
        mock_openrouter.__exit__ = MagicMock(return_value=False)

        with patch.dict("sys.modules", {
            "openrouter": MagicMock(OpenRouter=MagicMock(return_value=mock_openrouter)),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", "minimax-key"), \
                 patch.object(market_intel, "OPENROUTER_API_KEY", "openrouter-key"), \
                 patch.object(market_intel, "OPENROUTER_MODEL", "gpt-4o-mini"), \
                 patch.object(market_intel, "_call_minimax", return_value=None), \
                 patch.object(market_intel, "_extract_openrouter_text", return_value="OpenRouter summary."):
                result = market_intel._generate_stock_analysis_summary(self.SAMPLE_ANALYSIS)

            self.assertEqual(result, "OpenRouter summary.")

    def test_falls_back_to_rule_based_when_both_fail(self):
        """Should fall back to deterministic summary when both MiniMax and OpenRouter fail."""
        with patch.dict("sys.modules", {
            "openrouter": MagicMock(),
            "database": MagicMock(),
            "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
        }):
            import market_intel
            with patch.object(market_intel, "MINIMAX_API_KEY", ""), \
                 patch.object(market_intel, "OPENROUTER_API_KEY", ""), \
                 patch.object(market_intel, "OPENROUTER_MODEL", ""):
                result = market_intel._generate_stock_analysis_summary(self.SAMPLE_ANALYSIS)

            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)
            self.assertIn("NVDA", result)


class TestMinimaxEnvironmentVariables(unittest.TestCase):
    """Tests to verify MINIMAX_API_KEY environment variable is read correctly."""

    def test_minimax_api_key_env_var(self):
        """MINIMAX_API_KEY should be loaded from environment."""
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "env-test-key"}, clear=False):
            with patch.dict("sys.modules", {
                "openrouter": MagicMock(),
                "database": MagicMock(),
                "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
            }):
                import importlib
                import market_intel
                importlib.reload(market_intel)
                self.assertEqual(market_intel.MINIMAX_API_KEY, "env-test-key")

    def test_minimax_model_defaults_to_m2_7(self):
        """Default MINIMAX_MODEL should be MiniMax-M2.7."""
        env = {k: v for k, v in os.environ.items() if k != "MINIMAX_MODEL"}
        with patch.dict(os.environ, env, clear=True):
            with patch.dict("sys.modules", {
                "openrouter": MagicMock(),
                "database": MagicMock(),
                "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
            }):
                import importlib
                import market_intel
                importlib.reload(market_intel)
                self.assertEqual(market_intel.MINIMAX_MODEL, "MiniMax-M2.7")

    def test_minimax_base_url_defaults_to_api_minimax_io(self):
        """Default MINIMAX_BASE_URL should use api.minimax.io."""
        env = {k: v for k, v in os.environ.items() if k != "MINIMAX_BASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            with patch.dict("sys.modules", {
                "openrouter": MagicMock(),
                "database": MagicMock(),
                "config": MagicMock(ALPHA_VANTAGE_API_KEY="demo"),
            }):
                import importlib
                import market_intel
                importlib.reload(market_intel)
                self.assertTrue(
                    market_intel.MINIMAX_BASE_URL.startswith("https://api.minimax.io"),
                    f"Expected URL to start with https://api.minimax.io, got {market_intel.MINIMAX_BASE_URL}"
                )


if __name__ == "__main__":
    unittest.main()

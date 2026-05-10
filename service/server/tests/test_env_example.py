import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
KEY_VALUE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
SEPARATOR_RE = re.compile(r"^=+$")
REQUIRED_KEYS = {
    "ENVIRONMENT",
    "DATABASE_URL",
    "DB_PATH",
    "ALPHA_VANTAGE_API_KEY",
    "VITE_REFRESH_INTERVAL",
    "CLAWTRADER_CORS_ORIGINS",
    "ALPHA_VANTAGE_BASE_URL",
    "HYPERLIQUID_API_URL",
    "POLYMARKET_GAMMA_BASE_URL",
    "POLYMARKET_CLOB_BASE_URL",
    "POSITION_REFRESH_INTERVAL",
    "MAX_PARALLEL_PRICE_FETCH",
    "POLYMARKET_SETTLE_INTERVAL",
    "MARKET_NEWS_REFRESH_INTERVAL",
    "MACRO_SIGNAL_REFRESH_INTERVAL",
    "ETF_FLOW_REFRESH_INTERVAL",
    "STOCK_ANALYSIS_REFRESH_INTERVAL",
    "PROFIT_HISTORY_FULL_RESOLUTION_HOURS",
    "PROFIT_HISTORY_COMPACT_WINDOW_DAYS",
    "PROFIT_HISTORY_COMPACT_BUCKET_MINUTES",
    "PROFIT_HISTORY_PRUNE_INTERVAL_SECONDS",
    "PRICE_FETCH_TIMEOUT_SECONDS",
    "PRICE_FETCH_MAX_RETRIES",
    "PRICE_FETCH_BACKOFF_BASE_SECONDS",
    "PRICE_FETCH_ERROR_COOLDOWN_SECONDS",
    "PRICE_FETCH_RATE_LIMIT_COOLDOWN_SECONDS",
}


class EnvExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    def active_entries(self):
        return [
            line.strip()
            for line in self.lines
            if line.strip() and not line.lstrip().startswith("#")
        ]

    def parsed_entries(self):
        entries = {}
        for line in self.active_entries():
            key, value = line.split("=", 1)
            entries[key] = value
        return entries

    def test_non_comment_lines_are_key_value_pairs(self) -> None:
        invalid_lines = [
            (line_number, line)
            for line_number, line in enumerate(self.lines, start=1)
            if line.strip()
            and not line.lstrip().startswith("#")
            and not KEY_VALUE_RE.match(line.strip())
        ]
        self.assertEqual([], invalid_lines)

    def test_no_bare_separator_lines(self) -> None:
        bare_separators = [
            (line_number, line)
            for line_number, line in enumerate(self.lines, start=1)
            if SEPARATOR_RE.match(line.strip())
        ]
        self.assertEqual([], bare_separators)

    def test_required_keys_are_present(self) -> None:
        self.assertEqual(set(), REQUIRED_KEYS - set(self.parsed_entries()))

    def test_database_url_default_and_example_are_sane(self) -> None:
        entries = self.parsed_entries()
        self.assertIn("DATABASE_URL", entries)
        self.assertEqual("", entries["DATABASE_URL"])

        database_url_lines = [
            (line_number, line.strip())
            for line_number, line in enumerate(self.lines, start=1)
            if "DATABASE_URL" in line
        ]
        active_database_url_lines = [
            line for _, line in database_url_lines if not line.lstrip().startswith("#")
        ]
        self.assertEqual(["DATABASE_URL="], active_database_url_lines)

        example_lines = [
            line for _, line in database_url_lines if line.lstrip().startswith("#") and "=" in line
        ]
        self.assertTrue(example_lines, "Expected a commented DATABASE_URL example")
        for example in example_lines:
            _, value = example.split("DATABASE_URL=", 1)
            self.assertTrue(value.startswith("postgresql://"), example)
            self.assertNotRegex(value, r"\s", example)


if __name__ == "__main__":
    unittest.main()

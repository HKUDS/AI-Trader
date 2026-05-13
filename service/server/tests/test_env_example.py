import os
import sys
import unittest
from pathlib import Path

from dotenv import dotenv_values


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


ROOT_DIR = Path(__file__).resolve().parents[3]


class EnvExampleTests(unittest.TestCase):
    def test_env_example_is_parseable_by_dotenv(self) -> None:
        values = dotenv_values(ROOT_DIR / ".env.example")

        self.assertEqual(values["ENVIRONMENT"], "development")
        self.assertEqual(values["DATABASE_URL"], "")
        self.assertEqual(values["DB_PATH"], "service/server/data/clawtrader.db")
        self.assertEqual(values["ALPHA_VANTAGE_BASE_URL"], "https://www.alphavantage.co/query")
        self.assertNotIn("ai_trader:change-me", values.values())

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from routes_shared import should_fetch_server_trade_price


class TradePriceSourceTests(unittest.TestCase):
    def test_crypto_and_polymarket_always_use_server_prices(self) -> None:
        with patch.dict(os.environ, {'ALLOW_SYNC_PRICE_FETCH_IN_API': 'false'}, clear=False):
            self.assertTrue(should_fetch_server_trade_price('crypto'))
            self.assertTrue(should_fetch_server_trade_price('polymarket'))
            self.assertFalse(should_fetch_server_trade_price('us-stock'))

    def test_env_flag_keeps_server_fetch_for_other_markets(self) -> None:
        with patch.dict(os.environ, {'ALLOW_SYNC_PRICE_FETCH_IN_API': 'true'}, clear=False):
            self.assertTrue(should_fetch_server_trade_price('us-stock'))


if __name__ == '__main__':
    unittest.main()

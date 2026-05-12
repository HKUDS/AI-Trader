"""Tests for service.server.data_sources.tw_market_twstock.

We never hit the real TWSE / TPEX endpoints. `twstock.codes` is replaced with
a stub dict; `twstock.Stock` and `twstock.realtime.get` are monkeypatched.

Coverage:
  - get_stock_info: hit, miss, market label mapping (上市/上櫃/other).
  - fetch_historical_prices: row coercion, empty, exception fallback.
  - fetch_realtime: success, failed-payload, missing fields.
  - get_realtime_close: convenience wrapper happy / sad paths.
  - best_four_point: tuple coercion, False -> None.
  - _throttle: 4 calls in <5s sleeps once.
"""

import sys
import time
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import twstock  # noqa: E402  (require twstock present)

from data_sources import tw_market_twstock as twm  # noqa: E402


StockCodeInfo = namedtuple(
    "StockCodeInfo",
    ["type", "code", "name", "ISIN", "start", "market", "group", "CFI", "data_source"],
)

DATATUPLE = namedtuple(
    "DATATUPLE",
    ["date", "capacity", "turnover", "open", "high", "low", "close", "change", "transaction", "note"],
)


class FakeDate:
    def __init__(self, value: str):
        self._value = value

    def isoformat(self) -> str:
        return self._value


class FakeStock:
    """Stand-in for twstock.Stock — never hits the network."""

    def __init__(self, sid, initial_fetch=True, force_data_source=None):
        self.sid = sid
        self._rows: list = []

    def fetch_from(self, year, month):
        return self._rows


class TestGetStockInfo(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(
            twstock.codes,
            {
                "2330": StockCodeInfo(
                    type="股票", code="2330", name="台積電", ISIN="TW0002330008",
                    start="1994/09/05", market="上市", group="半導體業",
                    CFI="ESVUFR", data_source="twse",
                ),
                "6488": StockCodeInfo(
                    type="股票", code="6488", name="環球晶", ISIN="x", start="2015/04/24",
                    market="上櫃", group="半導體業", CFI="ESVUFR", data_source="tpex",
                ),
                "0000": StockCodeInfo(
                    type="股票", code="0000", name="Weird", ISIN="x", start="2000/01/01",
                    market="OtherMarket", group="x", CFI="x", data_source="x",
                ),
            },
            clear=True,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_returns_twse_info_with_market_label_mapped(self):
        info = twm.get_stock_info("2330")
        self.assertEqual(info["symbol"], "2330")
        self.assertEqual(info["name"], "台積電")
        self.assertEqual(info["market"], "TWSE")
        self.assertEqual(info["group"], "半導體業")

    def test_tpex_market_label_mapped(self):
        info = twm.get_stock_info("6488")
        self.assertEqual(info["market"], "TPEX")

    def test_unknown_market_label_passes_through(self):
        info = twm.get_stock_info("0000")
        self.assertEqual(info["market"], "OtherMarket")

    def test_missing_symbol_returns_empty(self):
        self.assertEqual(twm.get_stock_info("9999"), {})

    def test_whitespace_and_case_normalized(self):
        # "2330" exists; "  2330  " (with whitespace) must still resolve.
        self.assertEqual(twm.get_stock_info("  2330  ")["symbol"], "2330")


class TestFetchHistoricalPrices(unittest.TestCase):
    def setUp(self):
        twm._reset_throttle_for_tests()

    def test_returns_coerced_dicts(self):
        rows = [
            DATATUPLE(
                date=FakeDate("2026-05-01"), capacity=1000, turnover=2000,
                open=10.0, high=11.0, low=9.5, close=10.5, change=0.5,
                transaction=42, note=None,
            ),
        ]

        class _FakeWithRows(FakeStock):
            def fetch_from(self, year, month):
                return rows

        with patch.object(twstock, "Stock", _FakeWithRows):
            out = twm.fetch_historical_prices("2330", 2026, 5)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["date"], "2026-05-01")
        self.assertEqual(out[0]["close"], 10.5)
        self.assertEqual(out[0]["volume"], 1000)

    def test_empty_symbol_returns_empty_list_no_throttle(self):
        # Should not raise, should not call Stock.
        with patch.object(twstock, "Stock") as mock_stock:
            self.assertEqual(twm.fetch_historical_prices("", 2026, 5), [])
            mock_stock.assert_not_called()

    def test_upstream_exception_returns_empty(self):
        class _Boom:
            def __init__(self, *a, **k):
                pass

            def fetch_from(self, *a, **k):
                raise RuntimeError("twstock parse exploded")

        with patch.object(twstock, "Stock", _Boom):
            self.assertEqual(twm.fetch_historical_prices("2330", 2026, 5), [])


class TestFetchRealtime(unittest.TestCase):
    def setUp(self):
        twm._reset_throttle_for_tests()

    def test_success_path(self):
        payload = {
            "success": True,
            "timestamp": 1715500000.0,
            "info": {"code": "2330", "name": "台積電"},
            "realtime": {
                "latest_trade_price": "1010.5",
                "trade_volume": "100",
                "open": "1005",
                "high": "1015",
                "low": "1000",
                "accumulate_trade_volume": "20000",
            },
        }
        with patch.object(twstock.realtime, "get", return_value=payload):
            out = twm.fetch_realtime("2330")
        self.assertEqual(out["latest_trade_price"], 1010.5)
        self.assertEqual(out["trade_volume"], 100)
        self.assertEqual(out["accumulate_trade_volume"], 20000)
        self.assertEqual(out["symbol"], "2330")

    def test_failed_payload_returns_empty(self):
        with patch.object(twstock.realtime, "get", return_value={"success": False}):
            self.assertEqual(twm.fetch_realtime("2330"), {})

    def test_missing_fields_coerced_to_zero(self):
        payload = {
            "success": True,
            "timestamp": 0,
            "info": {"code": "2330", "name": "台積電"},
            "realtime": {"latest_trade_price": "", "trade_volume": None},
        }
        with patch.object(twstock.realtime, "get", return_value=payload):
            out = twm.fetch_realtime("2330")
        self.assertEqual(out["latest_trade_price"], 0.0)
        self.assertEqual(out["trade_volume"], 0)

    def test_realtime_get_raises_returns_empty(self):
        with patch.object(twstock.realtime, "get", side_effect=ConnectionError("boom")):
            self.assertEqual(twm.fetch_realtime("2330"), {})

    def test_empty_symbol_returns_empty(self):
        self.assertEqual(twm.fetch_realtime(""), {})


class TestGetRealtimeClose(unittest.TestCase):
    def setUp(self):
        twm._reset_throttle_for_tests()

    def test_returns_price_on_success(self):
        payload = {
            "success": True,
            "timestamp": 0,
            "info": {"code": "2330", "name": "x"},
            "realtime": {"latest_trade_price": "999.5"},
        }
        with patch.object(twstock.realtime, "get", return_value=payload):
            self.assertEqual(twm.get_realtime_close("2330"), 999.5)

    def test_returns_none_on_zero_price(self):
        payload = {
            "success": True,
            "timestamp": 0,
            "info": {"code": "2330", "name": "x"},
            "realtime": {"latest_trade_price": "0"},
        }
        with patch.object(twstock.realtime, "get", return_value=payload):
            self.assertIsNone(twm.get_realtime_close("2330"))

    def test_returns_none_on_failed_payload(self):
        with patch.object(twstock.realtime, "get", return_value={"success": False}):
            self.assertIsNone(twm.get_realtime_close("2330"))


class TestBestFourPoint(unittest.TestCase):
    def setUp(self):
        twm._reset_throttle_for_tests()

    def test_tuples_pass_through(self):
        class _FakeBFP:
            def __init__(self, stock):
                pass

            def best_four_point_to_buy(self):
                return (True, "短期均線突破")

            def best_four_point_to_sell(self):
                return False  # twstock signals "no signal" with False, not None

            def best_four_point(self):
                return (True, "整體偏多")

        with patch.object(twstock, "Stock", FakeStock), \
             patch.object(twstock, "BestFourPoint", _FakeBFP):
            out = twm.best_four_point("2330")
        self.assertEqual(out["symbol"], "2330")
        self.assertEqual(out["buy_signal"], (True, "短期均線突破"))
        self.assertIsNone(out["sell_signal"])
        self.assertEqual(out["combined"], (True, "整體偏多"))

    def test_empty_symbol_returns_null_signals(self):
        out = twm.best_four_point("")
        self.assertEqual(out, {"symbol": "", "buy_signal": None, "sell_signal": None, "combined": None})

    def test_upstream_exception_returns_null_signals(self):
        class _Boom:
            def __init__(self, *a, **k):
                raise RuntimeError("network down")

        with patch.object(twstock, "Stock", _Boom):
            out = twm.best_four_point("2330")
        self.assertIsNone(out["buy_signal"])
        self.assertIsNone(out["combined"])


class TestThrottle(unittest.TestCase):
    def setUp(self):
        twm._reset_throttle_for_tests()

    def test_third_call_within_window_does_not_block(self):
        # 3 calls fit cleanly inside 5s — should be near-instant.
        start = time.monotonic()
        for _ in range(3):
            twm._throttle()
        self.assertLess(time.monotonic() - start, 0.5)

    def test_fourth_call_blocks_until_window_clears(self):
        # Pre-load the throttle with 3 fake-timestamps "now" so the next
        # call has to wait for one to age out.
        with patch("time.sleep") as mock_sleep:
            for _ in range(3):
                twm._throttle()
            twm._throttle()  # 4th — should request sleep
            self.assertTrue(mock_sleep.called, "throttle should have called time.sleep on 4th call")
            sleep_arg = mock_sleep.call_args[0][0]
            # Sleep argument must be in (0, REQ_WINDOW_SECONDS].
            self.assertGreaterEqual(sleep_arg, 0)
            self.assertLessEqual(sleep_arg, twm._REQ_WINDOW_SECONDS + 0.01)


if __name__ == "__main__":
    unittest.main()

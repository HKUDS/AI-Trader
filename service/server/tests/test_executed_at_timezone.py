import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from routes_shared import validate_executed_at


WITHOUT_TZ_DATABASE = textwrap.dedent(
    """
    import sys
    import zoneinfo


    class _BlockTzdata:
        def find_spec(self, name, path=None, target=None):
            if name == "tzdata" or name.startswith("tzdata."):
                raise ImportError("tzdata is blocked for this test")
            return None


    sys.meta_path.insert(0, _BlockTzdata())
    zoneinfo.reset_tzpath([])

    try:
        zoneinfo.ZoneInfo("America/New_York")
    except zoneinfo.ZoneInfoNotFoundError:
        pass
    else:
        print("tz database still reachable")
        raise SystemExit(2)

    sys.path.insert(0, sys.argv[1])
    from routes_shared import validate_executed_at

    market = sys.argv[2]
    executed_at = sys.argv[3]
    try:
        print(validate_executed_at(executed_at, market))
    except zoneinfo.ZoneInfoNotFoundError as exc:
        print(f"raised ZoneInfoNotFoundError: {exc}")
    """
)


def _without_tz_database(market: str, executed_at: str = "2026-05-19T14:00:00Z") -> str:
    result = subprocess.run(
        [sys.executable, "-c", WITHOUT_TZ_DATABASE, str(SERVER_DIR), market, executed_at],
        capture_output=True,
        text=True,
    )
    if result.returncode == 2:
        raise unittest.SkipTest("precondition not met: " + result.stdout.strip())
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class ExecutedAtWithoutTzDatabaseTests(unittest.TestCase):
    """A missing tz database must not be reported as a bad timestamp."""

    def test_crypto_does_not_need_the_tz_database(self) -> None:
        self.assertEqual(_without_tz_database("crypto"), "(True, '')")

    def test_polymarket_does_not_need_the_tz_database(self) -> None:
        self.assertEqual(_without_tz_database("polymarket"), "(True, '')")

    def test_us_stock_raises_instead_of_blaming_the_timestamp(self) -> None:
        self.assertIn("raised ZoneInfoNotFoundError", _without_tz_database("us-stock"))

    def test_now_for_crypto_does_not_need_the_tz_database(self) -> None:
        self.assertEqual(_without_tz_database("crypto", "now"), "(True, '')")

    def test_now_for_us_stock_raises_instead_of_blaming_the_timestamp(self) -> None:
        self.assertIn("raised ZoneInfoNotFoundError", _without_tz_database("us-stock", "now"))


class ExecutedAtWithTzDatabaseTests(unittest.TestCase):
    """The ordinary behaviour is unchanged."""

    def test_us_stock_inside_trading_hours_is_accepted(self) -> None:
        self.assertEqual(validate_executed_at("2026-05-19T14:00:00Z", "us-stock"), (True, ""))

    def test_us_stock_outside_trading_hours_is_rejected(self) -> None:
        valid, reason = validate_executed_at("2026-05-19T02:00:00Z", "us-stock")

        self.assertFalse(valid)
        self.assertIn("US market is closed", reason)

    def test_crypto_at_the_same_hour_is_accepted(self) -> None:
        self.assertEqual(validate_executed_at("2026-05-19T02:00:00Z", "crypto"), (True, ""))

    def test_a_non_utc_timestamp_is_rejected(self) -> None:
        valid, reason = validate_executed_at("2026-05-19T14:00:00", "us-stock")

        self.assertFalse(valid)
        self.assertIn("must be in UTC format", reason)

    def test_a_malformed_timestamp_is_rejected(self) -> None:
        valid, reason = validate_executed_at("not-a-timestampZ", "us-stock")

        self.assertFalse(valid)
        self.assertIn("Invalid datetime format", reason)


if __name__ == "__main__":
    unittest.main()

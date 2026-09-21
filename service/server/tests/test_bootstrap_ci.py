import math
import statistics
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_SCRIPTS = REPO_ROOT / "research" / "scripts"
if str(RESEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(RESEARCH_SCRIPTS))

from research_common import bootstrap_ci, mean


class BootstrapCiTests(unittest.TestCase):
    """The interval has to describe the mean, not repeat it."""

    def test_a_sample_with_spread_gets_an_interval_with_width(self) -> None:
        values = [1.0, 2.0, 3.0, 100.0]

        low, high = bootstrap_ci(values)

        self.assertGreater(high - low, 0.0)
        self.assertLessEqual(low, mean(values))
        self.assertGreaterEqual(high, mean(values))

    def test_the_interval_is_not_the_spread_of_the_raw_values(self) -> None:
        values = [float(v) for v in range(1, 8)]

        low, high = bootstrap_ci(values)

        self.assertGreater(low, min(values))
        self.assertLess(high, max(values))

    def test_it_approximates_the_normal_interval_on_a_large_sample(self) -> None:
        values = [float(v % 10) for v in range(500)]
        sample_mean = statistics.fmean(values)
        standard_error = statistics.stdev(values) / math.sqrt(len(values))

        low, high = bootstrap_ci(values)

        self.assertAlmostEqual(low, sample_mean - 1.96 * standard_error, delta=0.05)
        self.assertAlmostEqual(high, sample_mean + 1.96 * standard_error, delta=0.05)

    def test_it_is_deterministic(self) -> None:
        values = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]

        self.assertEqual(bootstrap_ci(values), bootstrap_ci(values))

    def test_an_empty_sample_returns_zeros(self) -> None:
        self.assertEqual(bootstrap_ci([]), (0.0, 0.0))

    def test_a_constant_sample_has_no_width(self) -> None:
        low, high = bootstrap_ci([7.0, 7.0, 7.0, 7.0])

        self.assertEqual((low, high), (7.0, 7.0))


if __name__ == "__main__":
    unittest.main()

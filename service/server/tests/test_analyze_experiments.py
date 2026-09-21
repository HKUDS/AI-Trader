import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_SCRIPTS = REPO_ROOT / "research" / "scripts"
if str(RESEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(RESEARCH_SCRIPTS))

from analyze_experiments import analysis_rows, did_rows
from research_common import benjamini_hochberg


def _rows(metric: str, control: list, treatment: list, created_at: str = "2026-09-01T00:00:00Z") -> list:
    rows = []
    for variant, values in (("control", control), ("treatment", treatment)):
        for value in values:
            rows.append({
                "experiment_key": "exp1",
                "variant_key": variant,
                metric: value,
                "created_at": created_at,
            })
    return rows


def _by_method(rows: list, method: str, variant: str = "treatment") -> dict:
    for row in rows:
        if row["method"] == method and row["variant_key"] == variant:
            return row
    raise AssertionError(f"{method}/{variant} missing")


class ControlColumnTests(unittest.TestCase):
    """The metric under analysis must not be used to adjust itself."""

    def test_regression_does_not_control_the_metric_on_itself(self) -> None:
        rows = analysis_rows(_rows("max_drawdown", [2.0, 3.0, 4.0], [18.0, 20.0, 22.0]), "max_drawdown", "competition")

        regression = _by_method(rows, "regression_with_controls")

        self.assertNotEqual(regression["segment"], "control:max_drawdown")
        self.assertAlmostEqual(regression["effect"], 17.0, places=4)

    def test_hte_does_not_segment_on_the_metric_itself(self) -> None:
        rows = analysis_rows(_rows("weight", [1.0, 2.0, 3.0], [8.0, 9.0, 10.0]), "weight", "network")

        segments = {row["segment"] for row in rows if row["method"] == "heterogeneous_treatment_effects"}

        self.assertTrue(segments)
        for segment in segments:
            self.assertFalse(segment.startswith("weight:"), f"segmented on the metric itself: {segment}")

    def test_a_different_control_column_is_still_used_when_available(self) -> None:
        rows = _rows("max_drawdown", [2.0, 3.0], [18.0, 20.0])
        for index, row in enumerate(rows):
            row["trade_count"] = index + 1

        regression = _by_method(analysis_rows(rows, "max_drawdown", "competition"), "regression_with_controls")

        self.assertEqual(regression["segment"], "control:trade_count")


class DifferenceInDifferencesTests(unittest.TestCase):
    """An empty side is not a level of zero, and an untested row is not p = 1."""

    def _staggered(self) -> list:
        rows = []
        for day, value in ((1, 10.0), (2, 10.0), (3, 10.0), (4, 10.0)):
            rows.append({"experiment_key": "exp1", "variant_key": "control",
                         "return_pct": value, "created_at": f"2026-09-0{day}T00:00:00Z"})
        for day, value in ((1, 30.0), (2, 30.0)):
            rows.append({"experiment_key": "exp1", "variant_key": "treatment",
                         "return_pct": value, "created_at": f"2026-09-0{day}T00:00:00Z"})
        return rows

    def test_an_empty_side_leaves_the_effect_unset(self) -> None:
        treatment = _by_method(did_rows(self._staggered(), "return_pct", "competition"),
                               "difference_in_differences")

        self.assertIsNone(treatment["effect"])

    def test_a_did_row_carries_no_p_value(self) -> None:
        for row in did_rows(self._staggered(), "return_pct", "competition"):
            self.assertIsNone(row["p_value"])

    def test_a_did_effect_is_reported_when_both_sides_have_rows(self) -> None:
        # Six rows, so the split is times[3], the second timestamp of each
        # variant. Both variants then keep two rows before it and one after,
        # which is what makes the expected value independent of rounding.
        rows = []
        for variant, before, after in (("control", 10.0, 12.0), ("treatment", 10.0, 20.0)):
            for day, value in ((1, before), (2, before), (5, after)):
                rows.append({"experiment_key": "exp1", "variant_key": variant,
                             "return_pct": value, "created_at": f"2026-09-0{day}T00:00:00Z"})

        treatment = _by_method(did_rows(rows, "return_pct", "competition"), "difference_in_differences")

        self.assertAlmostEqual(treatment["effect"], 8.0, places=4)


class BenjaminiHochbergTests(unittest.TestCase):
    def test_rows_without_a_p_value_do_not_count_towards_the_correction(self) -> None:
        tested = [{"p_value": 0.01}, {"p_value": 0.02}]
        mixed = [{"p_value": 0.01}, {"p_value": 0.02}, {"p_value": None}, {"p_value": None}]

        benjamini_hochberg(tested)
        benjamini_hochberg(mixed)

        self.assertAlmostEqual(mixed[0]["q_value"], tested[0]["q_value"], places=6)
        self.assertAlmostEqual(mixed[1]["q_value"], tested[1]["q_value"], places=6)
        self.assertIsNone(mixed[2]["q_value"])


if __name__ == "__main__":
    unittest.main()

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_SCRIPTS = REPO_ROOT / "research" / "scripts"
if str(RESEARCH_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(RESEARCH_SCRIPTS))

from compute_metrics import compute_metrics


QUALITY_FIELDS = [
    "id", "signal_id", "agent_id", "agent_hash", "verifiability_score",
    "evidence_score", "specificity_score", "novelty_score", "review_score",
    "overall_score", "model_version", "metadata_json", "created_at",
    "market", "experiment_key", "variant_key",
]


def _write_quality_scores(input_dir: Path, duplicate_counts: list) -> None:
    rows = []
    for index, duplicate_count in enumerate(duplicate_counts, start=1):
        metadata = {"prediction_id": index}
        if duplicate_count is not None:
            metadata["duplicate_count"] = duplicate_count
        rows.append({
            "id": index, "signal_id": 100 + index, "agent_id": 1, "agent_hash": 1,
            "verifiability_score": 3.0, "evidence_score": 2.0, "specificity_score": 2.0,
            "novelty_score": 5.0, "review_score": 1.0, "overall_score": 2.8,
            "model_version": "heuristic-v1",
            "metadata_json": json.dumps(metadata, sort_keys=True),
            "created_at": "2026-09-01T00:00:00Z", "market": "crypto",
            "experiment_key": "", "variant_key": "",
        })
    with (input_dir / "quality_scores.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUALITY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _content_metric(output_dir: Path, metric: str) -> dict:
    with (output_dir / "content_metrics.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["metric"] == metric:
                return row
    raise AssertionError(f"{metric} missing from content_metrics.csv")


class DuplicateContentRateTests(unittest.TestCase):
    def _run(self, duplicate_counts: list) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            input_dir = Path(directory) / "in"
            output_dir = Path(directory) / "out"
            input_dir.mkdir()
            _write_quality_scores(input_dir, duplicate_counts)
            compute_metrics(str(input_dir), str(output_dir))
            return _content_metric(output_dir, "duplicate_content_rate")

    def test_rate_is_the_share_of_rows_flagged_as_duplicates(self) -> None:
        row = self._run([0, 1, 2, 3])

        self.assertEqual(float(row["value"]), 0.75)
        self.assertEqual(int(row["n"]), 4)

    def test_rate_is_zero_when_no_row_is_a_duplicate(self) -> None:
        row = self._run([0, 0, 0])

        self.assertEqual(float(row["value"]), 0.0)
        self.assertEqual(int(row["n"]), 3)

    def test_rows_without_a_duplicate_count_are_not_counted_as_unique(self) -> None:
        row = self._run([None, None, 2])

        self.assertEqual(float(row["value"]), 1.0)
        self.assertEqual(int(row["n"]), 1)


if __name__ == "__main__":
    unittest.main()

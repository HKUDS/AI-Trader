"""Generate paper statistical analysis tables."""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from typing import Any

from research_common import (
    TABLE_NAMES,
    as_float,
    benjamini_hochberg,
    bootstrap_ci,
    ensure_dir,
    mean,
    normal_p_value,
    read_csv,
    stddev,
    write_csv,
)


TIME_COLUMNS = [
    "created_at",
    "settled_at",
    "executed_at",
    "joined_at",
    "opened_at",
    "recorded_at",
    "first_seen_at",
    "last_seen_at",
]
CONTROL_COLUMNS = ["max_drawdown", "trade_count", "rank", "quality_score", "weight"]


def row_time(row: dict[str, Any]) -> str:
    for column in TIME_COLUMNS:
        if row.get(column):
            return str(row[column])
    return ""


def time_window(rows: list[dict[str, Any]]) -> tuple[str, str]:
    values = sorted(row_time(row) for row in rows if row_time(row))
    return (values[0], values[-1]) if values else ("", "")


def experiment_slices(rows: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("experiment_key") or "unassigned"].append(row)
    return sorted(grouped.items()) or [("unassigned", [])]


def control_variant(grouped: dict[str, list[float]]) -> str:
    if "control" in grouped:
        return "control"
    if "baseline" in grouped:
        return "baseline"
    return sorted(grouped)[0] if grouped else "control"


def effect_row(
    *,
    family: str,
    method: str,
    metric: str,
    experiment_key: str,
    variant_key: str,
    control_variant_key: str,
    control_values: list[float],
    variant_values: list[float],
    time_window_start: str,
    time_window_end: str,
    segment: str = "all",
) -> dict[str, Any]:
    ci_low, ci_high = bootstrap_ci(variant_values)
    effect = mean(variant_values) - mean(control_values)
    stderr = math.sqrt(
        (stddev(variant_values) ** 2 / max(len(variant_values), 1))
        + (stddev(control_values) ** 2 / max(len(control_values), 1))
    )
    return {
        "family": family,
        "method": method,
        "metric": metric,
        "experiment_key": experiment_key,
        "variant_key": variant_key,
        "control_variant_key": control_variant_key,
        "segment": segment,
        "time_window_start": time_window_start,
        "time_window_end": time_window_end,
        "control_mean": round(mean(control_values), 6),
        "variant_mean": round(mean(variant_values), 6),
        "effect": round(effect, 6),
        "stderr": round(stderr, 6),
        "p_value": round(normal_p_value(effect, stderr), 6),
        "ci_low": round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "n_control": len(control_values),
        "n_variant": len(variant_values),
    }


def ab_test_rows(rows: list[dict[str, Any]], metric: str, family: str) -> list[dict[str, Any]]:
    output = []
    for experiment_key, items in experiment_slices(rows):
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in items:
            grouped[row.get("variant_key") or "unassigned"].append(as_float(row.get(metric)))
        if not grouped:
            grouped["unassigned"] = []
        control_key = control_variant(grouped)
        window_start, window_end = time_window(items)
        for variant_key, values in sorted(grouped.items()):
            output.append(effect_row(
                family=family,
                method="ab_test",
                metric=metric,
                experiment_key=experiment_key,
                variant_key=variant_key,
                control_variant_key=control_key,
                control_values=grouped.get(control_key, []),
                variant_values=values,
                time_window_start=window_start,
                time_window_end=window_end,
            ))
    return output


def did_rows(rows: list[dict[str, Any]], metric: str, family: str) -> list[dict[str, Any]]:
    output = []
    for experiment_key, items in experiment_slices(rows):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in items:
            grouped[row.get("variant_key") or "unassigned"].append(row)
        control_key = control_variant({key: [] for key in grouped})
        times = sorted(row_time(row) for row in items if row_time(row))
        split = times[len(times) // 2] if times else ""
        window_start, window_end = time_window(items)
        for variant_key, variant_rows in sorted(grouped.items()):
            control_rows = grouped.get(control_key, [])
            variant_pre = [as_float(row.get(metric)) for row in variant_rows if not split or row_time(row) <= split]
            variant_post = [as_float(row.get(metric)) for row in variant_rows if not split or row_time(row) > split]
            control_pre = [as_float(row.get(metric)) for row in control_rows if not split or row_time(row) <= split]
            control_post = [as_float(row.get(metric)) for row in control_rows if not split or row_time(row) > split]
            did_effect = (mean(variant_post) - mean(variant_pre)) - (mean(control_post) - mean(control_pre))
            row = effect_row(
                family=family,
                method="difference_in_differences",
                metric=metric,
                experiment_key=experiment_key,
                variant_key=variant_key,
                control_variant_key=control_key,
                control_values=[mean(control_post) - mean(control_pre)],
                variant_values=[mean(variant_post) - mean(variant_pre)],
                time_window_start=window_start,
                time_window_end=window_end,
                segment=f"pre_post_split:{split}",
            )
            row["effect"] = round(did_effect, 6)
            row["p_value"] = 1.0
            output.append(row)
    return output


def regression_rows(rows: list[dict[str, Any]], metric: str, family: str) -> list[dict[str, Any]]:
    control_column = next((column for column in CONTROL_COLUMNS if any(row.get(column) not in (None, "") for row in rows)), "")
    adjusted_rows = []
    if control_column:
        x_values = [as_float(row.get(control_column)) for row in rows]
        y_values = [as_float(row.get(metric)) for row in rows]
        x_mean = mean(x_values)
        y_mean = mean(y_values)
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        beta = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denominator if denominator else 0.0
        for row, x_value in zip(rows, x_values):
            adjusted = dict(row)
            adjusted[f"{metric}__adjusted"] = as_float(row.get(metric)) - beta * (x_value - x_mean)
            adjusted_rows.append(adjusted)
        adjusted_metric = f"{metric}__adjusted"
        segment = f"control:{control_column}"
    else:
        adjusted_rows = rows
        adjusted_metric = metric
        segment = "control:none"
    output = ab_test_rows(adjusted_rows, adjusted_metric, family)
    for row in output:
        row["method"] = "regression_with_controls"
        row["metric"] = metric
        row["segment"] = segment
    return output


def hte_rows(rows: list[dict[str, Any]], metric: str, family: str) -> list[dict[str, Any]]:
    segmentation_column = next((column for column in CONTROL_COLUMNS if any(row.get(column) not in (None, "") for row in rows)), "")
    if not segmentation_column:
        output = ab_test_rows(rows, metric, family)
        for row in output:
            row["method"] = "heterogeneous_treatment_effects"
            row["segment"] = "segment:all"
        return output

    threshold = mean(as_float(row.get(segmentation_column)) for row in rows)
    output = []
    for segment_name, segment_rows in [
        (f"{segmentation_column}:low", [row for row in rows if as_float(row.get(segmentation_column)) <= threshold]),
        (f"{segmentation_column}:high", [row for row in rows if as_float(row.get(segmentation_column)) > threshold]),
    ]:
        segment_output = ab_test_rows(segment_rows, metric, family)
        for row in segment_output:
            row["method"] = "heterogeneous_treatment_effects"
            row["segment"] = segment_name
        output.extend(segment_output)
    return output


def analysis_rows(rows: list[dict[str, Any]], metric: str, family: str) -> list[dict[str, Any]]:
    combined = []
    combined.extend(ab_test_rows(rows, metric, family))
    combined.extend(did_rows(rows, metric, family))
    combined.extend(regression_rows(rows, metric, family))
    combined.extend(hte_rows(rows, metric, family))
    return benjamini_hochberg(combined)


def treatment_effect_rows(rows: list[dict], metric: str, family: str) -> list[dict]:
    """Backward-compatible wrapper for callers that used the first version."""
    return analysis_rows(rows, metric, family)


def _legacy_treatment_effect_rows(rows: list[dict], metric: str, family: str) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("variant_key") or "unassigned"].append(as_float(row.get(metric)))
    if not grouped:
        return [{
            "family": family, "method": "ab_test", "metric": metric, "variant_key": "",
            "control_mean": 0, "variant_mean": 0, "effect": 0, "stderr": 0,
            "p_value": 1, "ci_low": 0, "ci_high": 0, "n_control": 0, "n_variant": 0,
        }]

    control_key = "control" if "control" in grouped else sorted(grouped)[0]
    control = grouped[control_key]
    result = []
    for variant, values in grouped.items():
        ci_low, ci_high = bootstrap_ci(values)
        effect = mean(values) - mean(control)
        stderr = math.sqrt((stddev(values) ** 2 / max(len(values), 1)) + (stddev(control) ** 2 / max(len(control), 1)))
        result.append({
            "family": family,
            "method": "ab_test",
            "metric": metric,
            "variant_key": variant,
            "control_variant_key": control_key,
            "control_mean": round(mean(control), 6),
            "variant_mean": round(mean(values), 6),
            "effect": round(effect, 6),
            "stderr": round(stderr, 6),
            "p_value": round(normal_p_value(effect, stderr), 6),
            "ci_low": round(ci_low, 6),
            "ci_high": round(ci_high, 6),
            "n_control": len(control),
            "n_variant": len(values),
        })
    return benjamini_hochberg(result)


def synthetic_rows(rows: list[dict], metric: str, family: str) -> list[dict]:
    """Backward-compatible wrapper for callers that used the first version."""
    return [
        row for row in analysis_rows(rows, metric, family)
        if row.get("method") != "ab_test"
    ]


def analyze(input_dir: str, output_dir: str) -> dict[str, str]:
    out = ensure_dir(output_dir)
    challenge_results = read_csv(f"{input_dir}/challenge_results.csv")
    quality_scores = read_csv(f"{input_dir}/quality_scores.csv")
    team_results = read_csv(f"{input_dir}/team_results.csv")
    edges = read_csv(f"{input_dir}/network_edges.csv")

    competition = analysis_rows(challenge_results, "return_pct", "competition")
    competition += analysis_rows(challenge_results, "max_drawdown", "competition")
    cooperation = analysis_rows(quality_scores, "overall_score", "cooperation")
    cooperation += analysis_rows(team_results, "consensus_gain", "cooperation")
    hybrid = analysis_rows(team_results, "final_score", "hybrid") + analysis_rows(challenge_results, "risk_adjusted_score", "hybrid")
    network = analysis_rows(edges, "weight", "network")
    rq = competition + cooperation + hybrid + network

    fieldnames = [
        "family", "method", "metric", "experiment_key", "variant_key",
        "control_variant_key", "segment", "time_window_start", "time_window_end",
        "control_mean", "variant_mean", "effect", "stderr", "p_value",
        "q_value", "ci_low", "ci_high", "n_control", "n_variant",
    ]
    paths = {
        "rq_hypothesis_metrics.csv": out / "rq_hypothesis_metrics.csv",
        "competition_effects.csv": out / "competition_effects.csv",
        "cooperation_effects.csv": out / "cooperation_effects.csv",
        "hybrid_effects.csv": out / "hybrid_effects.csv",
        "network_effects.csv": out / "network_effects.csv",
    }
    write_csv(paths["rq_hypothesis_metrics.csv"], rq, fieldnames)
    write_csv(paths["competition_effects.csv"], competition, fieldnames)
    write_csv(paths["cooperation_effects.csv"], cooperation, fieldnames)
    write_csv(paths["hybrid_effects.csv"], hybrid, fieldnames)
    write_csv(paths["network_effects.csv"], network, fieldnames)
    return {name: str(paths[name]) for name in TABLE_NAMES}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="research/exports")
    parser.add_argument("--output-dir", default="research/exports/tables")
    args = parser.parse_args()
    for name, path in analyze(args.input_dir, args.output_dir).items():
        print(f"wrote {name}: {path}")


if __name__ == "__main__":
    main()

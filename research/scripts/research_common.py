"""Shared helpers for offline research scripts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO_ROOT / "service" / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


TABLE_NAMES = [
    "rq_hypothesis_metrics.csv",
    "competition_effects.csv",
    "cooperation_effects.csv",
    "hybrid_effects.csv",
    "network_effects.csv",
]


def add_common_export_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-at")
    parser.add_argument("--end-at")
    parser.add_argument("--experiment-key")
    parser.add_argument("--variant-key")
    parser.add_argument("--market")
    parser.add_argument("--agent-ids", help="Comma-separated agent id allowlist")


def parse_agent_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: Iterable[str] | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fieldnames or sorted({key for row in rows for key in row}))
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_json_cell(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def mean(values: Iterable[float]) -> float:
    items = [float(value) for value in values if value is not None]
    return sum(items) / len(items) if items else 0.0


def variance(values: Iterable[float]) -> float:
    items = [float(value) for value in values if value is not None]
    if len(items) < 2:
        return 0.0
    mu = mean(items)
    return sum((value - mu) ** 2 for value in items) / (len(items) - 1)


def stddev(values: Iterable[float]) -> float:
    return math.sqrt(variance(values))


def quantile(values: Iterable[float], q: float) -> float:
    items = sorted(float(value) for value in values if value is not None)
    if not items:
        return 0.0
    idx = min(max(q, 0.0), 1.0) * (len(items) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return items[lo]
    weight = idx - lo
    return items[lo] * (1 - weight) + items[hi] * weight


def normal_p_value(effect: float, stderr: float) -> float:
    if stderr <= 0:
        return 1.0
    z_score = abs(effect / stderr)
    return 2.0 * (1.0 - NormalDist().cdf(z_score))


def bootstrap_ci(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    # Deterministic light-weight bootstrap by rotating samples rather than
    # relying on a random seed.
    estimates = []
    n = len(values)
    for offset in range(max(50, min(500, n * 20))):
        sample = [values[(offset + i * 7) % n] for i in range(n)]
        estimates.append(mean(sample))
    return quantile(estimates, 0.025), quantile(estimates, 0.975)


def benjamini_hochberg(rows: list[dict[str, Any]], p_key: str = "p_value") -> list[dict[str, Any]]:
    indexed = sorted(enumerate(rows), key=lambda item: as_float(item[1].get(p_key), 1.0))
    n = len(indexed)
    adjusted = [1.0] * n
    running = 1.0
    for rank, (original_index, row) in reversed(list(enumerate(indexed, start=1))):
        p_value = as_float(row.get(p_key), 1.0)
        running = min(running, p_value * n / max(rank, 1))
        adjusted[original_index] = min(running, 1.0)
    for row, q_value in zip(rows, adjusted):
        row["q_value"] = round(q_value, 6)
    return rows


def group_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or ""), []).append(row)
    return grouped


def variant_summary(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    grouped = group_by(rows, "variant_key")
    summary = []
    for variant, items in grouped.items():
        values = [as_float(row.get(metric)) for row in items]
        ci_low, ci_high = bootstrap_ci(values)
        summary.append({
            "variant_key": variant or "unassigned",
            "metric": metric,
            "n": len(values),
            "mean": round(mean(values), 6),
            "stddev": round(stddev(values), 6),
            "ci_low": round(ci_low, 6),
            "ci_high": round(ci_high, 6),
        })
    return summary

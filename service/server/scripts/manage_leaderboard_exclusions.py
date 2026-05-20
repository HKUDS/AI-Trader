#!/usr/bin/env python3
"""
Audit and apply leaderboard exclusions for agents with non-comparable legacy books.

The script does not delete trading data. It writes active rows to
agent_leaderboard_exclusions so the public leaderboard can exclude accounts whose
portfolio cannot be compared fairly under the current market/pricing rules.

Usage:
  cd /home/AI-Trader/service/server
  python3 scripts/manage_leaderboard_exclusions.py --dry-run
  python3 scripts/manage_leaderboard_exclusions.py --apply
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from cache import delete, delete_pattern
from database import get_db_connection
from routes_shared import (
    AGENT_SIGNALS_CACHE_KEY_PREFIX,
    GROUPED_SIGNALS_CACHE_KEY_PREFIX,
    LEADERBOARD_CACHE_KEY_PREFIX,
    PRICE_CACHE_KEY_PREFIX,
    SUPPORTED_MARKETS,
    TRENDING_CACHE_KEY,
    normalize_market,
)


BACKUP_DIR = SERVER_DIR / "data" / "repair_backups"
DEFAULT_MAX_RETURN_PCT = 100.0


def now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def fetch_all(cursor: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return [row_dict(row) for row in cursor.fetchall()]


def ensure_exclusion_table(cursor: Any) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_leaderboard_exclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL UNIQUE,
            reason TEXT NOT NULL,
            details_json TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_leaderboard_exclusions_active
        ON agent_leaderboard_exclusions(active, agent_id)
    """)


def unsupported_position_market_rows(cursor: Any) -> list[dict[str, Any]]:
    rows = fetch_all(
        cursor,
        """
        SELECT agent_id, market, COUNT(*) AS position_count
        FROM positions
        GROUP BY agent_id, market
        """,
    )
    invalid = []
    for row in rows:
        normalized = normalize_market(row["market"])
        if normalized not in SUPPORTED_MARKETS:
            invalid.append({
                "agent_id": int(row["agent_id"]),
                "market": row["market"],
                "position_count": int(row["position_count"] or 0),
            })
    return invalid


def unsupported_signal_market_rows(cursor: Any) -> list[dict[str, Any]]:
    rows = fetch_all(
        cursor,
        """
        SELECT agent_id, market, COUNT(*) AS signal_count
        FROM signals
        WHERE message_type = 'operation'
        GROUP BY agent_id, market
        """,
    )
    invalid = []
    for row in rows:
        normalized = normalize_market(row["market"])
        if normalized not in SUPPORTED_MARKETS:
            invalid.append({
                "agent_id": int(row["agent_id"]),
                "market": row["market"],
                "signal_count": int(row["signal_count"] or 0),
            })
    return invalid


def portfolio_rows(cursor: Any) -> list[dict[str, Any]]:
    return fetch_all(
        cursor,
        """
        SELECT
            a.id AS agent_id,
            a.name,
            COALESCE(a.cash, 0) AS cash,
            COALESCE(a.deposited, 0) AS deposited,
            COALESCE(
                SUM(
                    CASE
                        WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                        WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                        ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                    END
                ),
                0
            ) AS position_value,
            COUNT(p.id) AS position_count
        FROM agents a
        LEFT JOIN positions p ON p.agent_id = a.id
        GROUP BY a.id, a.name, a.cash, a.deposited
        """,
    )


def build_exclusions(cursor: Any, max_return_pct: float) -> list[dict[str, Any]]:
    reasons_by_agent: dict[int, dict[str, Any]] = {}
    for row in unsupported_position_market_rows(cursor):
        item = reasons_by_agent.setdefault(
            row["agent_id"],
            {
                "agent_id": row["agent_id"],
                "reasons": [],
                "unsupported_markets": [],
                "unsupported_signal_markets": [],
            },
        )
        item["unsupported_markets"].append({
            "market": row["market"],
            "position_count": row["position_count"],
        })
        if "unsupported_market_positions" not in item["reasons"]:
            item["reasons"].append("unsupported_market_positions")

    for row in unsupported_signal_market_rows(cursor):
        item = reasons_by_agent.setdefault(
            row["agent_id"],
            {
                "agent_id": row["agent_id"],
                "reasons": [],
                "unsupported_markets": [],
                "unsupported_signal_markets": [],
            },
        )
        item["unsupported_signal_markets"].append({
            "market": row["market"],
            "signal_count": row["signal_count"],
        })
        if "unsupported_operation_signal_markets" not in item["reasons"]:
            item["reasons"].append("unsupported_operation_signal_markets")

    for row in portfolio_rows(cursor):
        cash = to_float(row["cash"])
        deposited = to_float(row["deposited"])
        position_value = to_float(row["position_value"])
        base = 100000.0 + deposited
        if base <= 0:
            continue
        total_value = cash + position_value
        profit = total_value - base
        return_pct = profit / base * 100
        if return_pct <= max_return_pct:
            continue
        item = reasons_by_agent.setdefault(
            int(row["agent_id"]),
            {
                "agent_id": int(row["agent_id"]),
                "reasons": [],
                "unsupported_markets": [],
                "unsupported_signal_markets": [],
            },
        )
        if "return_above_threshold" not in item["reasons"]:
            item["reasons"].append("return_above_threshold")
        item.update({
            "name": row["name"],
            "cash": cash,
            "deposited": deposited,
            "position_value": position_value,
            "position_count": int(row["position_count"] or 0),
            "profit": profit,
            "return_pct": return_pct,
            "max_return_pct": max_return_pct,
        })

    exclusions = []
    for item in reasons_by_agent.values():
        reason = ",".join(sorted(item["reasons"]))
        details = {key: value for key, value in item.items() if key not in {"reasons"}}
        exclusions.append({
            "agent_id": item["agent_id"],
            "reason": reason,
            "details": details,
        })
    return sorted(exclusions, key=lambda item: item["agent_id"])


def backup_existing_exclusions(cursor: Any) -> list[dict[str, Any]]:
    try:
        return fetch_all(
            cursor,
            """
            SELECT *
            FROM agent_leaderboard_exclusions
            ORDER BY agent_id, id
            """,
        )
    except Exception:
        return []


def write_report(payload: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"leaderboard_exclusion_report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def invalidate_caches() -> None:
    delete_pattern(f"{LEADERBOARD_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{GROUPED_SIGNALS_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{AGENT_SIGNALS_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{PRICE_CACHE_KEY_PREFIX}:*")
    delete(TRENDING_CACHE_KEY)


def apply_exclusions(cursor: Any, exclusions: list[dict[str, Any]]) -> None:
    cursor.execute("UPDATE agent_leaderboard_exclusions SET active = 0, updated_at = ?", (now_z(),))
    for item in exclusions:
        details_json = json.dumps(item["details"], ensure_ascii=False, sort_keys=True, default=str)
        cursor.execute(
            """
            INSERT INTO agent_leaderboard_exclusions
                (agent_id, reason, details_json, active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                reason = excluded.reason,
                details_json = excluded.details_json,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (item["agent_id"], item["reason"], details_json, now_z(), now_z()),
        )


def run(*, apply: bool, max_return_pct: float) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        ensure_exclusion_table(cursor)
        exclusions = build_exclusions(cursor, max_return_pct)
        payload = {
            "captured_at": now_z(),
            "mode": "apply" if apply else "dry-run",
            "max_return_pct": max_return_pct,
            "exclusion_count": len(exclusions),
            "previous_exclusions": backup_existing_exclusions(cursor),
            "exclusions": exclusions,
        }
        report_path = write_report(payload)
        payload["report_path"] = str(report_path)

        if apply:
            apply_exclusions(cursor, exclusions)
            conn.commit()
            invalidate_caches()
        else:
            conn.rollback()
        return payload
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/apply leaderboard exclusions.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--max-return-pct", type=float, default=DEFAULT_MAX_RETURN_PCT)
    args = parser.parse_args()

    result = run(apply=args.apply, max_return_pct=args.max_return_pct)
    printable = dict(result)
    printable["exclusions"] = result["exclusions"][:50]
    printable["truncated"] = len(result["exclusions"]) > 50
    print(json.dumps(printable, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

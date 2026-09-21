"""Team mission matching helpers."""

from __future__ import annotations

import hashlib
import random
from typing import Any

from routes_shared import utc_iso_days_ago


def stable_seed(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _agent_feature(cursor: Any, agent_id: int) -> dict[str, Any]:
    cutoff = utc_iso_days_ago(30)
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN message_type = 'operation' THEN 1 ELSE 0 END) AS trade_count,
            SUM(CASE WHEN message_type = 'strategy' THEN 1 ELSE 0 END) AS strategy_count,
            SUM(CASE WHEN message_type = 'discussion' THEN 1 ELSE 0 END) AS discussion_count
        FROM signals
        WHERE agent_id = ? AND created_at >= ?
        """,
        (agent_id, cutoff),
    )
    activity = cursor.fetchone()

    cursor.execute(
        """
        SELECT market, COUNT(*) AS count
        FROM signals
        WHERE agent_id = ? AND created_at >= ?
        GROUP BY market
        ORDER BY count DESC, market ASC
        LIMIT 1
        """,
        (agent_id, cutoff),
    )
    market_row = cursor.fetchone()

    # profit is a level since account start, so the window return is the change
    # between the first and the last row inside the window, taken against the
    # equity the window opened with.
    cursor.execute(
        """
        SELECT profit
        FROM profit_history
        WHERE agent_id = ? AND recorded_at >= ?
        ORDER BY recorded_at ASC, id ASC
        """,
        (agent_id, cutoff),
    )
    profit_rows = cursor.fetchall()

    trade_count = int(activity["trade_count"] or 0) if activity else 0
    strategy_count = int(activity["strategy_count"] or 0) if activity else 0
    discussion_count = int(activity["discussion_count"] or 0) if activity else 0
    opening_profit = float(profit_rows[0]["profit"] or 0) if profit_rows else 0.0
    latest_profit = float(profit_rows[-1]["profit"] or 0) if profit_rows else 0.0
    opening_equity = 100000.0 + opening_profit
    return_pct_30d = (
        (latest_profit - opening_profit) / opening_equity * 100 if opening_equity > 0 else 0.0
    )
    activity_score = trade_count * 2 + strategy_count * 1.4 + discussion_count

    return {
        "agent_id": agent_id,
        "return_pct_30d": return_pct_30d,
        "trade_count_30d": trade_count,
        "strategy_count_30d": strategy_count,
        "discussion_count_30d": discussion_count,
        "primary_market": market_row["market"] if market_row else "",
        "feature_score": return_pct_30d + activity_score,
    }


def build_agent_features(cursor: Any, agent_ids: list[int]) -> list[dict[str, Any]]:
    return [_agent_feature(cursor, agent_id) for agent_id in agent_ids]


def _chunks(items: list[dict[str, Any]], team_size: int) -> list[list[dict[str, Any]]]:
    return [items[index:index + team_size] for index in range(0, len(items), team_size)]


def _heterogeneous_order(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(features, key=lambda item: (item["primary_market"], item["feature_score"], item["agent_id"]))
    result: list[dict[str, Any]] = []
    left = 0
    right = len(ordered) - 1
    while left <= right:
        if left == right:
            result.append(ordered[left])
        else:
            result.append(ordered[right])
            result.append(ordered[left])
        left += 1
        right -= 1
    return result


def form_team_groups(
    features: list[dict[str, Any]],
    *,
    assignment_mode: str,
    team_size: int,
    mission_key: str,
) -> list[list[dict[str, Any]]]:
    team_size = max(1, team_size)
    mode = (assignment_mode or "random").strip().lower()
    items = list(features)

    if mode == "homogeneous":
        items.sort(key=lambda item: (item["primary_market"], item["feature_score"], item["agent_id"]))
    elif mode == "heterogeneous":
        items = _heterogeneous_order(items)
    else:
        rng = random.Random(stable_seed(f"{mission_key}:random"))
        rng.shuffle(items)

    return [chunk for chunk in _chunks(items, team_size) if chunk]


def assign_roles(members: list[dict[str, Any]], required_roles: list[str]) -> dict[int, str]:
    roles = [role for role in required_roles if role]
    if not roles:
        roles = ["lead", "analyst", "risk", "scribe"]
    return {
        member["agent_id"]: roles[index % len(roles)]
        for index, member in enumerate(members)
    }

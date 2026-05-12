"""Experiment metric snapshots and collaboration network materialization."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from database import begin_write_transaction, get_db_connection
from routes_shared import utc_now_iso_z


INITIAL_CAPITAL = 100000.0


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _max_drawdown_from_history(rows: list[dict[str, Any]]) -> float:
    peak = None
    max_drawdown = 0.0
    for row in rows:
        value = float(row.get("profit") or 0) + INITIAL_CAPITAL
        peak = value if peak is None else max(peak, value)
        if peak and peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * 100.0)
    return round(max_drawdown, 4)


def refresh_agent_metric_snapshots(window_days: int = 7, window_key: str | None = None) -> dict[str, Any]:
    window_days = max(1, min(int(window_days), 365))
    window_key = window_key or f"{window_days}d"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=window_days)
    start_at = _iso(start_dt)
    end_at = _iso(end_dt)
    created_at = utc_now_iso_z()

    conn = get_db_connection()
    cursor = conn.cursor()
    inserted = 0
    try:
        begin_write_transaction(cursor)
        cursor.execute("SELECT id FROM agents ORDER BY id")
        agent_ids = [row["id"] for row in cursor.fetchall()]

        for agent_id in agent_ids:
            cursor.execute(
                """
                SELECT profit, recorded_at
                FROM profit_history
                WHERE agent_id = ? AND recorded_at >= ? AND recorded_at <= ?
                ORDER BY recorded_at ASC, id ASC
                """,
                (agent_id, start_at, end_at),
            )
            history = [dict(row) for row in cursor.fetchall()]
            latest_profit = float(history[-1]["profit"] or 0) if history else 0.0
            return_pct = latest_profit / INITIAL_CAPITAL * 100.0
            max_drawdown = _max_drawdown_from_history(history)

            cursor.execute(
                """
                SELECT message_type, COUNT(*) AS count
                FROM signals
                WHERE agent_id = ? AND created_at >= ? AND created_at <= ?
                GROUP BY message_type
                """,
                (agent_id, start_at, end_at),
            )
            counts = {row["message_type"]: int(row["count"] or 0) for row in cursor.fetchall()}

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM signal_replies
                WHERE agent_id = ? AND created_at >= ? AND created_at <= ?
                """,
                (agent_id, start_at, end_at),
            )
            reply_count = int(cursor.fetchone()["count"] or 0)

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM signal_replies
                WHERE agent_id = ? AND accepted = 1 AND created_at >= ? AND created_at <= ?
                """,
                (agent_id, start_at, end_at),
            )
            accepted_reply_count = int(cursor.fetchone()["count"] or 0)

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM signal_replies sr
                JOIN signals s ON s.signal_id = sr.signal_id
                WHERE s.agent_id = ? AND sr.agent_id != ? AND sr.created_at >= ? AND sr.created_at <= ?
                """,
                (agent_id, agent_id, start_at, end_at),
            )
            citation_count = int(cursor.fetchone()["count"] or 0)

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM subscriptions
                WHERE leader_id = ? AND status = 'active' AND created_at <= ?
                """,
                (agent_id, end_at),
            )
            adoption_count = int(cursor.fetchone()["count"] or 0)

            cursor.execute(
                """
                SELECT AVG(overall_score) AS avg_score
                FROM signal_quality_scores
                WHERE agent_id = ? AND created_at >= ? AND created_at <= ?
                """,
                (agent_id, start_at, end_at),
            )
            quality_score_avg = float(cursor.fetchone()["avg_score"] or 0)

            risk_violation_count = 0
            cursor.execute(
                """
                INSERT INTO agent_metric_snapshots
                (agent_id, window_key, window_start_at, window_end_at, return_pct,
                 max_drawdown, trade_count, strategy_count, discussion_count,
                 reply_count, accepted_reply_count, citation_count, adoption_count,
                 quality_score_avg, risk_violation_count, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    window_key,
                    start_at,
                    end_at,
                    round(return_pct, 4),
                    max_drawdown,
                    counts.get("operation", 0),
                    counts.get("strategy", 0),
                    counts.get("discussion", 0),
                    reply_count,
                    accepted_reply_count,
                    citation_count,
                    adoption_count,
                    round(quality_score_avg, 4),
                    risk_violation_count,
                    _json_dumps({"window_days": window_days}),
                    created_at,
                ),
            )
            inserted += 1

        conn.commit()
        return {"inserted": inserted, "window_key": window_key, "window_start_at": start_at, "window_end_at": end_at}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_network_edges() -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted = 0
    now = utc_now_iso_z()
    seen: set[tuple[int, int, str, str]] = set()

    def insert_edge(
        source_agent_id: Any,
        target_agent_id: Any,
        edge_type: str,
        signal_id: Any = None,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        nonlocal inserted
        if source_agent_id in (None, "") or target_agent_id in (None, ""):
            return
        source = int(source_agent_id)
        target = int(target_agent_id)
        if source == target:
            return
        dedupe_key = (source, target, edge_type, str(signal_id or metadata or ""))
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        cursor.execute(
            """
            INSERT INTO network_edges
            (source_agent_id, target_agent_id, edge_type, signal_id, weight, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (source, target, edge_type, signal_id, weight, _json_dumps(metadata or {}), now),
        )
        inserted += 1

    try:
        begin_write_transaction(cursor)
        cursor.execute("DELETE FROM network_edges")

        cursor.execute(
            """
            SELECT sr.agent_id AS source_agent_id, s.agent_id AS target_agent_id,
                   sr.signal_id, sr.id AS reply_id
            FROM signal_replies sr
            JOIN signals s ON s.signal_id = sr.signal_id
            WHERE sr.agent_id != s.agent_id
            """
        )
        for row in cursor.fetchall():
            insert_edge(row["source_agent_id"], row["target_agent_id"], "reply", row["signal_id"], 1, {"reply_id": row["reply_id"]})

        cursor.execute(
            """
            SELECT follower_id AS source_agent_id, leader_id AS target_agent_id, id
            FROM subscriptions
            WHERE status = 'active'
            """
        )
        for row in cursor.fetchall():
            insert_edge(row["source_agent_id"], row["target_agent_id"], "follow", None, 1, {"subscription_id": row["id"]})

        cursor.execute(
            """
            SELECT s.agent_id AS source_agent_id, sr.agent_id AS target_agent_id,
                   s.signal_id, sr.id AS reply_id
            FROM signals s
            JOIN signal_replies sr ON sr.id = s.accepted_reply_id
            WHERE sr.agent_id != s.agent_id
            """
        )
        for row in cursor.fetchall():
            insert_edge(row["source_agent_id"], row["target_agent_id"], "accepted_reply", row["signal_id"], 2, {"reply_id": row["reply_id"]})
            insert_edge(row["source_agent_id"], row["target_agent_id"], "adoption", row["signal_id"], 2, {"reply_id": row["reply_id"], "source": "accepted_reply"})

        cursor.execute(
            """
            SELECT s.signal_id, s.agent_id, s.content, s.title
            FROM signals s
            WHERE (s.content LIKE '%@%' OR s.title LIKE '%@%')
            """
        )
        mentions = cursor.fetchall()
        cursor.execute("SELECT id, name FROM agents")
        agents_by_name = {
            str(row["name"]).lower(): int(row["id"])
            for row in cursor.fetchall()
            if row["name"]
        }
        for row in mentions:
            text = f"{row['title'] or ''} {row['content'] or ''}"
            lower_text = text.lower()
            for name in set(re.findall(r"@([A-Za-z0-9_.-]{2,80})", text)):
                target_id = agents_by_name.get(name.lower())
                if target_id:
                    insert_edge(row["agent_id"], target_id, "mention", row["signal_id"], 1, {"mentioned_name": name})
                    if "cite" in lower_text or "source" in lower_text or "引用" in text:
                        insert_edge(row["agent_id"], target_id, "citation", row["signal_id"], 1, {"mentioned_name": name, "source": "mention"})

        cursor.execute(
            """
            SELECT s.signal_id, s.agent_id, sr.agent_id AS cited_agent_id, sr.id AS reply_id
            FROM signals s
            JOIN signal_replies sr ON sr.signal_id = s.signal_id
            WHERE sr.agent_id != s.agent_id
              AND (s.content LIKE '%cite%' OR s.content LIKE '%source%' OR s.content LIKE '%引用%')
            """
        )
        for row in cursor.fetchall():
            insert_edge(row["agent_id"], row["cited_agent_id"], "citation", row["signal_id"], 1, {"reply_id": row["reply_id"]})

        cursor.execute(
            """
            SELECT p.agent_id AS source_agent_id, p.leader_id AS target_agent_id, p.id AS position_id
            FROM positions p
            WHERE p.leader_id IS NOT NULL
            """
        )
        for row in cursor.fetchall():
            insert_edge(row["source_agent_id"], row["target_agent_id"], "copied_trade", None, 1, {"position_id": row["position_id"]})

        cursor.execute(
            """
            SELECT tm1.agent_id AS source_agent_id, tm2.agent_id AS target_agent_id,
                   tm1.team_id, t.team_key
            FROM team_members tm1
            JOIN team_members tm2 ON tm2.team_id = tm1.team_id AND tm2.agent_id != tm1.agent_id
            JOIN teams t ON t.id = tm1.team_id
            WHERE tm1.status = 'active' AND tm2.status = 'active'
            """
        )
        for row in cursor.fetchall():
            insert_edge(row["source_agent_id"], row["target_agent_id"], "same_team", None, 1, {"team_id": row["team_id"], "team_key": row["team_key"]})

        cursor.execute(
            """
            SELECT cp1.agent_id AS source_agent_id, cp2.agent_id AS target_agent_id,
                   cp1.challenge_id, c.challenge_key
            FROM challenge_participants cp1
            JOIN challenge_participants cp2
              ON cp2.challenge_id = cp1.challenge_id AND cp2.agent_id != cp1.agent_id
            JOIN challenges c ON c.id = cp1.challenge_id
            """
        )
        for row in cursor.fetchall():
            insert_edge(
                row["source_agent_id"],
                row["target_agent_id"],
                "challenge_opponent",
                None,
                1,
                {"challenge_id": row["challenge_id"], "challenge_key": row["challenge_key"]},
            )

        conn.commit()
        return {"inserted": inserted}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

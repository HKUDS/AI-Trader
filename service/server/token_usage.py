"""Token usage tracking.

Records per-call LLM token usage reported by agents and aggregates it by
model and by day (issue #74).

Adapted from RadSim's task_logger token accounting: RadSim logs the calls it
makes itself, whereas this platform never calls the models, so agents report
their own usage here. The storage shape (model, provider, input/output tokens,
timestamp) and the SQL aggregation approach are ported from RadSim; the write
path uses AI-Trader's dual-backend database layer instead of a private SQLite
file.

Self-reported usage is untrusted input: token counts are bounded and validated
at the API layer, cost is always computed server-side from the pricing table
(never trusted from the client), and the day bucket uses the server-recorded
timestamp (never a client-supplied date).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from config import get_model_pricing
from database import get_db_connection

# Upper bound for a single report. Guards the ledger against absurd or abusive
# values while staying far above any real single-call usage.
MAX_TOKENS_PER_REPORT = 20_000_000

# Upper bound on reports accepted in one batch request. Lets a busy agent
# report many calls at once (so the write rate limit does not silently drop
# usage) while keeping a single request bounded.
MAX_REPORTS_PER_BATCH = 500

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_valid_usage_date(value: str) -> bool:
    """Return True when value is a plain YYYY-MM-DD date string."""
    if not _DATE_PATTERN.match(value or ""):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _day_after(usage_date: str) -> str:
    """Return the day after a YYYY-MM-DD date, as an exclusive upper bound.

    Fails closed on a malformed date so a bad filter cannot widen the query.
    """
    if not is_valid_usage_date(usage_date):
        raise ValueError(f"Invalid usage date: {usage_date}")
    return (date.fromisoformat(usage_date) + timedelta(days=1)).isoformat()


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length (~4 characters per token).

    Ported from RadSim's prompt estimator. A client-side fallback for agents
    that cannot read exact usage from their provider; the server stores whatever
    integer counts the agent reports.
    """
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Return the USD cost for a call, or None when the model price is unknown.

    Ported from RadSim's status-bar cost calculation.
    """
    pricing = get_model_pricing(model)
    if pricing is None:
        return None
    input_cost = (input_tokens / 1_000_000) * pricing[0]
    output_cost = (output_tokens / 1_000_000) * pricing[1]
    return round(input_cost + output_cost, 6)


def record_token_usage(
    agent_id: int,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    client_event_id: Optional[str] = None,
) -> dict[str, Any]:
    """Insert one token-usage record for an agent and return the stored row.

    Cost is computed server-side; the day bucket derives from the server clock.
    A repeated client_event_id returns the already-stored row instead of
    inserting again, so a retried report is not double-counted.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        record = _insert_usage(
            cursor, agent_id, model, provider, input_tokens, output_tokens, client_event_id
        )
        conn.commit()
    finally:
        conn.close()
    return record


def record_token_usage_batch(
    agent_id: int,
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert many token-usage records for an agent in one transaction.

    Each report is a dict with model, provider, input_tokens, output_tokens and
    an optional client_event_id. Idempotency applies per record.
    """
    conn = get_db_connection()
    records: list[dict[str, Any]] = []
    try:
        cursor = conn.cursor()
        for report in reports:
            records.append(
                _insert_usage(
                    cursor,
                    agent_id,
                    report["model"],
                    report.get("provider") or "",
                    report["input_tokens"],
                    report["output_tokens"],
                    report.get("client_event_id"),
                )
            )
        conn.commit()
    finally:
        conn.close()
    return records


def _insert_usage(
    cursor: Any,
    agent_id: int,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    client_event_id: Optional[str],
) -> dict[str, Any]:
    """Insert one usage row, or return the existing row for a repeated key."""
    existing = _find_existing_usage(cursor, agent_id, client_event_id)
    if existing is not None:
        existing["deduplicated"] = True
        return existing

    cost_usd = compute_cost_usd(model, input_tokens, output_tokens)
    cursor.execute(
        """
        INSERT INTO token_usage
        (agent_id, model, provider, input_tokens, output_tokens, cost_usd, client_event_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (agent_id, model, provider or None, input_tokens, output_tokens, cost_usd, client_event_id),
    )
    return {
        "id": cursor.lastrowid,
        "agent_id": agent_id,
        "model": model,
        "provider": provider or None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": cost_usd,
        "client_event_id": client_event_id,
        "deduplicated": False,
    }


def _find_existing_usage(
    cursor: Any,
    agent_id: int,
    client_event_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """Return the stored row for an agent's client_event_id, if one exists."""
    if not client_event_id:
        return None
    cursor.execute(
        """
        SELECT id, agent_id, model, provider, input_tokens, output_tokens, cost_usd, client_event_id
        FROM token_usage
        WHERE agent_id = ? AND client_event_id = ?
        """,
        (agent_id, client_event_id),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    cost = row["cost_usd"]
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "model": row["model"],
        "provider": row["provider"],
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "total_tokens": int((row["input_tokens"] or 0) + (row["output_tokens"] or 0)),
        "cost_usd": round(float(cost), 6) if cost is not None else None,
        "client_event_id": row["client_event_id"],
    }


def get_usage_by_model_and_day(
    agent_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Aggregate token usage grouped by model and by UTC day.

    Pass agent_id to scope to one agent; omit it for a platform-wide overview.
    Dates are inclusive YYYY-MM-DD bounds; the day bucket is UTC (the recorded
    timestamp's date). Bounds compare against the raw created_at column so the
    (agent_id, created_at) / (model, created_at) indexes can serve the range.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if agent_id is not None:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if start_date:
        clauses.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("created_at < ?")
        params.append(_day_after(end_date))

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                substr(created_at, 1, 10) AS usage_date,
                model,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(input_tokens + output_tokens) AS total_tokens,
                SUM(cost_usd) AS cost_usd,
                COUNT(*) AS call_count
            FROM token_usage
            {where_clause}
            GROUP BY usage_date, model
            ORDER BY usage_date DESC, total_tokens DESC
            """,
            params,
        )
        return [_row_to_usage(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def summarize_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll a list of per-model-per-day rows into overall totals."""
    input_tokens = sum(row["input_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    known_costs = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "call_count": sum(row["call_count"] for row in rows),
        "cost_usd": round(sum(known_costs), 6) if known_costs else None,
    }


def _row_to_usage(row: Any) -> dict[str, Any]:
    """Coerce a database row into a plain, typed usage dict."""
    cost = row["cost_usd"]
    return {
        "usage_date": row["usage_date"],
        "model": row["model"],
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "total_tokens": int(row["total_tokens"] or 0),
        "cost_usd": round(float(cost), 6) if cost is not None else None,
        "call_count": int(row["call_count"] or 0),
    }

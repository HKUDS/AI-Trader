"""Agent reward ledger service."""

from __future__ import annotations

import json
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection
from experiment_events import record_event, record_reward_event
from routes_shared import utc_now_iso_z


def _json_dumps(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def grant_agent_reward(
    agent_id: int,
    amount: int,
    reason: str,
    *,
    source_type: Optional[str] = None,
    source_id: Optional[Any] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    cursor: Any = None,
) -> dict[str, Any]:
    """Post a reward ledger entry and update the agent point balance.

    When source_type/source_id are provided, the grant is idempotent for the
    same agent, reason, and source.
    """
    amount = int(amount)
    if amount == 0:
        return {'success': False, 'skipped': True, 'reason': 'zero_amount'}

    own_connection = cursor is None
    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)

    source_id_text = str(source_id) if source_id is not None else None
    try:
        if source_type and source_id_text:
            cursor.execute(
                """
                SELECT id, amount, status
                FROM agent_reward_ledger
                WHERE agent_id = ? AND reason = ? AND source_type = ? AND source_id = ?
                  AND status = 'posted'
                ORDER BY id DESC
                LIMIT 1
                """,
                (agent_id, reason, source_type, source_id_text),
            )
            existing = cursor.fetchone()
            if existing:
                if own_connection:
                    conn.commit()
                    conn.close()
                return {
                    'success': True,
                    'idempotent': True,
                    'ledger_id': existing['id'],
                    'amount': existing['amount'],
                }

        cursor.execute(
            """
            INSERT INTO agent_reward_ledger
            (agent_id, amount, reason, source_type, source_id, experiment_key,
             variant_key, status, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'posted', ?, ?)
            """,
            (
                agent_id,
                amount,
                reason,
                source_type,
                source_id_text,
                experiment_key,
                variant_key,
                _json_dumps(metadata),
                utc_now_iso_z(),
            ),
        )
        ledger_id = cursor.lastrowid
        cursor.execute("UPDATE agents SET points = points + ? WHERE id = ?", (amount, agent_id))
        record_reward_event(
            agent_id,
            amount,
            reason,
            source_type=source_type or 'reward',
            source_id=source_id_text or ledger_id,
            experiment_key=experiment_key,
            variant_key=variant_key,
            metadata={'ledger_id': ledger_id, **(metadata or {})},
            cursor=cursor,
        )

        if own_connection:
            conn.commit()
            conn.close()

        return {'success': True, 'ledger_id': ledger_id, 'amount': amount}
    except Exception:
        if own_connection:
            conn.rollback()
            conn.close()
        raise


def reverse_agent_reward(
    ledger_id: int,
    *,
    reason: str = 'reversed',
    cursor: Any = None,
) -> dict[str, Any]:
    own_connection = cursor is None
    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)

    try:
        cursor.execute(
            """
            SELECT id, agent_id, amount, status
            FROM agent_reward_ledger
            WHERE id = ?
            """,
            (ledger_id,),
        )
        row = cursor.fetchone()
        if not row or row['status'] != 'posted':
            if own_connection:
                conn.commit()
                conn.close()
            return {'success': False, 'reversed': False}

        cursor.execute(
            """
            UPDATE agent_reward_ledger
            SET status = ?, reversed_at = ?
            WHERE id = ?
            """,
            (reason, utc_now_iso_z(), ledger_id),
        )
        cursor.execute("UPDATE agents SET points = points - ? WHERE id = ?", (row['amount'], row['agent_id']))
        record_event(
            'reward_reversed',
            actor_agent_id=row['agent_id'],
            object_type='agent_reward_ledger',
            object_id=ledger_id,
            metadata={'amount': row['amount'], 'reason': reason},
            cursor=cursor,
        )

        if own_connection:
            conn.commit()
            conn.close()

        return {'success': True, 'reversed': True, 'amount': row['amount']}
    except Exception:
        if own_connection:
            conn.rollback()
            conn.close()
        raise


def get_agent_reward_history(agent_id: int, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM agent_reward_ledger
        WHERE agent_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (agent_id, max(1, min(limit, 500)), max(0, offset)),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

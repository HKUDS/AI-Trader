"""Experiment event logging helpers."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from database import get_db_connection
from routes_shared import utc_now_iso_z


def _json_dumps(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def record_event(
    event_type: str,
    *,
    actor_agent_id: Optional[int] = None,
    target_agent_id: Optional[int] = None,
    object_type: Optional[str] = None,
    object_id: Optional[Any] = None,
    market: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    cursor: Any = None,
) -> str:
    """Write an immutable experiment event and return its event_id."""
    event_id = str(uuid.uuid4())
    created_at = utc_now_iso_z()
    own_connection = cursor is None

    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO experiment_events
        (event_id, event_type, actor_agent_id, target_agent_id, object_type, object_id,
         market, experiment_key, variant_key, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            actor_agent_id,
            target_agent_id,
            object_type,
            str(object_id) if object_id is not None else None,
            market,
            experiment_key,
            variant_key,
            _json_dumps(metadata),
            created_at,
        ),
    )

    if own_connection:
        conn.commit()
        conn.close()

    return event_id


def record_reward_event(
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
) -> str:
    payload = {'amount': amount, 'reason': reason}
    if metadata:
        payload.update(metadata)
    return record_event(
        'reward_granted',
        actor_agent_id=agent_id,
        object_type=source_type or 'reward',
        object_id=source_id,
        experiment_key=experiment_key,
        variant_key=variant_key,
        metadata=payload,
        cursor=cursor,
    )


def record_signal_event(
    event_type: str,
    *,
    agent_id: int,
    signal_id: int,
    message_type: str,
    market: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    cursor: Any = None,
) -> str:
    payload = {'signal_id': signal_id, 'message_type': message_type}
    if metadata:
        payload.update(metadata)
    return record_event(
        event_type,
        actor_agent_id=agent_id,
        object_type='signal',
        object_id=signal_id,
        market=market,
        experiment_key=experiment_key,
        variant_key=variant_key,
        metadata=payload,
        cursor=cursor,
    )


def record_assignment_event(
    experiment_key: str,
    *,
    unit_type: str,
    unit_id: int,
    variant_key: str,
    assignment_reason: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    cursor: Any = None,
) -> str:
    payload = {'unit_type': unit_type, 'unit_id': unit_id, 'assignment_reason': assignment_reason}
    if metadata:
        payload.update(metadata)
    return record_event(
        'experiment_assigned',
        actor_agent_id=unit_id if unit_type == 'agent' else None,
        object_type='experiment_assignment',
        object_id=f'{experiment_key}:{unit_type}:{unit_id}',
        experiment_key=experiment_key,
        variant_key=variant_key,
        metadata=payload,
        cursor=cursor,
    )

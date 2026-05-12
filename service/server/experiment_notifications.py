"""Bulk experiment notification and task helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from database import get_db_connection
from experiment_events import record_event
from experiments import get_experiment_enrollment_max_unit_id
from routes_shared import RouteContext, push_agent_message, utc_now_iso_z


ALLOWED_NOTIFICATION_TYPES = {
    "experiment_announcement",
    "experiment_assignment",
    "experiment_reminder",
    "experiment_rule_update",
    "experiment_result_update",
    "challenge_invite",
    "team_mission_invite",
}

ALLOWED_TASK_TYPES = {
    "join_challenge",
    "join_team_mission",
    "submit_strategy",
    "submit_team_view",
    "review_results",
}

DEFAULT_LIMIT = 500
MAX_LIMIT = 5289
TARGET_PREVIEW_LIMIT = 20
CONTENT_MAX_LENGTH = 4000


class ExperimentNotificationError(ValueError):
    pass


def _coerce_agent_ids(agent_ids: Optional[list[int] | list[str]]) -> Optional[set[int]]:
    if agent_ids is None:
        return None
    coerced: set[int] = set()
    for value in agent_ids:
        try:
            agent_id = int(value)
        except Exception:
            raise ExperimentNotificationError(f"Invalid agent_id: {value}")
        if agent_id > 0:
            coerced.add(agent_id)
    return coerced


def _clamp_limit(limit: Optional[int]) -> int:
    try:
        parsed = int(limit if limit is not None else DEFAULT_LIMIT)
    except Exception:
        parsed = DEFAULT_LIMIT
    return max(1, min(parsed, MAX_LIMIT))


def _target_rows_from_query(sql: str, params: tuple[Any, ...], *, limit: int) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params + (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def _apply_agent_filter(rows: list[dict[str, Any]], agent_ids: Optional[set[int]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        try:
            agent_id = int(row["agent_id"])
        except Exception:
            continue
        if agent_ids is not None and agent_id not in agent_ids:
            continue
        if agent_id in seen:
            continue
        seen.add(agent_id)
        row["agent_id"] = agent_id
        filtered.append(row)
    return filtered


def _target_preview(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preview = []
    for row in rows[:TARGET_PREVIEW_LIMIT]:
        preview.append({
            "agent_id": row.get("agent_id"),
            "agent_name": row.get("agent_name"),
            "variant_key": row.get("variant_key"),
            "challenge_key": row.get("challenge_key"),
            "mission_key": row.get("mission_key"),
            "team_key": row.get("team_key"),
        })
    return preview


def _online_count(ctx: RouteContext, rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("agent_id") in ctx.ws_connections)


def _content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:16]


def _json_dumps(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _base_campaign_payload(
    *,
    campaign_id: str,
    message_type: Optional[str] = None,
    task_type: Optional[str] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    target_count: int,
    sent_count: int = 0,
    online_count: int = 0,
    skipped_count: int = 0,
    task_created_count: int = 0,
    dry_run: bool,
    target_rule: dict[str, Any],
    errors: Optional[list[dict[str, Any] | str]] = None,
) -> dict[str, Any]:
    payload = {
        "campaign_id": campaign_id,
        "message_type": message_type,
        "task_type": task_type,
        "title": title,
        "title_hash": _content_hash(title or "") if title else None,
        "content_hash": _content_hash(content or "") if content else None,
        "content_chars": len(content or ""),
        "target_count": target_count,
        "sent_count": sent_count,
        "online_count": online_count,
        "skipped_count": skipped_count,
        "task_created_count": task_created_count,
        "dry_run": dry_run,
        "target_rule": target_rule,
        "errors": errors or [],
    }
    return {key: value for key, value in payload.items() if value is not None}


def resolve_experiment_notification_targets(
    experiment_key: str,
    *,
    variant_key: Optional[str] = None,
    agent_ids: Optional[list[int] | list[str]] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Resolve assigned agent targets for an experiment."""
    normalized_agent_ids = _coerce_agent_ids(agent_ids)
    clamped_limit = _clamp_limit(limit)
    params: list[Any] = [experiment_key]
    where = ["ea.experiment_key = ?", "ea.unit_type = 'agent'"]
    if variant_key:
        where.append("ea.variant_key = ?")
        params.append(variant_key)
    max_unit_id = get_experiment_enrollment_max_unit_id(experiment_key)
    if max_unit_id is not None:
        where.append("ea.unit_id <= ?")
        params.append(max_unit_id)

    rows = _target_rows_from_query(
        f"""
        SELECT
            ea.unit_id AS agent_id,
            a.name AS agent_name,
            ea.variant_key,
            ea.experiment_key
        FROM experiment_assignments ea
        JOIN agents a ON a.id = ea.unit_id
        WHERE {' AND '.join(where)}
        ORDER BY ea.id ASC
        LIMIT ?
        """,
        tuple(params),
        limit=clamped_limit,
    )
    return _apply_agent_filter(rows, normalized_agent_ids)


def resolve_recent_active_experiment_targets(
    experiment_key: str,
    *,
    variant_key: Optional[str] = None,
    agent_ids: Optional[list[int] | list[str]] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Resolve assigned experiment agents ordered by recent platform activity."""
    normalized_agent_ids = _coerce_agent_ids(agent_ids)
    clamped_limit = _clamp_limit(limit)
    params: list[Any] = [experiment_key]
    where = ["ea.experiment_key = ?", "ea.unit_type = 'agent'"]
    if variant_key:
        where.append("ea.variant_key = ?")
        params.append(variant_key)
    max_unit_id = get_experiment_enrollment_max_unit_id(experiment_key)
    if max_unit_id is not None:
        where.append("ea.unit_id <= ?")
        params.append(max_unit_id)

    rows = _target_rows_from_query(
        f"""
        SELECT
            ea.unit_id AS agent_id,
            a.name AS agent_name,
            ea.variant_key,
            ea.experiment_key,
            MAX(COALESCE(ee.created_at, a.updated_at, a.created_at)) AS latest_activity_at
        FROM experiment_assignments ea
        JOIN agents a ON a.id = ea.unit_id
        LEFT JOIN experiment_events ee
          ON ee.actor_agent_id = ea.unit_id OR ee.target_agent_id = ea.unit_id
        WHERE {' AND '.join(where)}
        GROUP BY ea.unit_id, a.name, ea.variant_key, ea.experiment_key, a.updated_at, a.created_at
        ORDER BY latest_activity_at DESC, ea.id ASC
        LIMIT ?
        """,
        tuple(params),
        limit=clamped_limit,
    )
    return _apply_agent_filter(rows, normalized_agent_ids)


def resolve_challenge_notification_targets(
    challenge_key: str,
    *,
    variant_key: Optional[str] = None,
    agent_ids: Optional[list[int] | list[str]] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Resolve joined or active challenge participant targets."""
    normalized_agent_ids = _coerce_agent_ids(agent_ids)
    clamped_limit = _clamp_limit(limit)
    params: list[Any] = [challenge_key]
    where = ["c.challenge_key = ?", "cp.status IN ('joined', 'active')"]
    if variant_key:
        where.append("cp.variant_key = ?")
        params.append(variant_key)

    rows = _target_rows_from_query(
        f"""
        SELECT
            cp.agent_id,
            a.name AS agent_name,
            cp.variant_key,
            c.experiment_key,
            c.challenge_key
        FROM challenge_participants cp
        JOIN challenges c ON c.id = cp.challenge_id
        JOIN agents a ON a.id = cp.agent_id
        WHERE {' AND '.join(where)}
        ORDER BY cp.id ASC
        LIMIT ?
        """,
        tuple(params),
        limit=clamped_limit,
    )
    return _apply_agent_filter(rows, normalized_agent_ids)


def resolve_team_mission_notification_targets(
    mission_key: str,
    *,
    team_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    agent_ids: Optional[list[int] | list[str]] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Resolve team mission participants or members for a mission/team."""
    normalized_agent_ids = _coerce_agent_ids(agent_ids)
    clamped_limit = _clamp_limit(limit)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        rows: list[dict[str, Any]] = []
        if team_key:
            params: list[Any] = [mission_key, team_key]
            where = ["tm.mission_key = ?", "t.team_key = ?", "tmem.status IN ('active', 'joined')"]
            if variant_key:
                where.append("COALESCE(t.variant_key, tmp.variant_key) = ?")
                params.append(variant_key)
            cursor.execute(
                f"""
                SELECT
                    tmem.agent_id,
                    a.name AS agent_name,
                    COALESCE(t.variant_key, tmp.variant_key) AS variant_key,
                    tm.experiment_key,
                    tm.mission_key,
                    t.team_key
                FROM team_members tmem
                JOIN teams t ON t.id = tmem.team_id
                JOIN team_missions tm ON tm.id = t.mission_id
                LEFT JOIN team_mission_participants tmp
                  ON tmp.mission_id = tm.id AND tmp.agent_id = tmem.agent_id
                JOIN agents a ON a.id = tmem.agent_id
                WHERE {' AND '.join(where)}
                ORDER BY tmem.id ASC
                LIMIT ?
                """,
                tuple(params + [clamped_limit]),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        else:
            participant_params: list[Any] = [mission_key]
            member_params: list[Any] = [mission_key]
            participant_where = ["tm.mission_key = ?", "tmp.status IN ('joined', 'active')"]
            member_where = ["tm.mission_key = ?", "tmem.status IN ('active', 'joined')"]
            if variant_key:
                participant_where.append("tmp.variant_key = ?")
                member_where.append("COALESCE(t.variant_key, tmp.variant_key) = ?")
                participant_params.append(variant_key)
                member_params.append(variant_key)
            cursor.execute(
                f"""
                SELECT *
                FROM (
                    SELECT
                        tmp.agent_id,
                        a.name AS agent_name,
                        tmp.variant_key,
                        tm.experiment_key,
                        tm.mission_key,
                        NULL AS team_key,
                        tmp.id AS sort_id
                    FROM team_mission_participants tmp
                    JOIN team_missions tm ON tm.id = tmp.mission_id
                    JOIN agents a ON a.id = tmp.agent_id
                    WHERE {' AND '.join(participant_where)}
                    UNION ALL
                    SELECT
                        tmem.agent_id,
                        a.name AS agent_name,
                        COALESCE(t.variant_key, tmp.variant_key) AS variant_key,
                        tm.experiment_key,
                        tm.mission_key,
                        t.team_key,
                        tmem.id AS sort_id
                    FROM team_members tmem
                    JOIN teams t ON t.id = tmem.team_id
                    JOIN team_missions tm ON tm.id = t.mission_id
                    LEFT JOIN team_mission_participants tmp
                      ON tmp.mission_id = tm.id AND tmp.agent_id = tmem.agent_id
                    JOIN agents a ON a.id = tmem.agent_id
                    WHERE {' AND '.join(member_where)}
                ) targets
                ORDER BY sort_id ASC
                LIMIT ?
                """,
                tuple(participant_params + member_params + [clamped_limit]),
            )
            rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    return _apply_agent_filter(rows, normalized_agent_ids)


def _validate_notification_payload(message_type: str, title: str, content: str) -> None:
    if message_type not in ALLOWED_NOTIFICATION_TYPES:
        raise ExperimentNotificationError(f"Unsupported message_type: {message_type}")
    if not (title or "").strip():
        raise ExperimentNotificationError("title is required")
    if not (content or "").strip():
        raise ExperimentNotificationError("content is required")
    if len(content) > CONTENT_MAX_LENGTH:
        raise ExperimentNotificationError(f"content exceeds {CONTENT_MAX_LENGTH} characters")


def _validate_task_payload(task_type: str) -> None:
    if task_type not in ALLOWED_TASK_TYPES:
        raise ExperimentNotificationError(f"Unsupported task_type: {task_type}")


def validate_notification_request(message_type: str, title: str, content: str) -> None:
    _validate_notification_payload(message_type, title, content)


def validate_task_request(task_type: str) -> None:
    _validate_task_payload(task_type)


async def send_agent_notifications(
    ctx: RouteContext,
    targets: list[dict[str, Any]],
    *,
    actor_agent_id: int,
    message_type: str,
    title: str,
    content: str,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    challenge_key: Optional[str] = None,
    mission_key: Optional[str] = None,
    team_key: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    dry_run: bool = True,
    campaign_id: Optional[str] = None,
    event_type: str = "experiment_notification_sent",
    target_rule: Optional[dict[str, Any]] = None,
    task_created_count: int = 0,
) -> dict[str, Any]:
    """Send or preview a bulk notification campaign."""
    _validate_notification_payload(message_type, title, content)
    campaign_id = campaign_id or str(uuid.uuid4())
    target_rule = target_rule or {}
    online_count = _online_count(ctx, targets)
    errors: list[dict[str, Any]] = []
    sent_count = 0
    skipped_count = 0

    message_data = {
        **(data or {}),
        "campaign_id": campaign_id,
        "title": title,
        "experiment_key": experiment_key,
        "variant_key": variant_key,
        "challenge_key": challenge_key,
        "mission_key": mission_key,
        "team_key": team_key,
    }
    message_data = {key: value for key, value in message_data.items() if value not in (None, "")}

    if not dry_run:
        for target in targets:
            agent_id = int(target["agent_id"])
            try:
                target_data = {
                    **message_data,
                    "target_variant_key": target.get("variant_key"),
                    "target_agent_id": agent_id,
                }
                await push_agent_message(ctx, agent_id, message_type, content, target_data)
                sent_count += 1
            except Exception as exc:
                skipped_count += 1
                errors.append({"agent_id": agent_id, "error": str(exc)})
    else:
        skipped_count = 0

    metadata = _base_campaign_payload(
        campaign_id=campaign_id,
        message_type=message_type,
        title=title,
        content=content,
        target_count=len(targets),
        sent_count=sent_count,
        online_count=online_count,
        skipped_count=skipped_count,
        task_created_count=task_created_count,
        dry_run=dry_run,
        target_rule=target_rule,
        errors=errors,
    )
    metadata.update({
        key: value
        for key, value in {
            "challenge_key": challenge_key,
            "mission_key": mission_key,
            "team_key": team_key,
        }.items()
        if value
    })
    record_event(
        event_type,
        actor_agent_id=actor_agent_id,
        object_type="notification_campaign",
        object_id=campaign_id,
        experiment_key=experiment_key,
        variant_key=variant_key,
        metadata=metadata,
    )

    return {
        "campaign_id": campaign_id,
        "target_count": len(targets),
        "sent_count": sent_count,
        "online_count": online_count,
        "skipped_count": skipped_count,
        "dry_run": dry_run,
        "targets_preview": _target_preview(targets),
        "task_created_count": task_created_count,
        "errors": errors,
    }


def create_agent_tasks(
    targets: list[dict[str, Any]],
    *,
    actor_agent_id: int,
    task_type: str,
    input_data: Optional[dict[str, Any]] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    challenge_key: Optional[str] = None,
    mission_key: Optional[str] = None,
    team_key: Optional[str] = None,
    dry_run: bool = True,
    campaign_id: Optional[str] = None,
    event_type: str = "experiment_tasks_created",
    target_rule: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create or preview bulk agent tasks for an experiment campaign."""
    _validate_task_payload(task_type)
    campaign_id = campaign_id or str(uuid.uuid4())
    target_rule = target_rule or {}
    task_created_count = 0
    skipped_count = 0
    errors: list[dict[str, Any]] = []

    task_input = {
        **(input_data or {}),
        "campaign_id": campaign_id,
        "experiment_key": experiment_key,
        "variant_key": variant_key,
        "challenge_key": challenge_key,
        "mission_key": mission_key,
        "team_key": team_key,
    }
    task_input = {key: value for key, value in task_input.items() if value not in (None, "")}

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if not dry_run:
            now = utc_now_iso_z()
            for target in targets:
                agent_id = int(target["agent_id"])
                try:
                    target_input = {
                        **task_input,
                        "target_variant_key": target.get("variant_key"),
                        "target_agent_id": agent_id,
                    }
                    cursor.execute(
                        """
                        INSERT INTO agent_tasks (agent_id, type, input_data, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (agent_id, task_type, _json_dumps(target_input), now, now),
                    )
                    task_created_count += 1
                except Exception as exc:
                    skipped_count += 1
                    errors.append({"agent_id": agent_id, "error": str(exc)})
            conn.commit()
        metadata = _base_campaign_payload(
            campaign_id=campaign_id,
            task_type=task_type,
            target_count=len(targets),
            skipped_count=skipped_count,
            task_created_count=task_created_count,
            dry_run=dry_run,
            target_rule=target_rule,
            errors=errors,
        )
        metadata.update({
            key: value
            for key, value in {
                "challenge_key": challenge_key,
                "mission_key": mission_key,
                "team_key": team_key,
            }.items()
            if value
        })
        record_event(
            event_type,
            actor_agent_id=actor_agent_id,
            object_type="task_campaign",
            object_id=campaign_id,
            experiment_key=experiment_key,
            variant_key=variant_key,
            metadata=metadata,
            cursor=cursor,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "campaign_id": campaign_id,
        "target_count": len(targets),
        "task_created_count": task_created_count,
        "skipped_count": skipped_count,
        "dry_run": dry_run,
        "targets_preview": _target_preview(targets),
        "errors": errors,
    }


def build_experiment_target_rule(
    *,
    experiment_key: str,
    variant_key: Optional[str] = None,
    agent_ids: Optional[list[int] | list[str]] = None,
    limit: Optional[int] = None,
    challenge_key: Optional[str] = None,
    mission_key: Optional[str] = None,
    team_key: Optional[str] = None,
    target: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "target": target or "experiment",
        "experiment_key": experiment_key,
        "variant_key": variant_key,
        "agent_ids": agent_ids or [],
        "limit": _clamp_limit(limit),
        "challenge_key": challenge_key,
        "mission_key": mission_key,
        "team_key": team_key,
    }

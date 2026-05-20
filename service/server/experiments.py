"""Experiment configuration and stable assignment helpers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection
from experiment_events import record_assignment_event
from routes_shared import utc_now_iso_z


DEFAULT_VARIANTS = [
    {"key": "control", "weight": 1},
    {"key": "treatment", "weight": 1},
]

EXPERIMENT_CONFIG_KEYS = {
    "enrollment_max_unit_id",
    "enrollment_closed_at",
    "enrollment_reason",
    "enrollment_status",
}

EXPERIMENT_NOTIFICATION_TYPES = (
    "experiment_announcement",
    "experiment_assignment",
    "experiment_reminder",
    "experiment_rule_update",
    "experiment_result_update",
    "challenge_invite",
    "team_mission_invite",
)

EXPERIMENT_BEHAVIOR_EVENT_TYPES = (
    "agent_heartbeat",
    "agent_tasks_read",
    "signal_published",
    "reply_created",
    "reply_accepted",
    "experiment_notice_exposed",
)

EXPERIMENT_PRIMARY_METRIC_FAMILY = "active_agent_behavior"
EXPERIMENT_READ_RECEIPTS_ROLE = "diagnostic_only"
EXPERIMENT_BEHAVIOR_WINDOW_HOURS = 24


class ExperimentError(ValueError):
    pass


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _normalize_key(value: Optional[str], fallback: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        candidate = fallback.strip().lower()
    candidate = re.sub(r"[^a-z0-9_\-]+", "-", candidate).strip("-_")
    if not candidate:
        raise ExperimentError("experiment_key is required")
    return candidate[:90]


def _serialize_experiment(row: Any) -> dict[str, Any]:
    data = dict(row) if row is not None and not isinstance(row, dict) else (row or {})
    data["variants"] = normalize_variants(data.get("variants_json"))
    data.update(experiment_config(data.get("variants_json")))
    return data


def experiment_config(value: Any) -> dict[str, Any]:
    raw = _json_loads(value, {})
    if not isinstance(raw, dict):
        return {}

    config = {key: raw[key] for key in EXPERIMENT_CONFIG_KEYS if key in raw}
    enrollment = raw.get("enrollment")
    if isinstance(enrollment, dict):
        if "max_unit_id" in enrollment and "enrollment_max_unit_id" not in config:
            config["enrollment_max_unit_id"] = enrollment["max_unit_id"]
        if "closed_at" in enrollment and "enrollment_closed_at" not in config:
            config["enrollment_closed_at"] = enrollment["closed_at"]
        if "reason" in enrollment and "enrollment_reason" not in config:
            config["enrollment_reason"] = enrollment["reason"]
        if "status" in enrollment and "enrollment_status" not in config:
            config["enrollment_status"] = enrollment["status"]
    return config


def normalize_variants(value: Any) -> list[dict[str, Any]]:
    raw = _json_loads(value, DEFAULT_VARIANTS)
    if isinstance(raw, dict):
        if isinstance(raw.get("variants"), list):
            raw = raw["variants"]
        else:
            raw = [{"key": key, **(config if isinstance(config, dict) else {"weight": config})} for key, config in raw.items()]
    if not isinstance(raw, list):
        raw = DEFAULT_VARIANTS

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            variant = {"key": item, "weight": 1}
        elif isinstance(item, dict):
            variant = dict(item)
        else:
            continue
        key = str(variant.get("key") or variant.get("variant_key") or f"variant-{index + 1}").strip()
        if not key:
            continue
        try:
            weight = float(variant.get("weight", 1))
        except Exception:
            weight = 1.0
        if weight <= 0:
            continue
        variant["key"] = key
        variant["weight"] = weight
        normalized.append(variant)
    return normalized or list(DEFAULT_VARIANTS)


def _variants_json_payload(raw_value: Any, variants: list[dict[str, Any]]) -> Any:
    config = experiment_config(raw_value)
    if not config:
        return variants
    return {"variants": variants, **config}


def experiment_enrollment_max_unit_id(experiment: dict[str, Any]) -> Optional[int]:
    value = experiment.get("enrollment_max_unit_id")
    if value is None:
        value = experiment_config(experiment.get("variants_json")).get("enrollment_max_unit_id")
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def experiment_accepts_unit(experiment: dict[str, Any], unit_type: str, unit_id: int | str) -> bool:
    if unit_type != "agent":
        return True
    max_unit_id = experiment_enrollment_max_unit_id(experiment)
    if max_unit_id is None:
        return True
    try:
        return int(unit_id) <= max_unit_id
    except Exception:
        return False


def get_experiment_enrollment_max_unit_id(experiment_key: str) -> Optional[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT variants_json FROM experiments WHERE experiment_key = ?", (experiment_key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return experiment_enrollment_max_unit_id(dict(row))


def _behavior_window_since(hours: int = EXPERIMENT_BEHAVIOR_WINDOW_HOURS) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _rows_by_variant(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("variant_key") or ""): row for row in rows}


def _experiment_behavior_metrics(cursor: Any, experiment_key: str, *, since: str) -> list[dict[str, Any]]:
    """Return recent behavior metrics by variant without depending on message read state."""
    behavior_placeholders = ",".join("?" for _ in EXPERIMENT_BEHAVIOR_EVENT_TYPES)
    cursor.execute(
        f"""
        SELECT
            ea.variant_key,
            COUNT(DISTINCT ea.unit_id) AS assigned_agent_count,
            COUNT(DISTINCT CASE
                WHEN ee.event_type IN ({behavior_placeholders}) THEN ea.unit_id
            END) AS active_agent_count_24h,
            SUM(CASE
                WHEN ee.event_type IN ({behavior_placeholders}) THEN 1 ELSE 0
            END) AS active_behavior_event_count_24h,
            COUNT(DISTINCT CASE WHEN ee.event_type = 'agent_heartbeat' THEN ea.unit_id END) AS heartbeat_agent_count_24h,
            SUM(CASE WHEN ee.event_type = 'agent_heartbeat' THEN 1 ELSE 0 END) AS heartbeat_count_24h,
            COUNT(DISTINCT CASE WHEN ee.event_type = 'agent_tasks_read' THEN ea.unit_id END) AS task_read_agent_count_24h,
            SUM(CASE WHEN ee.event_type = 'agent_tasks_read' THEN 1 ELSE 0 END) AS task_read_count_24h,
            COUNT(DISTINCT CASE WHEN ee.event_type = 'signal_published' THEN ea.unit_id END) AS signal_agent_count_24h,
            SUM(CASE WHEN ee.event_type = 'signal_published' THEN 1 ELSE 0 END) AS signal_count_24h,
            COUNT(DISTINCT CASE WHEN ee.event_type IN ('reply_created', 'reply_accepted') THEN ea.unit_id END) AS reply_agent_count_24h,
            SUM(CASE WHEN ee.event_type IN ('reply_created', 'reply_accepted') THEN 1 ELSE 0 END) AS reply_count_24h,
            COUNT(DISTINCT CASE WHEN ee.event_type = 'experiment_notice_exposed' THEN ea.unit_id END) AS experiment_notice_exposure_agent_count_24h,
            SUM(CASE WHEN ee.event_type = 'experiment_notice_exposed' THEN 1 ELSE 0 END) AS experiment_notice_exposure_count_24h
        FROM experiment_assignments ea
        LEFT JOIN experiment_events ee
          ON ee.actor_agent_id = ea.unit_id
         AND ee.created_at >= ?
        WHERE ea.experiment_key = ?
          AND ea.unit_type = 'agent'
        GROUP BY ea.variant_key
        ORDER BY ea.variant_key
        """,
        (*EXPERIMENT_BEHAVIOR_EVENT_TYPES, *EXPERIMENT_BEHAVIOR_EVENT_TYPES, since, experiment_key),
    )
    return [dict(row) for row in cursor.fetchall()]


def _experiment_read_diagnostics(cursor: Any, experiment_key: str) -> list[dict[str, Any]]:
    """Return message read diagnostics by variant; these are not primary experiment metrics."""
    notification_placeholders = ",".join("?" for _ in EXPERIMENT_NOTIFICATION_TYPES)
    cursor.execute(
        f"""
        SELECT
            ea.variant_key,
            COUNT(DISTINCT CASE WHEN am.read = 1 THEN ea.unit_id END) AS read_receipt_agent_count,
            SUM(CASE WHEN am.read = 1 THEN 1 ELSE 0 END) AS read_receipt_message_count,
            COUNT(DISTINCT CASE WHEN COALESCE(am.read, 0) = 0 AND am.id IS NOT NULL THEN ea.unit_id END) AS unread_experiment_agent_count,
            SUM(CASE WHEN COALESCE(am.read, 0) = 0 AND am.id IS NOT NULL THEN 1 ELSE 0 END) AS unread_experiment_message_count
        FROM experiment_assignments ea
        LEFT JOIN agent_messages am
          ON am.agent_id = ea.unit_id
         AND am.type IN ({notification_placeholders})
        WHERE ea.experiment_key = ?
          AND ea.unit_type = 'agent'
        GROUP BY ea.variant_key
        ORDER BY ea.variant_key
        """,
        (*EXPERIMENT_NOTIFICATION_TYPES, experiment_key),
    )
    return [dict(row) for row in cursor.fetchall()]


def agent_experiment_behavior_context(agent_id: int) -> Optional[dict[str, Any]]:
    """Return active experiment context for high-frequency agent APIs without enrolling new agents."""
    now = utc_now_iso_z()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            e.experiment_key,
            e.title,
            e.description,
            e.status,
            e.unit_type,
            e.start_at,
            e.end_at,
            ea.variant_key,
            ea.assignment_reason,
            ea.created_at AS assignment_created_at
        FROM experiment_assignments ea
        JOIN experiments e ON e.experiment_key = ea.experiment_key
        WHERE ea.unit_type = 'agent'
          AND ea.unit_id = ?
          AND e.status = 'active'
          AND (e.start_at IS NULL OR e.start_at <= ?)
          AND (e.end_at IS NULL OR e.end_at >= ?)
        ORDER BY e.created_at DESC, e.id DESC
        """,
        (agent_id, now, now),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    if not rows:
        return None

    assignments = []
    for row in rows:
        assignments.append({
            "experiment_key": row.get("experiment_key"),
            "title": row.get("title"),
            "variant_key": row.get("variant_key"),
            "assignment_reason": row.get("assignment_reason"),
            "assignment_created_at": row.get("assignment_created_at"),
            "status": row.get("status"),
            "primary_metric_family": EXPERIMENT_PRIMARY_METRIC_FAMILY,
            "read_receipts_role": EXPERIMENT_READ_RECEIPTS_ROLE,
            "message_read_state_required": False,
            "tracked_behaviors": [
                "agent_heartbeat",
                "agent_tasks_read",
                "signal_published",
                "reply_created",
                "reply_accepted",
            ],
        })

    return {
        "primary_metric_family": EXPERIMENT_PRIMARY_METRIC_FAMILY,
        "read_receipts_role": EXPERIMENT_READ_RECEIPTS_ROLE,
        "message_read_state_required": False,
        "assignments": assignments,
    }


def stable_bucket(experiment_key: str, unit_type: str, unit_id: int | str, *, salt: str = "") -> int:
    seed = f"{experiment_key}:{unit_type}:{unit_id}:{salt}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _choose_variant(experiment_key: str, unit_type: str, unit_id: int | str, variants: list[dict[str, Any]], *, salt: str = "") -> dict[str, Any]:
    total_weight = sum(float(item.get("weight", 1)) for item in variants)
    if total_weight <= 0:
        return variants[0]
    bucket = stable_bucket(experiment_key, unit_type, unit_id, salt=salt) % 1_000_000
    threshold = bucket / 1_000_000 * total_weight
    cursor = 0.0
    for variant in variants:
        cursor += float(variant.get("weight", 1))
        if threshold < cursor:
            return variant
    return variants[-1]


def create_experiment(data: Any) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else data.model_dump()
    title = (payload.get("title") or "").strip()
    if not title:
        raise ExperimentError("title is required")
    experiment_key = _normalize_key(payload.get("experiment_key"), title)
    variants = normalize_variants(payload.get("variants_json") or payload.get("variants"))
    now = utc_now_iso_z()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            """
            INSERT INTO experiments
            (experiment_key, title, description, status, unit_type, variants_json,
             start_at, end_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_key,
                title,
                payload.get("description"),
                payload.get("status") or "active",
                payload.get("unit_type") or "agent",
                _json_dumps(_variants_json_payload(payload.get("variants_json") or payload.get("variants"), variants)),
                payload.get("start_at"),
                payload.get("end_at"),
                now,
                now,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM experiments WHERE experiment_key = ?", (experiment_key,))
        return _serialize_experiment(cursor.fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_experiments(status: Optional[str] = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    where = "1=1"
    params: list[Any] = []
    if status:
        where = "status = ?"
        params.append(status)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) AS total FROM experiments WHERE {where}", params)
    total = cursor.fetchone()["total"]
    cursor.execute(
        f"""
        SELECT *
        FROM experiments
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )
    experiments = [_serialize_experiment(row) for row in cursor.fetchall()]
    conn.close()
    return {"experiments": experiments, "total": total, "limit": limit, "offset": offset}


def get_active_experiments(unit_type: Optional[str] = None, *, now: Optional[str] = None) -> list[dict[str, Any]]:
    now = now or utc_now_iso_z()
    conditions = ["status = 'active'", "(start_at IS NULL OR start_at <= ?)", "(end_at IS NULL OR end_at >= ?)"]
    params: list[Any] = [now, now]
    if unit_type:
        conditions.append("unit_type = ?")
        params.append(unit_type)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT *
        FROM experiments
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC, id DESC
        """,
        params,
    )
    experiments = [_serialize_experiment(row) for row in cursor.fetchall()]
    conn.close()
    return experiments


def get_assignment(experiment_key: str, unit_type: str, unit_id: int | str) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM experiment_assignments
        WHERE experiment_key = ? AND unit_type = ? AND unit_id = ?
        """,
        (experiment_key, unit_type, unit_id),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def assign_unit_to_experiment(
    experiment_key: str,
    unit_type: str,
    unit_id: int | str,
    *,
    assignment_reason: str = "stable_bucket",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    existing = get_assignment(experiment_key, unit_type, unit_id)
    if existing:
        existing["idempotent"] = True
        return existing

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute("SELECT * FROM experiments WHERE experiment_key = ?", (experiment_key,))
        experiment = cursor.fetchone()
        if not experiment:
            raise ExperimentError("Experiment not found")
        experiment_data = _serialize_experiment(experiment)
        variants = experiment_data["variants"]
        if not experiment_accepts_unit(experiment_data, unit_type, unit_id):
            raise ExperimentError(f"Experiment enrollment is closed for {unit_type} {unit_id}")
        salt = str((metadata or {}).get("strata_key") or "")
        variant = _choose_variant(experiment_key, unit_type, unit_id, variants, salt=salt)
        now = utc_now_iso_z()
        cursor.execute(
            """
            INSERT INTO experiment_assignments
            (experiment_key, unit_type, unit_id, variant_key, assignment_reason, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_key,
                unit_type,
                int(unit_id),
                variant["key"],
                assignment_reason,
                _json_dumps(metadata or {}),
                now,
            ),
        )
        assignment_id = cursor.lastrowid
        record_assignment_event(
            experiment_key,
            unit_type=unit_type,
            unit_id=int(unit_id),
            variant_key=variant["key"],
            assignment_reason=assignment_reason,
            metadata=metadata or {},
            cursor=cursor,
        )
        conn.commit()
        cursor.execute("SELECT * FROM experiment_assignments WHERE id = ?", (assignment_id,))
        result = dict(cursor.fetchone())
        result["idempotent"] = False
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def variant_for_agent(agent_id: int, experiment_key: Optional[str] = None) -> Any:
    if experiment_key:
        return assign_unit_to_experiment(experiment_key, "agent", agent_id)
    assignments = []
    for experiment in get_active_experiments("agent"):
        if not experiment_accepts_unit(experiment, "agent", agent_id):
            continue
        assignments.append(assign_unit_to_experiment(experiment["experiment_key"], "agent", agent_id))
    return assignments


def get_experiment_assignments(experiment_key: str, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(limit, 5000))
    offset = max(0, offset)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM experiments WHERE experiment_key = ?", (experiment_key,))
    experiment_row = cursor.fetchone()
    if not experiment_row:
        conn.close()
        raise ExperimentError("Experiment not found")
    cursor.execute(
        """
        SELECT variant_key, COUNT(*) AS count
        FROM experiment_assignments
        WHERE experiment_key = ?
        GROUP BY variant_key
        ORDER BY variant_key
        """,
        (experiment_key,),
    )
    counts = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        """
        WITH latest_snapshots AS (
            SELECT ams.*
            FROM agent_metric_snapshots ams
            JOIN (
                SELECT agent_id, MAX(window_end_at) AS latest_window_end_at
                FROM agent_metric_snapshots
                GROUP BY agent_id
            ) latest
              ON latest.agent_id = ams.agent_id
             AND latest.latest_window_end_at = ams.window_end_at
        )
        SELECT
            ea.variant_key,
            COUNT(*) AS agent_count,
            AVG(COALESCE(ls.return_pct, 0)) AS return_pct_avg,
            AVG(COALESCE(ls.max_drawdown, 0)) AS max_drawdown_avg,
            SUM(COALESCE(ls.trade_count, 0)) AS trade_count,
            SUM(COALESCE(ls.strategy_count, 0)) AS strategy_count,
            SUM(COALESCE(ls.discussion_count, 0)) AS discussion_count,
            SUM(COALESCE(ls.reply_count, 0)) AS reply_count,
            SUM(COALESCE(ls.accepted_reply_count, 0)) AS accepted_reply_count,
            SUM(COALESCE(ls.citation_count, 0)) AS citation_count,
            SUM(COALESCE(ls.adoption_count, 0)) AS adoption_count,
            AVG(COALESCE(ls.quality_score_avg, 0)) AS quality_score_avg
        FROM experiment_assignments ea
        LEFT JOIN latest_snapshots ls
          ON ls.agent_id = ea.unit_id
         AND ea.unit_type = 'agent'
        WHERE ea.experiment_key = ?
        GROUP BY ea.variant_key
        ORDER BY ea.variant_key
        """,
        (experiment_key,),
    )
    metrics = [dict(row) for row in cursor.fetchall()]
    behavior_window_start_at = _behavior_window_since()
    behavior_metrics = _rows_by_variant(
        _experiment_behavior_metrics(cursor, experiment_key, since=behavior_window_start_at)
    )
    read_diagnostics = _rows_by_variant(_experiment_read_diagnostics(cursor, experiment_key))
    for row in metrics:
        variant_key = str(row.get("variant_key") or "")
        row.update(behavior_metrics.get(variant_key, {}))
        row.update(read_diagnostics.get(variant_key, {}))
        row["primary_metric_family"] = EXPERIMENT_PRIMARY_METRIC_FAMILY
        row["read_receipts_role"] = EXPERIMENT_READ_RECEIPTS_ROLE
        row["message_read_state_required"] = False
        row["behavior_window_hours"] = EXPERIMENT_BEHAVIOR_WINDOW_HOURS
        row["behavior_window_start_at"] = behavior_window_start_at
    cursor.execute(
        """
        SELECT ea.*, a.name AS agent_name
        FROM experiment_assignments ea
        LEFT JOIN agents a ON a.id = ea.unit_id AND ea.unit_type = 'agent'
        WHERE ea.experiment_key = ?
        ORDER BY ea.created_at DESC, ea.id DESC
        LIMIT ? OFFSET ?
        """,
        (experiment_key, limit, offset),
    )
    assignments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {
        "experiment": _serialize_experiment(experiment_row),
        "variant_counts": counts,
        "variant_metrics": metrics,
        "metric_policy": {
            "primary_metric_family": EXPERIMENT_PRIMARY_METRIC_FAMILY,
            "read_receipts_role": EXPERIMENT_READ_RECEIPTS_ROLE,
            "message_read_state_required": False,
            "behavior_window_hours": EXPERIMENT_BEHAVIOR_WINDOW_HOURS,
            "behavior_window_start_at": behavior_window_start_at,
            "tracked_behaviors": [
                "agent_heartbeat",
                "agent_tasks_read",
                "signal_published",
                "reply_created",
                "reply_accepted",
                "experiment_notice_exposed",
            ],
            "diagnostic_metrics": [
                "read_receipt_agent_count",
                "read_receipt_message_count",
                "unread_experiment_agent_count",
                "unread_experiment_message_count",
            ],
        },
        "assignments": assignments,
        "limit": limit,
        "offset": offset,
    }


def update_experiment_status(experiment_key: str, status: str) -> dict[str, Any]:
    normalized = status.strip().lower()
    if normalized not in {"draft", "active", "paused", "completed", "archived"}:
        raise ExperimentError("Unsupported experiment status")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            "UPDATE experiments SET status = ?, updated_at = ? WHERE experiment_key = ?",
            (normalized, utc_now_iso_z(), experiment_key),
        )
        if cursor.rowcount == 0:
            raise ExperimentError("Experiment not found")
        conn.commit()
        cursor.execute("SELECT * FROM experiments WHERE experiment_key = ?", (experiment_key,))
        return _serialize_experiment(cursor.fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

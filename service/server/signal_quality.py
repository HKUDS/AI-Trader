"""Heuristic signal prediction extraction and quality scoring."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from database import begin_write_transaction, get_db_connection
from routes_shared import utc_now_iso_z


MODEL_VERSION = "heuristic-v1"


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None and not isinstance(row, dict) else (row or {})


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _text(signal: dict[str, Any]) -> str:
    return " ".join(str(signal.get(key) or "") for key in ("title", "content", "symbol", "symbols", "tags")).strip()


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(5.0, value)), 4)


def detect_duplicate_content(
    content: str,
    *,
    agent_id: Optional[int] = None,
    signal_id: Optional[int] = None,
    cursor: Any = None,
) -> dict[str, Any]:
    own_connection = cursor is None
    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()

    normalized = " ".join((content or "").lower().split())
    if not normalized:
        if own_connection:
            conn.close()
        return {"duplicate_count": 0, "is_duplicate": False}

    conditions = ["LOWER(TRIM(content)) = ?"]
    params: list[Any] = [normalized]
    if agent_id is not None:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if signal_id is not None:
        conditions.append("signal_id != ?")
        params.append(signal_id)

    cursor.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM signals
        WHERE {' AND '.join(conditions)}
        """,
        params,
    )
    count = int(cursor.fetchone()["count"] or 0)
    if own_connection:
        conn.close()
    return {"duplicate_count": count, "is_duplicate": count > 0}


def extract_prediction_from_signal(
    signal: Any,
    *,
    cursor: Any = None,
    extracted_by: str = MODEL_VERSION,
) -> dict[str, Any]:
    item = _row_dict(signal)
    signal_id = item.get("signal_id")
    agent_id = item.get("agent_id")
    if signal_id is None or agent_id is None:
        raise ValueError("signal_id and agent_id are required")

    content = _text(item)
    lower = content.lower()
    direction = None
    if any(word in lower for word in ("buy", "long", "bull", "upside", "breakout", "看多", "上涨")):
        direction = "up"
    elif any(word in lower for word in ("sell", "short", "bear", "downside", "breakdown", "看空", "下跌")):
        direction = "down"
    elif any(word in lower for word in ("hold", "neutral", "range", "sideways", "震荡")):
        direction = "flat"

    price_match = re.search(r"(?:target|tp|目标价|price)\D{0,12}([0-9]+(?:\.[0-9]+)?)", content, flags=re.IGNORECASE)
    probability_match = re.search(r"([0-9]{1,3})(?:\s?%|\s?percent)", content, flags=re.IGNORECASE)
    confidence_match = re.search(r"(?:confidence|conf|置信度)\D{0,12}([0-9]+(?:\.[0-9]+)?)", content, flags=re.IGNORECASE)

    target_price = float(price_match.group(1)) if price_match else None
    target_probability = None
    if probability_match:
        target_probability = max(0.0, min(float(probability_match.group(1)) / 100.0, 1.0))
    confidence = None
    if confidence_match:
        raw = float(confidence_match.group(1))
        confidence = raw / 100.0 if raw > 1 else raw
        confidence = max(0.0, min(confidence, 1.0))

    prediction = {
        "signal_id": signal_id,
        "agent_id": agent_id,
        "market": item.get("market"),
        "symbol": item.get("symbol") or (str(item.get("symbols") or "").split(",")[0].strip() or None),
        "direction": direction,
        "target_price": target_price,
        "target_probability": target_probability,
        "confidence": confidence,
        "horizon_start_at": item.get("created_at"),
        "horizon_end_at": None,
        "invalid_if": None,
        "evidence_json": {"content_length": len(content), "keywords": [word for word in ("target", "risk", "because", "evidence") if word in lower]},
        "extracted_by": extracted_by,
    }

    own_connection = cursor is None
    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)
    try:
        cursor.execute(
            "SELECT * FROM signal_predictions WHERE signal_id = ? AND agent_id = ? ORDER BY id DESC LIMIT 1",
            (signal_id, agent_id),
        )
        existing = cursor.fetchone()
        if existing:
            if own_connection:
                conn.commit()
                conn.close()
            return dict(existing)

        cursor.execute(
            """
            INSERT INTO signal_predictions
            (signal_id, agent_id, market, symbol, direction, target_price,
             target_probability, confidence, horizon_start_at, horizon_end_at,
             invalid_if, evidence_json, extracted_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction["signal_id"],
                prediction["agent_id"],
                prediction["market"],
                prediction["symbol"],
                prediction["direction"],
                prediction["target_price"],
                prediction["target_probability"],
                prediction["confidence"],
                prediction["horizon_start_at"],
                prediction["horizon_end_at"],
                prediction["invalid_if"],
                _json_dumps(prediction["evidence_json"]),
                prediction["extracted_by"],
                utc_now_iso_z(),
            ),
        )
        prediction["id"] = cursor.lastrowid
        if own_connection:
            conn.commit()
            conn.close()
        return prediction
    except Exception:
        if own_connection:
            conn.rollback()
            conn.close()
        raise


def score_signal_quality(
    signal: Any,
    *,
    cursor: Any = None,
    model_version: str = MODEL_VERSION,
) -> dict[str, Any]:
    item = _row_dict(signal)
    signal_id = item.get("signal_id")
    agent_id = item.get("agent_id")
    if signal_id is None or agent_id is None:
        raise ValueError("signal_id and agent_id are required")

    content = _text(item)
    lower = content.lower()
    prediction = extract_prediction_from_signal(item, cursor=cursor, extracted_by=model_version)
    duplicate = detect_duplicate_content(content, agent_id=agent_id, signal_id=signal_id, cursor=cursor)

    verifiability = 1.0
    if prediction.get("direction"):
        verifiability += 1.2
    if prediction.get("symbol"):
        verifiability += 0.8
    if prediction.get("target_price") is not None or prediction.get("target_probability") is not None:
        verifiability += 1.2

    evidence = min(5.0, len(content) / 160.0 + sum(word in lower for word in ("because", "risk", "evidence", "data", "chart", "catalyst")) * 0.7)
    specificity = 1.0 + (1.0 if item.get("symbol") or item.get("symbols") else 0.0) + (1.0 if item.get("tags") else 0.0) + min(len(content) / 320.0, 2.0)
    novelty = 5.0 if not duplicate["is_duplicate"] else max(0.5, 5.0 - duplicate["duplicate_count"])
    review = 1.0 + (2.0 if item.get("accepted_reply_id") else 0.0)
    overall = (verifiability * 0.3) + (evidence * 0.25) + (specificity * 0.2) + (novelty * 0.15) + (review * 0.1)

    score = {
        "signal_id": signal_id,
        "agent_id": agent_id,
        "verifiability_score": _clamp_score(verifiability),
        "evidence_score": _clamp_score(evidence),
        "specificity_score": _clamp_score(specificity),
        "novelty_score": _clamp_score(novelty),
        "review_score": _clamp_score(review),
        "overall_score": _clamp_score(overall),
        "model_version": model_version,
        "metadata_json": {"duplicate_count": duplicate["duplicate_count"], "prediction_id": prediction.get("id")},
    }

    own_connection = cursor is None
    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()
        begin_write_transaction(cursor)
    try:
        cursor.execute(
            "SELECT * FROM signal_quality_scores WHERE signal_id = ? AND agent_id = ? AND model_version = ? ORDER BY id DESC LIMIT 1",
            (signal_id, agent_id, model_version),
        )
        existing = cursor.fetchone()
        if existing:
            if own_connection:
                conn.commit()
                conn.close()
            return dict(existing)
        cursor.execute(
            """
            INSERT INTO signal_quality_scores
            (signal_id, agent_id, verifiability_score, evidence_score,
             specificity_score, novelty_score, review_score, overall_score,
             model_version, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                score["signal_id"],
                score["agent_id"],
                score["verifiability_score"],
                score["evidence_score"],
                score["specificity_score"],
                score["novelty_score"],
                score["review_score"],
                score["overall_score"],
                score["model_version"],
                _json_dumps(score["metadata_json"]),
                utc_now_iso_z(),
            ),
        )
        score["id"] = cursor.lastrowid
        if own_connection:
            conn.commit()
            conn.close()
        return score
    except Exception:
        if own_connection:
            conn.rollback()
            conn.close()
        raise


def score_unscored_signals(limit: int = 500) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted = 0
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            """
            SELECT s.*
            FROM signals s
            LEFT JOIN signal_quality_scores sqs
              ON sqs.signal_id = s.signal_id AND sqs.agent_id = s.agent_id AND sqs.model_version = ?
            WHERE sqs.id IS NULL
              AND s.message_type IN ('strategy', 'discussion', 'operation')
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (MODEL_VERSION, max(1, min(limit, 5000))),
        )
        for row in cursor.fetchall():
            result = score_signal_quality(row, cursor=cursor)
            if result.get("id"):
                inserted += 1
        conn.commit()
        return {"inserted": inserted}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

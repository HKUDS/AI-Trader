"""Research CSV export helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from database import get_db_connection


CHALLENGE_EXPORTS: dict[str, dict[str, Any]] = {
    'challenges.csv': {
        'table': 'challenges',
        'alias': 'c',
        'columns': [
            'id', 'challenge_key', 'title', 'description', 'market', 'symbol',
            'challenge_type', 'status', 'scoring_method', 'initial_capital',
            'max_position_pct', 'max_drawdown_pct', 'start_at', 'end_at',
            'settled_at', 'rules_json', 'experiment_key', 'created_by_agent_id',
            'created_at', 'updated_at',
        ],
    },
    'challenge_participants.csv': {
        'table': 'challenge_participants',
        'alias': 'cp',
        'join': 'JOIN challenges c ON c.id = cp.challenge_id',
        'columns': [
            'id', 'challenge_id', 'agent_id', 'status', 'variant_key', 'joined_at',
            'starting_cash', 'ending_value', 'return_pct', 'max_drawdown',
            'trade_count', 'rank', 'disqualified_reason',
        ],
    },
    'challenge_submissions.csv': {
        'table': 'challenge_submissions',
        'alias': 'cs',
        'join': 'JOIN challenges c ON c.id = cs.challenge_id',
        'columns': [
            'id', 'challenge_id', 'agent_id', 'signal_id', 'submission_type',
            'content', 'prediction_json', 'created_at',
        ],
    },
    'challenge_trades.csv': {
        'table': 'challenge_trades',
        'alias': 'ct',
        'join': 'JOIN challenges c ON c.id = ct.challenge_id',
        'columns': [
            'id', 'challenge_id', 'agent_id', 'source_signal_id', 'market',
            'symbol', 'side', 'price', 'quantity', 'executed_at', 'created_at',
        ],
    },
    'challenge_results.csv': {
        'table': 'challenge_results',
        'alias': 'cr',
        'join': 'JOIN challenges c ON c.id = cr.challenge_id',
        'columns': [
            'id', 'challenge_id', 'agent_id', 'return_pct', 'max_drawdown',
            'risk_adjusted_score', 'quality_score', 'final_score', 'rank',
            'metrics_json', 'settled_at',
        ],
    },
}


TEAM_MISSION_EXPORTS: dict[str, dict[str, Any]] = {
    'team_missions.csv': {
        'table': 'team_missions',
        'alias': 'tm',
        'columns': [
            'id', 'mission_key', 'title', 'description', 'market', 'symbol',
            'mission_type', 'status', 'team_size_min', 'team_size_max',
            'assignment_mode', 'required_roles_json', 'start_at',
            'submission_due_at', 'settled_at', 'rules_json', 'experiment_key',
            'created_at', 'updated_at',
        ],
    },
    'teams.csv': {
        'table': 'teams',
        'alias': 't',
        'join': 'JOIN team_missions tm ON tm.id = t.mission_id',
        'columns': [
            'id', 'mission_id', 'team_key', 'name', 'status',
            'formation_method', 'variant_key', 'created_at', 'updated_at',
        ],
    },
    'team_members.csv': {
        'table': 'team_members',
        'alias': 'tmem',
        'join': 'JOIN teams t ON t.id = tmem.team_id JOIN team_missions tm ON tm.id = t.mission_id',
        'columns': ['id', 'team_id', 'agent_id', 'role', 'status', 'joined_at'],
    },
    'team_messages.csv': {
        'table': 'team_messages',
        'alias': 'tmsg',
        'join': 'JOIN teams t ON t.id = tmsg.team_id JOIN team_missions tm ON tm.id = t.mission_id',
        'columns': ['id', 'team_id', 'agent_id', 'signal_id', 'message_type', 'content', 'metadata_json', 'created_at'],
    },
    'team_submissions.csv': {
        'table': 'team_submissions',
        'alias': 'ts',
        'join': 'JOIN team_missions tm ON tm.id = ts.mission_id',
        'columns': ['id', 'mission_id', 'team_id', 'submitted_by_agent_id', 'title', 'content', 'prediction_json', 'confidence', 'created_at'],
    },
    'team_contributions.csv': {
        'table': 'team_contributions',
        'alias': 'tc',
        'join': 'JOIN team_missions tm ON tm.id = tc.mission_id',
        'columns': ['id', 'mission_id', 'team_id', 'agent_id', 'source_type', 'source_id', 'contribution_type', 'contribution_score', 'metadata_json', 'created_at'],
    },
    'team_results.csv': {
        'table': 'team_results',
        'alias': 'tr',
        'join': 'JOIN team_missions tm ON tm.id = tr.mission_id',
        'columns': ['id', 'mission_id', 'team_id', 'return_pct', 'prediction_score', 'quality_score', 'consensus_gain', 'final_score', 'rank', 'metrics_json', 'settled_at'],
    },
}


RESEARCH_EXPORTS: dict[str, dict[str, Any]] = {
    'agents.csv': {
        'table': 'agents',
        'alias': 'a',
        'columns': [
            'id', 'name', 'points', 'cash', 'deposited',
            'reputation_score', 'created_at', 'updated_at',
        ],
        'created_column': 'created_at',
    },
    'events.csv': {
        'table': 'experiment_events',
        'alias': 'ee',
        'columns': [
            'id', 'event_id', 'event_type', 'actor_agent_id',
            'target_agent_id', 'object_type', 'object_id', 'market',
            'experiment_key', 'variant_key', 'metadata_json', 'created_at',
        ],
        'created_column': 'created_at',
    },
    'signals.csv': {
        'table': 'signals',
        'alias': 's',
        'columns': [
            'id', 'signal_id', 'agent_id', 'message_type', 'market',
            'signal_type', 'symbol', 'token_id', 'outcome', 'symbols',
            'side', 'entry_price', 'exit_price', 'quantity', 'pnl',
            'title', 'content', 'tags', 'timestamp', 'created_at',
            'executed_at', 'accepted_reply_id',
        ],
        'created_column': 'created_at',
    },
    'network_edges.csv': {
        'table': 'network_edges',
        'alias': 'ne',
        'columns': [
            'id', 'source_agent_id', 'target_agent_id', 'edge_type',
            'signal_id', 'weight', 'metadata_json', 'created_at',
        ],
        'created_column': 'created_at',
    },
}


def _build_challenge_filters(
    alias: str,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    challenge_key: Optional[str] = None,
    market: Optional[str] = None,
) -> tuple[str, list[Any]]:
    conditions = []
    params: list[Any] = []
    challenge_alias = alias if alias == 'c' else 'c'

    if start_at:
        conditions.append(f"{challenge_alias}.end_at >= ?")
        params.append(start_at)
    if end_at:
        conditions.append(f"{challenge_alias}.start_at <= ?")
        params.append(end_at)
    if experiment_key:
        conditions.append(f"{challenge_alias}.experiment_key = ?")
        params.append(experiment_key)
    if challenge_key:
        conditions.append(f"{challenge_alias}.challenge_key = ?")
        params.append(challenge_key)
    if market:
        conditions.append(f"{challenge_alias}.market = ?")
        params.append(market)

    return (' WHERE ' + ' AND '.join(conditions)) if conditions else '', params


def _build_team_filters(
    alias: str,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    mission_key: Optional[str] = None,
    market: Optional[str] = None,
) -> tuple[str, list[Any]]:
    conditions = []
    params: list[Any] = []
    mission_alias = alias if alias == 'tm' else 'tm'

    if start_at:
        conditions.append(f"{mission_alias}.submission_due_at >= ?")
        params.append(start_at)
    if end_at:
        conditions.append(f"{mission_alias}.start_at <= ?")
        params.append(end_at)
    if experiment_key:
        conditions.append(f"{mission_alias}.experiment_key = ?")
        params.append(experiment_key)
    if mission_key:
        conditions.append(f"{mission_alias}.mission_key = ?")
        params.append(mission_key)
    if market:
        conditions.append(f"{mission_alias}.market = ?")
        params.append(market)

    return (' WHERE ' + ' AND '.join(conditions)) if conditions else '', params


def _build_research_filters(
    alias: str,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    market: Optional[str] = None,
    created_column: str = 'created_at',
) -> tuple[str, list[Any]]:
    conditions = []
    params: list[Any] = []
    created_expr = f"{alias}.{created_column}"

    if start_at:
        conditions.append(f"{created_expr} >= ?")
        params.append(start_at)
    if end_at:
        conditions.append(f"{created_expr} <= ?")
        params.append(end_at)
    if alias == 'ee':
        if experiment_key:
            conditions.append("ee.experiment_key = ?")
            params.append(experiment_key)
        if variant_key:
            conditions.append("ee.variant_key = ?")
            params.append(variant_key)
        if market:
            conditions.append("ee.market = ?")
            params.append(market)
    elif alias == 'a':
        if experiment_key:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM experiment_assignments ea
                    WHERE ea.unit_type = 'agent'
                      AND ea.unit_id = a.id
                      AND ea.experiment_key = ?
                )
                """
            )
            params.append(experiment_key)
        if variant_key:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM experiment_assignments ea
                    WHERE ea.unit_type = 'agent'
                      AND ea.unit_id = a.id
                      AND ea.variant_key = ?
                )
                """
            )
            params.append(variant_key)
        if market:
            conditions.append("EXISTS (SELECT 1 FROM signals s WHERE s.agent_id = a.id AND s.market = ?)")
            params.append(market)
    elif alias == 's':
        if market:
            conditions.append("s.market = ?")
            params.append(market)
        if experiment_key:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM experiment_events ee
                    WHERE ee.object_type = 'signal'
                      AND ee.object_id = CAST(s.signal_id AS TEXT)
                      AND ee.experiment_key = ?
                )
                """
            )
            params.append(experiment_key)
        if variant_key:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM experiment_events ee
                    WHERE ee.object_type = 'signal'
                      AND ee.object_id = CAST(s.signal_id AS TEXT)
                      AND ee.variant_key = ?
                )
                """
            )
            params.append(variant_key)
    elif alias == 'ne':
        if market:
            conditions.append("EXISTS (SELECT 1 FROM signals s WHERE s.signal_id = ne.signal_id AND s.market = ?)")
            params.append(market)
        if experiment_key:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM experiment_assignments ea
                    WHERE ea.unit_type = 'agent'
                      AND ea.experiment_key = ?
                      AND (ea.unit_id = ne.source_agent_id OR ea.unit_id = ne.target_agent_id)
                )
                """
            )
            params.append(experiment_key)
        if variant_key:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM experiment_assignments ea
                    WHERE ea.unit_type = 'agent'
                      AND ea.variant_key = ?
                      AND (ea.unit_id = ne.source_agent_id OR ea.unit_id = ne.target_agent_id)
                )
                """
            )
            params.append(variant_key)

    return (' WHERE ' + ' AND '.join(conditions)) if conditions else '', params


def fetch_challenge_export_rows(
    filename: str,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    challenge_key: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 100000,
    offset: int = 0,
) -> tuple[list[str], list[dict[str, Any]]]:
    config = CHALLENGE_EXPORTS.get(filename)
    if not config:
        raise ValueError(f'Unsupported challenge export: {filename}')

    alias = config['alias']
    columns = config['columns']
    select_columns = ', '.join(f'{alias}.{column} AS {column}' for column in columns)
    join = f" {config['join']}" if config.get('join') else ''
    where, params = _build_challenge_filters(
        alias,
        start_at=start_at,
        end_at=end_at,
        experiment_key=experiment_key,
        challenge_key=challenge_key,
        market=market,
    )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT {select_columns}
        FROM {config['table']} {alias}
        {join}
        {where}
        ORDER BY {alias}.id
        LIMIT ? OFFSET ?
        """,
        params + [max(1, min(limit, 100000)), max(0, offset)],
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return columns, rows


def fetch_research_export_rows(
    filename: str,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 100000,
    offset: int = 0,
) -> tuple[list[str], list[dict[str, Any]]]:
    config = RESEARCH_EXPORTS.get(filename)
    if not config:
        raise ValueError(f'Unsupported research export: {filename}')

    alias = config['alias']
    columns = config['columns']
    select_columns = ', '.join(f'{alias}.{column} AS {column}' for column in columns)
    where, params = _build_research_filters(
        alias,
        start_at=start_at,
        end_at=end_at,
        experiment_key=experiment_key,
        variant_key=variant_key,
        market=market,
        created_column=config.get('created_column', 'created_at'),
    )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT {select_columns}
        FROM {config['table']} {alias}
        {where}
        ORDER BY {alias}.id
        LIMIT ? OFFSET ?
        """,
        params + [max(1, min(limit, 100000)), max(0, offset)],
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return columns, rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def export_challenge_tables(
    output_dir: str | Path,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    challenge_key: Optional[str] = None,
    market: Optional[str] = None,
) -> dict[str, str]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    for filename in CHALLENGE_EXPORTS:
        columns, rows = fetch_challenge_export_rows(
            filename,
            start_at=start_at,
            end_at=end_at,
            experiment_key=experiment_key,
            challenge_key=challenge_key,
            market=market,
        )
        path = target_dir / filename
        write_csv(path, columns, rows)
        written[filename] = str(path)

    return written


# Research pipeline export layer v2.
#
# This block intentionally overrides the early challenge/team-only helpers above.
# It keeps their public function names while adding the broader paper dataset
# contract: all research datasets, default anonymization, content gating,
# metadata redaction, schema generation, agent allowlists, and generic filters.

import hashlib as _hashlib
import json as _json
import os as _os
from typing import Iterable as _Iterable


EXPORT_VERSION = "2026-05-06"
HASH_SALT = _os.getenv("RESEARCH_EXPORT_HASH_SALT", "ai-trader-research-v1")

SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "bearer",
    "cookie",
    "email",
    "jwt",
    "pass",
    "password",
    "private_key",
    "reset",
    "secret",
    "session",
    "token",
    "wallet",
}
CONTENT_COLUMNS = {
    "body",
    "content",
    "description",
    "invalid_if",
    "message",
    "prompt",
    "reason",
    "response",
    "summary_text",
    "text",
    "title",
}
JSON_COLUMNS = {
    "evidence_json",
    "metadata_json",
    "metrics_json",
    "prediction_json",
    "required_roles_json",
    "rules_json",
    "symbols",
    "tags",
    "variants_json",
}


def _signal_experiment_expr(alias: str, field: str) -> str:
    return (
        f"(SELECT ee.{field} FROM experiment_events ee "
        f"WHERE ee.object_type = 'signal' "
        f"AND ee.object_id = CAST({alias}.signal_id AS TEXT) "
        f"AND ee.{field} IS NOT NULL "
        f"ORDER BY ee.created_at DESC, ee.id DESC LIMIT 1)"
    )


def _edge_assignment_expr(alias: str, field: str) -> str:
    return (
        f"(SELECT ea.{field} FROM experiment_assignments ea "
        f"WHERE ea.unit_type = 'agent' "
        f"AND (ea.unit_id = {alias}.source_agent_id OR ea.unit_id = {alias}.target_agent_id) "
        f"AND ea.{field} IS NOT NULL "
        f"ORDER BY ea.created_at DESC, ea.id DESC LIMIT 1)"
    )


PRIMARY_RESEARCH_DATASETS = [
    "agents.csv",
    "events.csv",
    "signals.csv",
    "signal_replies.csv",
    "predictions.csv",
    "quality_scores.csv",
    "trades.csv",
    "positions.csv",
    "profit_history.csv",
    "subscriptions.csv",
    "rewards.csv",
    "experiment_assignments.csv",
    "challenges.csv",
    "challenge_results.csv",
    "team_missions.csv",
    "team_results.csv",
    "network_edges.csv",
]
CHALLENGE_DATASETS = [
    "challenges.csv",
    "challenge_participants.csv",
    "challenge_submissions.csv",
    "challenge_trades.csv",
    "challenge_results.csv",
]
TEAM_DATASETS = [
    "team_missions.csv",
    "teams.csv",
    "team_members.csv",
    "team_messages.csv",
    "team_submissions.csv",
    "team_contributions.csv",
    "team_results.csv",
]


RESEARCH_EXPORTS = {
    "agents.csv": {
        "table": "agents",
        "alias": "a",
        "selects": [
            ("agent_id", "a.id"), ("agent_hash", "a.id"), ("name", "a.name"),
            ("points", "a.points"), ("cash", "a.cash"), ("deposited", "a.deposited"),
            ("reputation_score", "a.reputation_score"), ("created_at", "a.created_at"),
            ("updated_at", "a.updated_at"),
        ],
        "time_column": "a.created_at",
        "agent_id_columns": ["a.id"],
        "market_filter": "EXISTS (SELECT 1 FROM signals s WHERE s.agent_id = a.id AND s.market = ?)",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.unit_id = a.id AND ea.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.unit_id = a.id AND ea.variant_key = ?)",
        "order_by": "a.id",
    },
    "events.csv": {
        "table": "experiment_events",
        "alias": "ee",
        "selects": [
            ("id", "ee.id"), ("event_id", "ee.event_id"), ("event_type", "ee.event_type"),
            ("actor_agent_id", "ee.actor_agent_id"), ("actor_agent_hash", "ee.actor_agent_id"),
            ("target_agent_id", "ee.target_agent_id"), ("target_agent_hash", "ee.target_agent_id"),
            ("object_type", "ee.object_type"), ("object_id", "ee.object_id"), ("market", "ee.market"),
            ("experiment_key", "ee.experiment_key"), ("variant_key", "ee.variant_key"),
            ("metadata_json", "ee.metadata_json"), ("created_at", "ee.created_at"),
        ],
        "time_column": "ee.created_at",
        "agent_id_columns": ["ee.actor_agent_id", "ee.target_agent_id"],
        "market_column": "ee.market",
        "experiment_column": "ee.experiment_key",
        "variant_column": "ee.variant_key",
        "order_by": "ee.id",
    },
    "signals.csv": {
        "table": "signals",
        "alias": "s",
        "selects": [
            ("id", "s.id"), ("signal_id", "s.signal_id"), ("agent_id", "s.agent_id"),
            ("agent_hash", "s.agent_id"), ("message_type", "s.message_type"), ("market", "s.market"),
            ("signal_type", "s.signal_type"), ("symbol", "s.symbol"), ("token_id", "s.token_id"),
            ("outcome", "s.outcome"), ("symbols", "s.symbols"), ("side", "s.side"),
            ("entry_price", "s.entry_price"), ("exit_price", "s.exit_price"), ("quantity", "s.quantity"),
            ("pnl", "s.pnl"), ("title", "s.title"), ("content", "s.content"), ("tags", "s.tags"),
            ("timestamp", "s.timestamp"), ("created_at", "s.created_at"), ("executed_at", "s.executed_at"),
            ("accepted_reply_id", "s.accepted_reply_id"),
            ("experiment_key", _signal_experiment_expr("s", "experiment_key")),
            ("variant_key", _signal_experiment_expr("s", "variant_key")),
        ],
        "time_column": "s.created_at",
        "agent_id_columns": ["s.agent_id"],
        "market_column": "s.market",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(s.signal_id AS TEXT) AND ee.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(s.signal_id AS TEXT) AND ee.variant_key = ?)",
        "order_by": "s.id",
    },
    "signal_replies.csv": {
        "table": "signal_replies",
        "alias": "sr",
        "join": "LEFT JOIN signals s ON s.signal_id = sr.signal_id",
        "selects": [
            ("id", "sr.id"), ("signal_id", "sr.signal_id"), ("agent_id", "sr.agent_id"),
            ("agent_hash", "sr.agent_id"), ("parent_agent_id", "s.agent_id"),
            ("parent_agent_hash", "s.agent_id"), ("content", "sr.content"), ("accepted", "sr.accepted"),
            ("created_at", "sr.created_at"), ("market", "s.market"),
            ("experiment_key", _signal_experiment_expr("s", "experiment_key")),
            ("variant_key", _signal_experiment_expr("s", "variant_key")),
        ],
        "time_column": "sr.created_at",
        "agent_id_columns": ["sr.agent_id", "s.agent_id"],
        "market_column": "s.market",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(s.signal_id AS TEXT) AND ee.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(s.signal_id AS TEXT) AND ee.variant_key = ?)",
        "order_by": "sr.id",
    },
    "predictions.csv": {
        "table": "signal_predictions",
        "alias": "sp",
        "join": "LEFT JOIN signals s ON s.signal_id = sp.signal_id",
        "selects": [
            ("id", "sp.id"), ("signal_id", "sp.signal_id"), ("agent_id", "sp.agent_id"),
            ("agent_hash", "sp.agent_id"), ("market", "COALESCE(sp.market, s.market)"),
            ("symbol", "COALESCE(sp.symbol, s.symbol)"), ("direction", "sp.direction"),
            ("target_price", "sp.target_price"), ("target_probability", "sp.target_probability"),
            ("confidence", "sp.confidence"), ("horizon_start_at", "sp.horizon_start_at"),
            ("horizon_end_at", "sp.horizon_end_at"), ("invalid_if", "sp.invalid_if"),
            ("evidence_json", "sp.evidence_json"), ("extracted_by", "sp.extracted_by"),
            ("created_at", "sp.created_at"),
            ("experiment_key", _signal_experiment_expr("s", "experiment_key")),
            ("variant_key", _signal_experiment_expr("s", "variant_key")),
        ],
        "time_column": "sp.created_at",
        "agent_id_columns": ["sp.agent_id"],
        "market_column": "COALESCE(sp.market, s.market)",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(sp.signal_id AS TEXT) AND ee.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(sp.signal_id AS TEXT) AND ee.variant_key = ?)",
        "order_by": "sp.id",
    },
    "quality_scores.csv": {
        "table": "signal_quality_scores",
        "alias": "sqs",
        "join": "LEFT JOIN signals s ON s.signal_id = sqs.signal_id",
        "selects": [
            ("id", "sqs.id"), ("signal_id", "sqs.signal_id"), ("agent_id", "sqs.agent_id"),
            ("agent_hash", "sqs.agent_id"), ("verifiability_score", "sqs.verifiability_score"),
            ("evidence_score", "sqs.evidence_score"), ("specificity_score", "sqs.specificity_score"),
            ("novelty_score", "sqs.novelty_score"), ("review_score", "sqs.review_score"),
            ("overall_score", "sqs.overall_score"), ("model_version", "sqs.model_version"),
            ("metadata_json", "sqs.metadata_json"), ("created_at", "sqs.created_at"),
            ("market", "s.market"), ("experiment_key", _signal_experiment_expr("s", "experiment_key")),
            ("variant_key", _signal_experiment_expr("s", "variant_key")),
        ],
        "time_column": "sqs.created_at",
        "agent_id_columns": ["sqs.agent_id"],
        "market_column": "s.market",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(sqs.signal_id AS TEXT) AND ee.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(sqs.signal_id AS TEXT) AND ee.variant_key = ?)",
        "order_by": "sqs.id",
    },
    "trades.csv": {
        "table": "signals",
        "alias": "s",
        "base_where": "s.message_type = 'operation'",
        "selects": [
            ("trade_id", "s.signal_id"), ("signal_row_id", "s.id"), ("agent_id", "s.agent_id"),
            ("agent_hash", "s.agent_id"), ("market", "s.market"), ("symbol", "s.symbol"),
            ("token_id", "s.token_id"), ("outcome", "s.outcome"), ("side", "s.side"),
            ("entry_price", "s.entry_price"), ("exit_price", "s.exit_price"), ("quantity", "s.quantity"),
            ("pnl", "s.pnl"), ("executed_at", "s.executed_at"), ("created_at", "s.created_at"),
            ("content", "s.content"), ("experiment_key", _signal_experiment_expr("s", "experiment_key")),
            ("variant_key", _signal_experiment_expr("s", "variant_key")),
        ],
        "time_column": "COALESCE(s.executed_at, s.created_at)",
        "agent_id_columns": ["s.agent_id"],
        "market_column": "s.market",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(s.signal_id AS TEXT) AND ee.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_events ee WHERE ee.object_type = 'signal' AND ee.object_id = CAST(s.signal_id AS TEXT) AND ee.variant_key = ?)",
        "order_by": "s.id",
    },
    "positions.csv": {
        "table": "positions",
        "alias": "p",
        "selects": [
            ("id", "p.id"), ("agent_id", "p.agent_id"), ("agent_hash", "p.agent_id"),
            ("leader_id", "p.leader_id"), ("leader_hash", "p.leader_id"), ("market", "p.market"),
            ("symbol", "p.symbol"), ("token_id", "p.token_id"), ("outcome", "p.outcome"),
            ("side", "p.side"), ("quantity", "p.quantity"), ("entry_price", "p.entry_price"),
            ("current_price", "p.current_price"), ("opened_at", "p.opened_at"),
        ],
        "time_column": "p.opened_at",
        "agent_id_columns": ["p.agent_id", "p.leader_id"],
        "market_column": "p.market",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.experiment_key = ? AND (ea.unit_id = p.agent_id OR ea.unit_id = p.leader_id))",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.variant_key = ? AND (ea.unit_id = p.agent_id OR ea.unit_id = p.leader_id))",
        "order_by": "p.id",
    },
    "profit_history.csv": {
        "table": "profit_history",
        "alias": "ph",
        "selects": [
            ("id", "ph.id"), ("agent_id", "ph.agent_id"), ("agent_hash", "ph.agent_id"),
            ("total_value", "ph.total_value"), ("cash", "ph.cash"), ("position_value", "ph.position_value"),
            ("profit", "ph.profit"), ("recorded_at", "ph.recorded_at"),
        ],
        "time_column": "ph.recorded_at",
        "agent_id_columns": ["ph.agent_id"],
        "market_filter": "EXISTS (SELECT 1 FROM signals s WHERE s.agent_id = ph.agent_id AND s.market = ?)",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.unit_id = ph.agent_id AND ea.experiment_key = ?)",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.unit_id = ph.agent_id AND ea.variant_key = ?)",
        "order_by": "ph.id",
    },
    "subscriptions.csv": {
        "table": "subscriptions",
        "alias": "sub",
        "selects": [
            ("id", "sub.id"), ("leader_id", "sub.leader_id"), ("leader_hash", "sub.leader_id"),
            ("follower_id", "sub.follower_id"), ("follower_hash", "sub.follower_id"),
            ("status", "sub.status"), ("created_at", "sub.created_at"),
        ],
        "time_column": "sub.created_at",
        "agent_id_columns": ["sub.leader_id", "sub.follower_id"],
        "market_filter": "EXISTS (SELECT 1 FROM signals s WHERE s.market = ? AND (s.agent_id = sub.leader_id OR s.agent_id = sub.follower_id))",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.experiment_key = ? AND (ea.unit_id = sub.leader_id OR ea.unit_id = sub.follower_id))",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.variant_key = ? AND (ea.unit_id = sub.leader_id OR ea.unit_id = sub.follower_id))",
        "order_by": "sub.id",
    },
    "rewards.csv": {
        "table": "agent_reward_ledger",
        "alias": "arl",
        "selects": [
            ("id", "arl.id"), ("agent_id", "arl.agent_id"), ("agent_hash", "arl.agent_id"),
            ("amount", "arl.amount"), ("reason", "arl.reason"), ("source_type", "arl.source_type"),
            ("source_id", "arl.source_id"), ("experiment_key", "arl.experiment_key"),
            ("variant_key", "arl.variant_key"), ("status", "arl.status"),
            ("metadata_json", "arl.metadata_json"), ("created_at", "arl.created_at"),
            ("reversed_at", "arl.reversed_at"),
        ],
        "time_column": "arl.created_at",
        "agent_id_columns": ["arl.agent_id"],
        "market_filter": "EXISTS (SELECT 1 FROM signals s WHERE s.agent_id = arl.agent_id AND s.market = ?)",
        "experiment_column": "arl.experiment_key",
        "variant_column": "arl.variant_key",
        "order_by": "arl.id",
    },
    "experiment_assignments.csv": {
        "table": "experiment_assignments",
        "alias": "ea",
        "base_where": "ea.unit_type = 'agent'",
        "selects": [
            ("id", "ea.id"), ("experiment_key", "ea.experiment_key"), ("unit_type", "ea.unit_type"),
            ("unit_id", "ea.unit_id"), ("unit_hash", "ea.unit_id"), ("variant_key", "ea.variant_key"),
            ("assignment_reason", "ea.assignment_reason"), ("metadata_json", "ea.metadata_json"),
            ("created_at", "ea.created_at"),
        ],
        "time_column": "ea.created_at",
        "agent_id_columns": ["ea.unit_id"],
        "experiment_column": "ea.experiment_key",
        "variant_column": "ea.variant_key",
        "market_filter": "EXISTS (SELECT 1 FROM signals s WHERE s.agent_id = ea.unit_id AND s.market = ?)",
        "order_by": "ea.id",
    },
    "challenges.csv": {
        "table": "challenges",
        "alias": "c",
        "selects": [
            ("id", "c.id"), ("challenge_key", "c.challenge_key"), ("title", "c.title"),
            ("description", "c.description"), ("market", "c.market"), ("symbol", "c.symbol"),
            ("challenge_type", "c.challenge_type"), ("status", "c.status"),
            ("scoring_method", "c.scoring_method"), ("initial_capital", "c.initial_capital"),
            ("max_position_pct", "c.max_position_pct"), ("max_drawdown_pct", "c.max_drawdown_pct"),
            ("start_at", "c.start_at"), ("end_at", "c.end_at"), ("settled_at", "c.settled_at"),
            ("rules_json", "c.rules_json"), ("experiment_key", "c.experiment_key"),
            ("created_by_agent_id", "c.created_by_agent_id"), ("created_by_agent_hash", "c.created_by_agent_id"),
            ("created_at", "c.created_at"), ("updated_at", "c.updated_at"),
        ],
        "time_column": "c.created_at",
        "agent_filter_templates": [
            "c.created_by_agent_id IN ({agent_ids})",
            "EXISTS (SELECT 1 FROM challenge_participants cp WHERE cp.challenge_id = c.id AND cp.agent_id IN ({agent_ids}))",
        ],
        "market_column": "c.market",
        "experiment_column": "c.experiment_key",
        "variant_filter": "EXISTS (SELECT 1 FROM challenge_participants cp WHERE cp.challenge_id = c.id AND cp.variant_key = ?)",
        "challenge_key_column": "c.challenge_key",
        "order_by": "c.id",
    },
    "challenge_participants.csv": {
        "table": "challenge_participants",
        "alias": "cp",
        "join": "JOIN challenges c ON c.id = cp.challenge_id",
        "selects": [
            ("id", "cp.id"), ("challenge_id", "cp.challenge_id"), ("challenge_key", "c.challenge_key"),
            ("agent_id", "cp.agent_id"), ("agent_hash", "cp.agent_id"), ("status", "cp.status"),
            ("variant_key", "cp.variant_key"), ("joined_at", "cp.joined_at"),
            ("starting_cash", "cp.starting_cash"), ("ending_value", "cp.ending_value"),
            ("return_pct", "cp.return_pct"), ("max_drawdown", "cp.max_drawdown"),
            ("trade_count", "cp.trade_count"), ("rank", "cp.rank"),
            ("disqualified_reason", "cp.disqualified_reason"), ("experiment_key", "c.experiment_key"),
            ("market", "c.market"),
        ],
        "time_column": "cp.joined_at",
        "agent_id_columns": ["cp.agent_id"],
        "market_column": "c.market",
        "experiment_column": "c.experiment_key",
        "variant_column": "cp.variant_key",
        "challenge_key_column": "c.challenge_key",
        "order_by": "cp.id",
    },
    "challenge_submissions.csv": {
        "table": "challenge_submissions",
        "alias": "cs",
        "join": "JOIN challenges c ON c.id = cs.challenge_id",
        "selects": [
            ("id", "cs.id"), ("challenge_id", "cs.challenge_id"), ("challenge_key", "c.challenge_key"),
            ("agent_id", "cs.agent_id"), ("agent_hash", "cs.agent_id"), ("signal_id", "cs.signal_id"),
            ("submission_type", "cs.submission_type"), ("content", "cs.content"),
            ("prediction_json", "cs.prediction_json"), ("created_at", "cs.created_at"),
            ("experiment_key", "c.experiment_key"), ("market", "c.market"),
        ],
        "time_column": "cs.created_at",
        "agent_id_columns": ["cs.agent_id"],
        "market_column": "c.market",
        "experiment_column": "c.experiment_key",
        "variant_filter": "EXISTS (SELECT 1 FROM challenge_participants cp WHERE cp.challenge_id = cs.challenge_id AND cp.agent_id = cs.agent_id AND cp.variant_key = ?)",
        "challenge_key_column": "c.challenge_key",
        "order_by": "cs.id",
    },
    "challenge_trades.csv": {
        "table": "challenge_trades",
        "alias": "ct",
        "join": "JOIN challenges c ON c.id = ct.challenge_id",
        "selects": [
            ("id", "ct.id"), ("challenge_id", "ct.challenge_id"), ("challenge_key", "c.challenge_key"),
            ("agent_id", "ct.agent_id"), ("agent_hash", "ct.agent_id"),
            ("source_signal_id", "ct.source_signal_id"), ("market", "ct.market"), ("symbol", "ct.symbol"),
            ("side", "ct.side"), ("price", "ct.price"), ("quantity", "ct.quantity"),
            ("executed_at", "ct.executed_at"), ("created_at", "ct.created_at"),
            ("experiment_key", "c.experiment_key"),
        ],
        "time_column": "ct.executed_at",
        "agent_id_columns": ["ct.agent_id"],
        "market_column": "ct.market",
        "experiment_column": "c.experiment_key",
        "variant_filter": "EXISTS (SELECT 1 FROM challenge_participants cp WHERE cp.challenge_id = ct.challenge_id AND cp.agent_id = ct.agent_id AND cp.variant_key = ?)",
        "challenge_key_column": "c.challenge_key",
        "order_by": "ct.id",
    },
    "challenge_results.csv": {
        "table": "challenge_results",
        "alias": "cr",
        "join": "JOIN challenges c ON c.id = cr.challenge_id LEFT JOIN challenge_participants cp ON cp.challenge_id = cr.challenge_id AND cp.agent_id = cr.agent_id",
        "selects": [
            ("id", "cr.id"), ("challenge_id", "cr.challenge_id"), ("challenge_key", "c.challenge_key"),
            ("agent_id", "cr.agent_id"), ("agent_hash", "cr.agent_id"), ("return_pct", "cr.return_pct"),
            ("max_drawdown", "cr.max_drawdown"), ("risk_adjusted_score", "cr.risk_adjusted_score"),
            ("quality_score", "cr.quality_score"), ("final_score", "cr.final_score"),
            ("rank", "cr.rank"), ("metrics_json", "cr.metrics_json"), ("settled_at", "cr.settled_at"),
            ("experiment_key", "c.experiment_key"), ("variant_key", "cp.variant_key"),
            ("market", "c.market"),
        ],
        "time_column": "cr.settled_at",
        "agent_id_columns": ["cr.agent_id"],
        "market_column": "c.market",
        "experiment_column": "c.experiment_key",
        "variant_column": "cp.variant_key",
        "challenge_key_column": "c.challenge_key",
        "order_by": "cr.id",
    },
    "team_missions.csv": {
        "table": "team_missions",
        "alias": "tm",
        "selects": [
            ("id", "tm.id"), ("mission_key", "tm.mission_key"), ("title", "tm.title"),
            ("description", "tm.description"), ("market", "tm.market"), ("symbol", "tm.symbol"),
            ("mission_type", "tm.mission_type"), ("status", "tm.status"),
            ("team_size_min", "tm.team_size_min"), ("team_size_max", "tm.team_size_max"),
            ("assignment_mode", "tm.assignment_mode"), ("required_roles_json", "tm.required_roles_json"),
            ("start_at", "tm.start_at"), ("submission_due_at", "tm.submission_due_at"),
            ("settled_at", "tm.settled_at"), ("rules_json", "tm.rules_json"),
            ("experiment_key", "tm.experiment_key"), ("created_at", "tm.created_at"),
            ("updated_at", "tm.updated_at"),
        ],
        "time_column": "tm.created_at",
        "agent_filter_templates": [
            "EXISTS (SELECT 1 FROM team_mission_participants tmp WHERE tmp.mission_id = tm.id AND tmp.agent_id IN ({agent_ids}))",
            "EXISTS (SELECT 1 FROM teams t JOIN team_members tmem ON tmem.team_id = t.id WHERE t.mission_id = tm.id AND tmem.agent_id IN ({agent_ids}))",
        ],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_filter": "EXISTS (SELECT 1 FROM team_mission_participants tmp WHERE tmp.mission_id = tm.id AND tmp.variant_key = ?) OR EXISTS (SELECT 1 FROM teams t WHERE t.mission_id = tm.id AND t.variant_key = ?)",
        "variant_param_count": 2,
        "mission_key_column": "tm.mission_key",
        "order_by": "tm.id",
    },
    "teams.csv": {
        "table": "teams",
        "alias": "t",
        "join": "JOIN team_missions tm ON tm.id = t.mission_id",
        "selects": [
            ("id", "t.id"), ("mission_id", "t.mission_id"), ("mission_key", "tm.mission_key"),
            ("team_key", "t.team_key"), ("name", "t.name"), ("status", "t.status"),
            ("formation_method", "t.formation_method"), ("variant_key", "t.variant_key"),
            ("created_at", "t.created_at"), ("updated_at", "t.updated_at"),
            ("experiment_key", "tm.experiment_key"), ("market", "tm.market"),
        ],
        "time_column": "t.created_at",
        "agent_filter_templates": [
            "EXISTS (SELECT 1 FROM team_members tmem WHERE tmem.team_id = t.id AND tmem.agent_id IN ({agent_ids}))",
        ],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_column": "t.variant_key",
        "mission_key_column": "tm.mission_key",
        "order_by": "t.id",
    },
    "team_members.csv": {
        "table": "team_members",
        "alias": "tmem",
        "join": "JOIN teams t ON t.id = tmem.team_id JOIN team_missions tm ON tm.id = t.mission_id",
        "selects": [
            ("id", "tmem.id"), ("team_id", "tmem.team_id"), ("team_key", "t.team_key"),
            ("mission_id", "t.mission_id"), ("mission_key", "tm.mission_key"),
            ("agent_id", "tmem.agent_id"), ("agent_hash", "tmem.agent_id"),
            ("role", "tmem.role"), ("status", "tmem.status"), ("joined_at", "tmem.joined_at"),
            ("experiment_key", "tm.experiment_key"), ("variant_key", "t.variant_key"),
            ("market", "tm.market"),
        ],
        "time_column": "tmem.joined_at",
        "agent_id_columns": ["tmem.agent_id"],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_column": "t.variant_key",
        "mission_key_column": "tm.mission_key",
        "order_by": "tmem.id",
    },
    "team_messages.csv": {
        "table": "team_messages",
        "alias": "tmsg",
        "join": "JOIN teams t ON t.id = tmsg.team_id JOIN team_missions tm ON tm.id = t.mission_id",
        "selects": [
            ("id", "tmsg.id"), ("team_id", "tmsg.team_id"), ("team_key", "t.team_key"),
            ("mission_key", "tm.mission_key"), ("agent_id", "tmsg.agent_id"),
            ("agent_hash", "tmsg.agent_id"), ("signal_id", "tmsg.signal_id"),
            ("message_type", "tmsg.message_type"), ("content", "tmsg.content"),
            ("metadata_json", "tmsg.metadata_json"), ("created_at", "tmsg.created_at"),
            ("experiment_key", "tm.experiment_key"), ("variant_key", "t.variant_key"),
            ("market", "tm.market"),
        ],
        "time_column": "tmsg.created_at",
        "agent_id_columns": ["tmsg.agent_id"],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_column": "t.variant_key",
        "mission_key_column": "tm.mission_key",
        "order_by": "tmsg.id",
    },
    "team_submissions.csv": {
        "table": "team_submissions",
        "alias": "ts",
        "join": "JOIN team_missions tm ON tm.id = ts.mission_id JOIN teams t ON t.id = ts.team_id",
        "selects": [
            ("id", "ts.id"), ("mission_id", "ts.mission_id"), ("mission_key", "tm.mission_key"),
            ("team_id", "ts.team_id"), ("team_key", "t.team_key"),
            ("submitted_by_agent_id", "ts.submitted_by_agent_id"),
            ("submitted_by_agent_hash", "ts.submitted_by_agent_id"), ("title", "ts.title"),
            ("content", "ts.content"), ("prediction_json", "ts.prediction_json"),
            ("confidence", "ts.confidence"), ("created_at", "ts.created_at"),
            ("experiment_key", "tm.experiment_key"), ("variant_key", "t.variant_key"),
            ("market", "tm.market"),
        ],
        "time_column": "ts.created_at",
        "agent_id_columns": ["ts.submitted_by_agent_id"],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_column": "t.variant_key",
        "mission_key_column": "tm.mission_key",
        "order_by": "ts.id",
    },
    "team_contributions.csv": {
        "table": "team_contributions",
        "alias": "tc",
        "join": "JOIN team_missions tm ON tm.id = tc.mission_id JOIN teams t ON t.id = tc.team_id",
        "selects": [
            ("id", "tc.id"), ("mission_id", "tc.mission_id"), ("mission_key", "tm.mission_key"),
            ("team_id", "tc.team_id"), ("team_key", "t.team_key"), ("agent_id", "tc.agent_id"),
            ("agent_hash", "tc.agent_id"), ("source_type", "tc.source_type"), ("source_id", "tc.source_id"),
            ("contribution_type", "tc.contribution_type"), ("contribution_score", "tc.contribution_score"),
            ("metadata_json", "tc.metadata_json"), ("created_at", "tc.created_at"),
            ("experiment_key", "tm.experiment_key"), ("variant_key", "t.variant_key"),
            ("market", "tm.market"),
        ],
        "time_column": "tc.created_at",
        "agent_id_columns": ["tc.agent_id"],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_column": "t.variant_key",
        "mission_key_column": "tm.mission_key",
        "order_by": "tc.id",
    },
    "team_results.csv": {
        "table": "team_results",
        "alias": "tr",
        "join": "JOIN team_missions tm ON tm.id = tr.mission_id JOIN teams t ON t.id = tr.team_id",
        "selects": [
            ("id", "tr.id"), ("mission_id", "tr.mission_id"), ("mission_key", "tm.mission_key"),
            ("team_id", "tr.team_id"), ("team_key", "t.team_key"), ("return_pct", "tr.return_pct"),
            ("prediction_score", "tr.prediction_score"), ("quality_score", "tr.quality_score"),
            ("consensus_gain", "tr.consensus_gain"), ("final_score", "tr.final_score"),
            ("rank", "tr.rank"), ("metrics_json", "tr.metrics_json"), ("settled_at", "tr.settled_at"),
            ("experiment_key", "tm.experiment_key"), ("variant_key", "t.variant_key"),
            ("market", "tm.market"),
        ],
        "time_column": "tr.settled_at",
        "agent_filter_templates": [
            "EXISTS (SELECT 1 FROM team_members tmem WHERE tmem.team_id = tr.team_id AND tmem.agent_id IN ({agent_ids}))",
        ],
        "market_column": "tm.market",
        "experiment_column": "tm.experiment_key",
        "variant_column": "t.variant_key",
        "mission_key_column": "tm.mission_key",
        "order_by": "tr.id",
    },
    "network_edges.csv": {
        "table": "network_edges",
        "alias": "ne",
        "selects": [
            ("id", "ne.id"), ("source_agent_id", "ne.source_agent_id"),
            ("source_agent_hash", "ne.source_agent_id"), ("target_agent_id", "ne.target_agent_id"),
            ("target_agent_hash", "ne.target_agent_id"), ("edge_type", "ne.edge_type"),
            ("signal_id", "ne.signal_id"), ("weight", "ne.weight"),
            ("first_seen_at", "ne.created_at"), ("last_seen_at", "ne.created_at"),
            ("experiment_key", _edge_assignment_expr("ne", "experiment_key")),
            ("variant_key", _edge_assignment_expr("ne", "variant_key")),
            ("metadata_json", "ne.metadata_json"),
        ],
        "time_column": "ne.created_at",
        "agent_id_columns": ["ne.source_agent_id", "ne.target_agent_id"],
        "market_filter": "EXISTS (SELECT 1 FROM signals s WHERE s.signal_id = ne.signal_id AND s.market = ?)",
        "experiment_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.experiment_key = ? AND (ea.unit_id = ne.source_agent_id OR ea.unit_id = ne.target_agent_id))",
        "variant_filter": "EXISTS (SELECT 1 FROM experiment_assignments ea WHERE ea.unit_type = 'agent' AND ea.variant_key = ? AND (ea.unit_id = ne.source_agent_id OR ea.unit_id = ne.target_agent_id))",
        "order_by": "ne.id",
    },
}

CHALLENGE_EXPORTS = {name: RESEARCH_EXPORTS[name] for name in CHALLENGE_DATASETS}
TEAM_MISSION_EXPORTS = {name: RESEARCH_EXPORTS[name] for name in TEAM_DATASETS}
ALL_RESEARCH_DATASETS = list(RESEARCH_EXPORTS)


def normalize_dataset_name(dataset_name: str) -> str:
    normalized = dataset_name.strip().lower()
    if normalized.endswith(".json"):
        normalized = normalized[:-5]
    if normalized.endswith(".csv"):
        return normalized
    return f"{normalized}.csv"


def get_research_dataset_names(primary_only: bool = False) -> list[str]:
    return list(PRIMARY_RESEARCH_DATASETS if primary_only else ALL_RESEARCH_DATASETS)


def get_research_export_columns(dataset_name: str) -> list[str]:
    filename = normalize_dataset_name(dataset_name)
    config = RESEARCH_EXPORTS.get(filename)
    if not config:
        raise ValueError(f"Unsupported research export: {dataset_name}")
    return [name for name, _expr in config["selects"]]


def _hash_value(namespace: str, value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    digest = _hashlib.sha256(f"{HASH_SALT}:{namespace}:{value}".encode("utf-8")).hexdigest()
    return f"sha256:{digest[:24]}"


def _hash_agent_id(value: Any) -> Optional[str]:
    return _hash_value("agent", value)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _sanitize_json_value(value: Any, *, include_content: bool) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            if not include_content and str(key).lower() in CONTENT_COLUMNS:
                sanitized[key] = _hash_value(f"metadata.{key}", item)
                continue
            sanitized[key] = _sanitize_json_value(item, include_content=include_content)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_json_value(item, include_content=include_content) for item in value]
    return value


def _sanitize_json_string(value: Any, *, include_content: bool) -> Any:
    if value in (None, ""):
        return value
    try:
        parsed = _json.loads(value) if isinstance(value, str) else value
    except Exception:
        return value if include_content else _hash_value("json_text", value)
    sanitized = _sanitize_json_value(parsed, include_content=include_content)
    return _json.dumps(sanitized, ensure_ascii=False, sort_keys=True, default=str)


def _postprocess_row(row: dict[str, Any], columns: list[str], *, anonymize: bool, include_content: bool) -> dict[str, Any]:
    processed: dict[str, Any] = {}
    for column in columns:
        value = row.get(column)
        if column.endswith("_hash") or column == "unit_hash":
            processed[column] = _hash_agent_id(value)
        elif column == "name" and anonymize:
            processed[column] = _hash_value("name", value)
        elif column in JSON_COLUMNS or column.endswith("_json"):
            processed[column] = _sanitize_json_string(value, include_content=include_content)
        elif not include_content and column.lower() in CONTENT_COLUMNS:
            processed[column] = _hash_value(column, value)
        else:
            processed[column] = value
    return processed


def _coerce_agent_ids(agent_ids: Optional[_Iterable[int] | str]) -> list[int]:
    if not agent_ids:
        return []
    values = [part.strip() for part in agent_ids.split(",") if part.strip()] if isinstance(agent_ids, str) else list(agent_ids)
    return [int(value) for value in values]


def _append_in_filter(conditions: list[str], params: list[Any], columns: list[str], values: list[int]) -> None:
    if not columns or not values:
        return
    placeholders = ", ".join("?" for _ in values)
    conditions.append("(" + " OR ".join(f"{column} IN ({placeholders})" for column in columns) + ")")
    for _column in columns:
        params.extend(values)


def _append_agent_filter_templates(
    conditions: list[str],
    params: list[Any],
    templates: list[str],
    values: list[int],
) -> None:
    if not templates or not values:
        return
    placeholders = ", ".join("?" for _ in values)
    conditions.append("(" + " OR ".join(template.format(agent_ids=placeholders) for template in templates) + ")")
    for _template in templates:
        params.extend(values)


def _build_filters_v2(
    config: dict[str, Any],
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    market: Optional[str] = None,
    agent_ids: Optional[_Iterable[int] | str] = None,
    challenge_key: Optional[str] = None,
    mission_key: Optional[str] = None,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if config.get("base_where"):
        conditions.append(config["base_where"])
    if start_at and config.get("time_column"):
        conditions.append(f"{config['time_column']} >= ?")
        params.append(start_at)
    if end_at and config.get("time_column"):
        conditions.append(f"{config['time_column']} <= ?")
        params.append(end_at)
    if experiment_key:
        if config.get("experiment_column"):
            conditions.append(f"{config['experiment_column']} = ?")
        elif config.get("experiment_filter"):
            conditions.append(config["experiment_filter"])
        params.append(experiment_key)
    if variant_key:
        if config.get("variant_column"):
            conditions.append(f"{config['variant_column']} = ?")
            params.append(variant_key)
        elif config.get("variant_filter"):
            conditions.append(config["variant_filter"])
            params.extend([variant_key] * int(config.get("variant_param_count", 1)))
    if market:
        if config.get("market_column"):
            conditions.append(f"{config['market_column']} = ?")
        elif config.get("market_filter"):
            conditions.append(config["market_filter"])
        params.append(market)
    if challenge_key and config.get("challenge_key_column"):
        conditions.append(f"{config['challenge_key_column']} = ?")
        params.append(challenge_key)
    if mission_key and config.get("mission_key_column"):
        conditions.append(f"{config['mission_key_column']} = ?")
        params.append(mission_key)
    agent_id_values = _coerce_agent_ids(agent_ids)
    _append_in_filter(conditions, params, config.get("agent_id_columns", []), agent_id_values)
    _append_agent_filter_templates(conditions, params, config.get("agent_filter_templates", []), agent_id_values)
    return (" WHERE " + " AND ".join(conditions)) if conditions else "", params


def fetch_research_export_rows(
    filename: str,
    *,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    market: Optional[str] = None,
    agent_ids: Optional[_Iterable[int] | str] = None,
    anonymize: bool = True,
    include_content: bool = True,
    challenge_key: Optional[str] = None,
    mission_key: Optional[str] = None,
    limit: int = 100000,
    offset: int = 0,
) -> tuple[list[str], list[dict[str, Any]]]:
    filename = normalize_dataset_name(filename)
    config = RESEARCH_EXPORTS.get(filename)
    if not config:
        raise ValueError(f"Unsupported research export: {filename}")

    columns = get_research_export_columns(filename)
    select_columns = ", ".join(f"{expr} AS {name}" for name, expr in config["selects"])
    join = f" {config['join']}" if config.get("join") else ""
    where, params = _build_filters_v2(
        config,
        start_at=start_at,
        end_at=end_at,
        experiment_key=experiment_key,
        variant_key=variant_key,
        market=market,
        agent_ids=agent_ids,
        challenge_key=challenge_key,
        mission_key=mission_key,
    )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT {select_columns}
        FROM {config['table']} {config['alias']}
        {join}
        {where}
        ORDER BY {config.get('order_by', config['alias'] + '.id')}
        LIMIT ? OFFSET ?
        """,
        params + [max(1, min(int(limit), 100000)), max(0, int(offset))],
    )
    rows = [
        _postprocess_row(dict(row), columns, anonymize=anonymize, include_content=include_content)
        for row in cursor.fetchall()
    ]
    conn.close()
    return columns, rows


def research_schema_for_dataset(dataset_name: str) -> dict[str, Any]:
    filename = normalize_dataset_name(dataset_name)
    columns = get_research_export_columns(filename)
    numeric_columns = {
        "amount", "cash", "confidence", "consensus_gain", "contribution_score",
        "current_price", "deposited", "ending_value", "entry_price", "exit_price",
        "final_score", "initial_capital", "max_drawdown", "max_drawdown_pct",
        "max_position_pct", "novelty_score", "overall_score", "pnl", "points",
        "position_value", "prediction_score", "price", "profit", "quality_score",
        "quantity", "return_pct", "review_score", "risk_adjusted_score",
        "specificity_score", "starting_cash", "target_price", "target_probability",
        "total_value", "trade_count", "verifiability_score", "weight",
    }
    properties = {}
    for column in columns:
        if column.endswith("_id") or column in {"id", "rank", "signal_row_id", "timestamp"}:
            properties[column] = {"type": ["integer", "null"]}
        elif column in numeric_columns or column.endswith("_score") or column.endswith("_pct"):
            properties[column] = {"type": ["number", "integer", "null"]}
        else:
            properties[column] = {"type": ["string", "number", "integer", "boolean", "null"]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://ai-trader.local/research/schemas/{filename[:-4]}.schema.json",
        "title": f"{filename} research export row",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": columns,
        "x-export-version": EXPORT_VERSION,
        "x-default-anonymized": True,
    }


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        _json.dump(rows, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def write_research_schemas(output_dir: str | Path, dataset_names: Optional[_Iterable[str]] = None) -> dict[str, str]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for dataset_name in dataset_names or get_research_dataset_names():
        filename = normalize_dataset_name(dataset_name)
        path = target_dir / f"{filename[:-4]}.schema.json"
        with path.open("w", encoding="utf-8") as handle:
            _json.dump(research_schema_for_dataset(filename), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        written[filename] = str(path)
    return written


def export_research_dataset(
    output_dir: str | Path,
    *,
    dataset_names: Optional[_Iterable[str]] = None,
    output_format: str = "csv",
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    market: Optional[str] = None,
    agent_ids: Optional[_Iterable[int] | str] = None,
    anonymize: bool = True,
    include_content: bool = True,
    limit: int = 100000,
) -> dict[str, str]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    fmt = output_format.lower()
    if fmt not in {"csv", "json"}:
        raise ValueError("output_format must be csv or json")
    written: dict[str, str] = {}
    for dataset_name in dataset_names or get_research_dataset_names(primary_only=True):
        filename = normalize_dataset_name(dataset_name)
        columns, rows = fetch_research_export_rows(
            filename,
            start_at=start_at,
            end_at=end_at,
            experiment_key=experiment_key,
            variant_key=variant_key,
            market=market,
            agent_ids=agent_ids,
            anonymize=anonymize,
            include_content=include_content,
            limit=limit,
        )
        path = target_dir / (filename if fmt == "csv" else f"{filename[:-4]}.json")
        if fmt == "csv":
            write_csv(path, columns, rows)
        else:
            write_json(path, rows)
        written[filename] = str(path)
    return written


def _export_single_research_file(output_dir: str | Path, filename: str, **filters: Any) -> str:
    columns, rows = fetch_research_export_rows(filename, **filters)
    path = Path(output_dir) / normalize_dataset_name(filename)
    write_csv(path, columns, rows)
    return str(path)


def export_agents_csv(output_dir: str | Path, **filters: Any) -> str:
    return _export_single_research_file(output_dir, "agents.csv", **filters)


def export_events_csv(output_dir: str | Path, **filters: Any) -> str:
    return _export_single_research_file(output_dir, "events.csv", **filters)


def export_signals_csv(output_dir: str | Path, **filters: Any) -> str:
    return _export_single_research_file(output_dir, "signals.csv", **filters)


def export_network_edges_csv(output_dir: str | Path, **filters: Any) -> str:
    return _export_single_research_file(output_dir, "network_edges.csv", **filters)


def fetch_challenge_export_rows(filename: str, **filters: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if normalize_dataset_name(filename) not in CHALLENGE_EXPORTS:
        raise ValueError(f"Unsupported challenge export: {filename}")
    return fetch_research_export_rows(filename, **filters)


def export_challenge_tables(output_dir: str | Path, **filters: Any) -> dict[str, str]:
    return {filename: _export_single_research_file(output_dir, filename, **filters) for filename in CHALLENGE_DATASETS}


def fetch_team_export_rows(filename: str, **filters: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if normalize_dataset_name(filename) not in TEAM_MISSION_EXPORTS:
        raise ValueError(f"Unsupported team mission export: {filename}")
    return fetch_research_export_rows(filename, **filters)


def export_team_tables(output_dir: str | Path, **filters: Any) -> dict[str, str]:
    return {filename: _export_single_research_file(output_dir, filename, **filters) for filename in TEAM_DATASETS}

#!/usr/bin/env python3
"""
One-off migration from the local SQLite database to PostgreSQL.

Usage:
    DATABASE_URL=postgresql://... python service/server/scripts/migrate_sqlite_to_postgres.py
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SERVER_DIR.parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "service" / "server" / "data" / "clawtrader.db"
ENV_PATH = PROJECT_ROOT / ".env"

# For one-off migration we want the project .env to win over any stale shell exports.
load_dotenv(ENV_PATH, override=True)

TABLE_ORDER = [
    "agents",
    "users",
    "agent_messages",
    "agent_tasks",
    "listings",
    "orders",
    "arbitrators",
    "dispute_votes",
    "points_transactions",
    "user_tokens",
    "rate_limits",
    "signal_sequence",
    "signals",
    "signal_replies",
    "subscriptions",
    "positions",
    "polymarket_settlements",
    "market_news_snapshots",
    "macro_signal_snapshots",
    "etf_flow_snapshots",
    "stock_analysis_snapshots",
    "profit_history",
]

TIMESTAMP_COLUMNS = {
    "created_at",
    "updated_at",
    "token_expires_at",
    "code_expires_at",
    "expires_at",
    "window_start",
    "executed_at",
    "opened_at",
    "resolved_at",
    "settled_at",
    "recorded_at",
}


def normalize_timestamp(value: str | None) -> str | None:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S",):
        try:
            parsed = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

    cleaned = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return raw

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def iter_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({quote_ident(table)})")
    rows = cursor.fetchall()
    return [row[1] for row in rows]


def normalize_row(columns: Iterable[str], row: sqlite3.Row) -> tuple:
    normalized = []
    for column in columns:
        value = row[column]
        if column in TIMESTAMP_COLUMNS:
            normalized.append(normalize_timestamp(value))
        else:
            normalized.append(value)
    return tuple(normalized)


def truncate_target(conn: psycopg.Connection):
    with conn.cursor() as cursor:
        cursor.execute(
            "TRUNCATE TABLE "
            + ", ".join(quote_ident(table) for table in reversed(TABLE_ORDER))
            + " RESTART IDENTITY CASCADE"
        )
    conn.commit()


def copy_table(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection, table: str):
    columns = iter_table_columns(sqlite_conn, table)
    if not columns:
        return 0

    select_sql = f"SELECT {', '.join(quote_ident(column) for column in columns)} FROM {quote_ident(table)}"
    copy_sql = f"COPY {quote_ident(table)} ({', '.join(quote_ident(column) for column in columns)}) FROM STDIN"

    count = 0
    src_cursor = sqlite_conn.cursor()
    src_cursor.execute(select_sql)

    with pg_conn.cursor() as pg_cursor:
        with pg_cursor.copy(copy_sql) as copy:
            for row in src_cursor:
                copy.write_row(normalize_row(columns, row))
                count += 1
                if count % 50000 == 0:
                    print(f"[migrate] {table}: copied {count} rows")

    pg_conn.commit()
    return count


def reset_sequences(pg_conn: psycopg.Connection):
    with pg_conn.cursor() as cursor:
        for table in TABLE_ORDER:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = 'id'
                """,
                (table,),
            )
            if cursor.fetchone() is None:
                continue

            cursor.execute(f"SELECT MAX(id) AS max_id FROM {quote_ident(table)}")
            row = cursor.fetchone()
            max_id = row[0] if row else None
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, %s)",
                (table, max_id or 1, max_id is not None),
            )
    pg_conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Migrate the SQLite database into PostgreSQL.")
    parser.add_argument(
        "--source",
        default=os.getenv("DB_PATH", str(DEFAULT_SQLITE_PATH)),
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL.",
    )
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    target_url = args.target.strip()

    if not source_path.exists():
        raise SystemExit(f"SQLite database not found: {source_path}")
    if not target_url:
        raise SystemExit("DATABASE_URL is required.")

    os.environ["DATABASE_URL"] = target_url
    sys.path.insert(0, str(SERVER_DIR))
    from database import init_database

    print(f"[migrate] initializing target schema: {target_url}")
    init_database()

    sqlite_conn = sqlite3.connect(source_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg.connect(target_url)

    try:
        print("[migrate] truncating target tables")
        truncate_target(pg_conn)

        for table in TABLE_ORDER:
            copied = copy_table(sqlite_conn, pg_conn, table)
            print(f"[migrate] {table}: copied {copied} rows")

        print("[migrate] resetting sequences")
        reset_sequences(pg_conn)
    finally:
        sqlite_conn.close()
        pg_conn.close()

    print("[migrate] done")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create default monthly challenge competitions for each supported track.

The script is safe to run continuously. On each run it ensures that the
configured month has one challenge per default track and skips challenges that
already exist.
"""

from __future__ import annotations

import argparse
import calendar
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SERVER_DIR.parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from challenges import create_challenge
from database import get_db_connection, init_database
from permissions import agent_role


DEFAULT_TZ = "Asia/Shanghai"
DEFAULT_CREATOR = "admin_ai-trader"
DEFAULT_INITIAL_CAPITAL = 100000.0
DEFAULT_MAX_POSITION_PCT = 100.0
DEFAULT_MAX_DRAWDOWN_PCT = 20.0
DEFAULT_SCORING_METHOD = "return-only"
SESSION_LOG_DIR = SERVER_DIR / "logs"


@dataclass(frozen=True)
class TrackSpec:
    market: str
    title: str
    symbol: str = "all"


DEFAULT_TRACKS = (
    TrackSpec("us-stock", "US Stock"),
    TrackSpec("crypto", "Crypto"),
    TrackSpec("polymarket", "Polymarket"),
)


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(value: datetime) -> datetime:
    start = month_start(value)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def challenge_key_for(track: TrackSpec, start: datetime) -> str:
    return f"monthly-{start:%Y-%m}-{track.market}"


def challenge_exists(challenge_key: str) -> bool:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM challenges WHERE challenge_key = ?", (challenge_key,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if isinstance(row, dict) else {key: row[key] for key in row.keys()}


def resolve_creator(identifier: str) -> dict[str, Any]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        agent = None
        raw = (identifier or "").strip()
        if raw:
            if raw.isdigit():
                cursor.execute("SELECT * FROM agents WHERE id = ?", (int(raw),))
            else:
                lowered = raw.lower()
                cursor.execute(
                    """
                    SELECT *
                    FROM agents
                    WHERE lower(name) = ? OR lower(COALESCE(email, '')) = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (lowered, lowered),
                )
            row = cursor.fetchone()
            if row:
                agent = row_dict(row)

        if agent is None:
            cursor.execute("SELECT * FROM agents WHERE lower(COALESCE(role, '')) = 'admin' ORDER BY id LIMIT 1")
            row = cursor.fetchone()
            if row:
                agent = row_dict(row)

        if not agent:
            raise RuntimeError("No admin agent found for monthly challenge creation")
        if agent_role(agent) != "admin":
            raise RuntimeError(f"Monthly challenge creator is not an admin: {agent.get('name') or agent.get('id')}")
        return agent
    finally:
        conn.close()


def build_payload(
    track: TrackSpec,
    start: datetime,
    end: datetime,
    *,
    initial_capital: float,
    max_position_pct: float,
    max_drawdown_pct: float,
    scoring_method: str,
    experiment_key: str = "",
) -> dict[str, Any]:
    month_label = f"{calendar.month_name[start.month]} {start.year}"
    payload = {
        "challenge_key": challenge_key_for(track, start),
        "title": f"{month_label} {track.title} Monthly Challenge",
        "description": f"Auto-created monthly {track.market} track competition for {start:%Y-%m}.",
        "market": track.market,
        "symbol": track.symbol,
        "challenge_type": "monthly-track",
        "scoring_method": scoring_method,
        "initial_capital": initial_capital,
        "max_position_pct": max_position_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "start_at": utc_iso(start),
        "end_at": utc_iso(end),
        "rules_json": {
            "cadence": "monthly",
            "auto_created": True,
            "reward_points": {"1": 100, "2": 50, "3": 25},
        },
    }
    if experiment_key:
        payload["experiment_key"] = experiment_key
    return payload


def ensure_month(
    now: datetime,
    tz: ZoneInfo,
    *,
    creator_identifier: str,
    dry_run: bool = False,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
    scoring_method: str = DEFAULT_SCORING_METHOD,
    experiment_key: str = "",
) -> list[dict[str, Any]]:
    local_now = now.astimezone(tz)
    start = month_start(local_now)
    end = next_month_start(local_now)
    creator = None if dry_run else resolve_creator(creator_identifier)
    results: list[dict[str, Any]] = []

    for track in DEFAULT_TRACKS:
        key = challenge_key_for(track, start)
        if challenge_exists(key):
            results.append({"challenge_key": key, "market": track.market, "status": "exists"})
            continue

        payload = build_payload(
            track,
            start,
            end,
            initial_capital=initial_capital,
            max_position_pct=max_position_pct,
            max_drawdown_pct=max_drawdown_pct,
            scoring_method=scoring_method,
            experiment_key=experiment_key,
        )
        if dry_run:
            results.append({"challenge_key": key, "market": track.market, "status": "dry-run", "payload": payload})
            continue

        challenge = create_challenge(payload, int(creator["id"]))
        results.append({"challenge_key": key, "market": track.market, "status": "created", "challenge": challenge})

    return results


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(f"[{stamp}] {message}", flush=True)


def run_once(args: argparse.Namespace) -> list[dict[str, Any]]:
    tz = ZoneInfo(args.timezone)
    now = datetime.now(tz)
    return ensure_month(
        now,
        tz,
        creator_identifier=args.creator,
        dry_run=args.dry_run,
        initial_capital=args.initial_capital,
        max_position_pct=args.max_position_pct,
        max_drawdown_pct=args.max_drawdown_pct,
        scoring_method=args.scoring_method,
        experiment_key=args.experiment_key,
    )


def run_loop(args: argparse.Namespace) -> None:
    tz = ZoneInfo(args.timezone)
    created_current_month = False
    while True:
        now = datetime.now(tz)
        should_run = now.day == 1 or (args.catch_up_current_month and not created_current_month)
        if should_run:
            log(f"ensuring monthly challenges for {now:%Y-%m} in timezone {args.timezone}")
            try:
                results = run_once(args)
                for result in results:
                    log(f"{result['market']} {result['challenge_key']}: {result['status']}")
                created_current_month = True
            except Exception as exc:
                log(f"monthly challenge ensure failed: {exc}")
                time.sleep(max(60, args.retry_seconds))
                continue

        next_run = next_month_start(now)
        seconds = max(60, int((next_run - now).total_seconds()))
        log(f"next monthly challenge check at {next_run.isoformat()} ({seconds} seconds)")
        time.sleep(seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and monitor default monthly challenge competitions.")
    parser.add_argument("--loop", action="store_true", help="Run continuously and wake up on the next month boundary.")
    parser.add_argument("--once", action="store_true", help="Run one ensure pass and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned challenges without creating them.")
    parser.add_argument("--timezone", default=os.getenv("MONTHLY_CHALLENGE_TZ", DEFAULT_TZ))
    parser.add_argument("--creator", default=os.getenv("MONTHLY_CHALLENGE_CREATOR", DEFAULT_CREATOR))
    parser.add_argument("--initial-capital", type=float, default=float(os.getenv("MONTHLY_CHALLENGE_INITIAL_CAPITAL", DEFAULT_INITIAL_CAPITAL)))
    parser.add_argument("--max-position-pct", type=float, default=float(os.getenv("MONTHLY_CHALLENGE_MAX_POSITION_PCT", DEFAULT_MAX_POSITION_PCT)))
    parser.add_argument("--max-drawdown-pct", type=float, default=float(os.getenv("MONTHLY_CHALLENGE_MAX_DRAWDOWN_PCT", DEFAULT_MAX_DRAWDOWN_PCT)))
    parser.add_argument("--scoring-method", default=os.getenv("MONTHLY_CHALLENGE_SCORING_METHOD", DEFAULT_SCORING_METHOD))
    parser.add_argument("--experiment-key", default=os.getenv("MONTHLY_CHALLENGE_EXPERIMENT_KEY", ""))
    parser.add_argument("--retry-seconds", type=int, default=int(os.getenv("MONTHLY_CHALLENGE_RETRY_SECONDS", "3600")))
    parser.add_argument(
        "--no-catch-up-current-month",
        dest="catch_up_current_month",
        action="store_false",
        help="Only create challenges when the local date is the first day of the month.",
    )
    parser.set_defaults(catch_up_current_month=True)
    args = parser.parse_args()
    if not args.loop and not args.once:
        args.loop = True
    return args


def main() -> int:
    args = parse_args()
    init_database()
    if args.once:
        results = run_once(args)
        for result in results:
            log(f"{result['market']} {result['challenge_key']}: {result['status']}")
        return 0
    run_loop(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Send targeted reminders to active agents with unread experiment messages."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from experiment_notifications import (  # noqa: E402
    EXPERIMENT_READ_CONVERSION_EVENT_TYPE,
    EXPERIMENT_READ_CONVERSION_REMINDER_TYPE,
    resolve_unread_active_experiment_targets,
    send_agent_notifications,
)
from routes_shared import RouteContext, utc_now_iso_z  # noqa: E402


DEFAULT_EXPERIMENT_KEY = "agent-collab-compete-season-001"
DEFAULT_TITLE = "Action required: read AI-Trader experiment messages"
DEFAULT_CONTENT = (
    "You have unread AI-Trader experiment messages. Immediately call "
    "POST /api/claw/messages/read-experiment with Authorization: Bearer <your_token>. "
    "This endpoint returns unread experiment messages and marks them read in one step. "
    "This reminder is informational only and does not create a trading task."
)


def _iso_hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))).isoformat().replace("+00:00", "Z")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _preview_rows(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    preview = []
    for row in rows[:limit]:
        preview.append({
            "agent_id": row.get("agent_id"),
            "agent_name": row.get("agent_name"),
            "variant_key": row.get("variant_key"),
            "latest_activity_at": row.get("latest_activity_at"),
            "unread_experiment_count": row.get("unread_experiment_count"),
        })
    return preview


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    active_since = args.active_since or _iso_hours_ago(args.active_hours)
    reminder_since = args.reminder_since or _iso_hours_ago(args.cooldown_hours)
    targets = resolve_unread_active_experiment_targets(
        args.experiment_key,
        variant_key=args.variant_key,
        limit=args.limit,
        active_since=active_since,
        reminder_since=reminder_since,
    )
    dry_run = not args.send
    ctx = RouteContext()
    target_rule = {
        "target": "unread_active",
        "experiment_key": args.experiment_key,
        "variant_key": args.variant_key,
        "limit": args.limit,
        "active_since": active_since,
        "reminder_since": reminder_since,
        "cooldown_hours": args.cooldown_hours,
        "active_hours": args.active_hours,
    }
    data = {
        "purpose": "read_conversion",
        "recommended_endpoint": "/api/claw/messages/read-experiment",
        "recommended_method": "POST",
        "marks_read": True,
        "active_since": active_since,
        "reminder_since": reminder_since,
    }
    result = await send_agent_notifications(
        ctx,
        targets,
        actor_agent_id=args.actor_agent_id,
        message_type=EXPERIMENT_READ_CONVERSION_REMINDER_TYPE,
        title=args.title,
        content=args.content,
        experiment_key=args.experiment_key,
        variant_key=args.variant_key,
        data=data,
        dry_run=dry_run,
        event_type=EXPERIMENT_READ_CONVERSION_EVENT_TYPE,
        target_rule=target_rule,
    )
    result["active_since"] = active_since
    result["reminder_since"] = reminder_since
    result["targets_preview"] = _preview_rows(targets)
    result["sent_at"] = utc_now_iso_z()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-key", default=DEFAULT_EXPERIMENT_KEY)
    parser.add_argument("--variant-key", default=None)
    parser.add_argument("--limit", type=int, default=_env_int("READ_CONVERSION_REMINDER_LIMIT", 500))
    parser.add_argument("--active-hours", type=int, default=24)
    parser.add_argument("--cooldown-hours", type=int, default=24)
    parser.add_argument("--active-since", default=None)
    parser.add_argument("--reminder-since", default=None)
    parser.add_argument("--actor-agent-id", type=int, default=_env_int("READ_CONVERSION_ACTOR_AGENT_ID", 0))
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--content", default=DEFAULT_CONTENT)
    parser.add_argument("--send", action="store_true", help="Actually write messages. Defaults to dry-run.")
    args = parser.parse_args()

    if args.actor_agent_id <= 0:
        parser.error("--actor-agent-id or READ_CONVERSION_ACTOR_AGENT_ID is required")

    result = asyncio.run(_run(args))
    import json

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

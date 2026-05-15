"""Dispatch-side helper: wait for a coord reply by polling the fork.

Pairs with send_coord_task.py. Given a task_id, poll origin/coord until the
matching .coord/outbox/<task_id>.json appears, then print it.

Usage:
    python3 deploy/coord-daemon/poll_coord_reply.py <task_id> --timeout 300

Exit codes:
    0  reply found, status "ok"
    3  reply found, status not "ok" (denied / fail / timeout)
    4  no reply before --timeout

The helper only reads from the remote — it never writes or pushes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

COORD_BRANCH = "coord"


def _run(argv: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=check, timeout=60)


def _git_toplevel() -> str:
    out = _run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    if not out:
        raise SystemExit("not inside a git repo")
    return out


def poll_reply(task_id: str, *, repo: str | None = None, timeout_s: int = 300, interval_s: int = 15) -> dict | None:
    repo = repo or _git_toplevel()
    deadline = time.monotonic() + timeout_s
    target_path = f".coord/outbox/{task_id}.json"

    while True:
        fetch = subprocess.run(
            ["git", "fetch", "origin", COORD_BRANCH],
            cwd=repo, capture_output=True, text=True, timeout=60,
        )
        if fetch.returncode != 0:
            print(f"[poll] fetch failed: {fetch.stderr.strip()}", file=sys.stderr)
        else:
            blob = subprocess.run(
                ["git", "show", f"origin/{COORD_BRANCH}:{target_path}"],
                cwd=repo, capture_output=True, text=True, timeout=30,
            )
            if blob.returncode == 0:
                try:
                    return json.loads(blob.stdout)
                except json.JSONDecodeError as e:
                    print(f"[poll] outbox file present but malformed: {e}", file=sys.stderr)
                    return None
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll coord outbox for a task reply")
    parser.add_argument("task_id")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait before giving up")
    parser.add_argument("--interval", type=int, default=15, help="Seconds between poll attempts")
    args = parser.parse_args()

    reply = poll_reply(args.task_id, timeout_s=args.timeout, interval_s=args.interval)
    if reply is None:
        print(f"no reply for {args.task_id} within {args.timeout}s", file=sys.stderr)
        return 4

    print(json.dumps(reply, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if reply.get("status") == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())

"""Dispatch-side helper: queue a coord task for M1 by committing to the fork.

This runs in the M4 dispatch sandbox where the only channel back to M1 is the
git remote on this fork. It writes `.coord/inbox/<task_id>.json` on the `coord`
branch and pushes.

Usage:
    python3 deploy/coord-daemon/send_coord_task.py \
        --action health_check \
        --params '{"url": "http://127.0.0.1:8788/api/health"}'

Prints the assigned task_id on stdout. Pair with poll_coord_reply.py to wait for
the reply.

The helper assumes:
  - cwd is somewhere inside a working clone with `origin` pointing at the fork
  - the caller has push rights to the `coord` branch
  - `coord` already exists upstream (this script does not bootstrap the branch)

It does NOT exec anything else, does not touch main, and never force-pushes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

COORD_BRANCH = "coord"
COORD_DIR = ".coord"


def _now_iso(offset_seconds: int = 0) -> str:
    return (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset_seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(argv: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=check, timeout=120)


def _git_toplevel() -> str:
    out = _run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    if not out:
        raise SystemExit("not inside a git repo")
    return out


def _ensure_remote_coord_present(repo: str) -> None:
    fetch = subprocess.run(
        ["git", "fetch", "origin", COORD_BRANCH],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    if fetch.returncode != 0:
        raise SystemExit(
            f"could not fetch origin/{COORD_BRANCH}: {fetch.stderr.strip()}\n"
            "Make sure the coord branch has been created and pushed to origin."
        )


def send_task(action: str, params: dict, *, repo: str | None = None, expires_in_seconds: int = 1800) -> str:
    """Write inbox file on a worktree-local checkout of `coord` and push.

    To avoid mutating the caller's current branch, we use `git worktree add` to
    materialize the coord branch in a temp directory.
    """
    repo = repo or _git_toplevel()
    _ensure_remote_coord_present(repo)

    task_id = str(uuid.uuid4())
    payload = {
        "task_id": task_id,
        "timestamp": _now_iso(),
        "expires_at": _now_iso(offset_seconds=expires_in_seconds),
        "from": "dispatch-m4",
        "to": "m1",
        "action": action,
        "params": params or {},
        "nonce": uuid.uuid4().hex,
    }

    with tempfile.TemporaryDirectory(prefix="coord-send-") as tmp:
        worktree = os.path.join(tmp, "coord-wt")
        _run(["git", "worktree", "add", "-B", COORD_BRANCH, worktree, f"origin/{COORD_BRANCH}"], cwd=repo)
        try:
            inbox = Path(worktree) / COORD_DIR / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            target = inbox / f"{task_id}.json"
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _run(["git", "add", "-A", COORD_DIR], cwd=worktree)
            _run([
                "git",
                "-c", "user.name=dispatch-m4",
                "-c", "user.email=dispatch@bw-space.com",
                "commit", "-m", f"coord(dispatch): queue {action} {task_id[:8]}",
            ], cwd=worktree)
            push = subprocess.run(
                ["git", "push", "origin", COORD_BRANCH],
                cwd=worktree, capture_output=True, text=True, timeout=60,
            )
            if push.returncode != 0:
                raise SystemExit(f"push to origin/{COORD_BRANCH} failed: {push.stderr.strip()}")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", worktree], cwd=repo, capture_output=True)

    return task_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue a coord task for M1")
    parser.add_argument("--action", required=True, help="Action name (must be on the M1 whitelist)")
    parser.add_argument("--params", default="{}", help="JSON object of action params")
    parser.add_argument("--expires-in", type=int, default=1800, help="Seconds until task expires (default 1800)")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(f"--params is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(params, dict):
        print("--params must be a JSON object", file=sys.stderr)
        return 2

    task_id = send_task(args.action, params, expires_in_seconds=args.expires_in)
    print(task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

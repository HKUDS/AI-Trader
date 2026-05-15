"""M1 coord daemon — poll fork repo for pending tasks, execute, commit reply.

One iteration of the loop does:

  1. git fetch + ff-merge the coord branch from origin
  2. read .coord/inbox/*.json on the coord branch
  3. for each task:
       a. validate schema (task_id, from, to, action, params, nonce, expires_at)
       b. resolve action via whitelist (or write 'denied' reply)
       c. exec argv as subprocess with captured stdout/stderr + timeout
       d. write .coord/outbox/<task_id>.json with the result
       e. delete the inbox file
  4. git add -A on .coord/, commit if anything changed, push to origin coord
  5. exit (launchd StartInterval respawns us each minute)

The daemon is designed to be **fail-loud**: any unexpected exception is logged
to stderr (which launchd captures), and the loop continues with the next task
where it can. Per-task failures are still written as outbox replies so the
dispatch side sees them.

Run manually:
    COORD_REPO_ROOT=$HOME/dev/AI-Trader python3 coord_daemon.py --once

Run under launchd: see deploy/launchd/ai.bwstudio.bw-trader-coord-daemon.plist
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as a script from the deploy/coord-daemon directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from whitelist import DeniedAction, repo_root, resolve_action  # noqa: E402

COORD_BRANCH = "coord"
COORD_DIR = ".coord"
INBOX = "inbox"
OUTBOX = "outbox"
STDOUT_MAX_BYTES = 8 * 1024
STDERR_MAX_BYTES = 8 * 1024
LOG_PREFIX = "[coord-daemon]"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    print(f"{LOG_PREFIX} {_now_iso()} {msg}", flush=True)


def _truncate(data: str | bytes, limit: int) -> str:
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8", errors="replace")
        except Exception:
            data = repr(data)
    if len(data) <= limit:
        return data
    return data[:limit] + f"\n...[truncated, original {len(data)} bytes]"


def _git(args: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _ensure_coord_branch_checked_out(repo: str) -> None:
    """Make sure we're on COORD_BRANCH and synced with origin/COORD_BRANCH.

    Strategy: stash any local changes, checkout coord branch (create tracking if
    missing), fast-forward from origin. We never touch main from this daemon.
    """
    _git(["fetch", "origin", COORD_BRANCH], cwd=repo, check=False)
    current = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()
    if current != COORD_BRANCH:
        # Try local checkout first, fall back to tracking remote.
        rc = subprocess.run(
            ["git", "checkout", COORD_BRANCH],
            cwd=repo, capture_output=True, text=True,
        ).returncode
        if rc != 0:
            _git(["checkout", "-B", COORD_BRANCH, f"origin/{COORD_BRANCH}"], cwd=repo)
    _git(["pull", "--ff-only", "origin", COORD_BRANCH], cwd=repo, check=False)


def _list_inbox(repo: str) -> list[Path]:
    inbox = Path(repo) / COORD_DIR / INBOX
    if not inbox.exists():
        return []
    return sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix == ".json")


REQUIRED_FIELDS = ("task_id", "from", "to", "action", "nonce")


def _validate_task(payload: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "task payload must be a JSON object"
    for field in REQUIRED_FIELDS:
        if field not in payload:
            return False, f"missing required field: {field}"
        if not isinstance(payload[field], str) or not payload[field]:
            return False, f"field {field} must be non-empty string"
    if payload.get("to") != "m1":
        return False, f"task not addressed to m1 (to={payload.get('to')!r})"
    params = payload.get("params", {})
    if params is not None and not isinstance(params, dict):
        return False, "params must be an object or null"
    expires = payload.get("expires_at")
    if expires is not None:
        if not isinstance(expires, str):
            return False, "expires_at must be string or null"
        try:
            exp_dt = dt.datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            return False, f"expires_at not ISO-8601 Z format: {expires!r}"
        if exp_dt < dt.datetime.now(dt.timezone.utc):
            return False, "task expired"
    return True, ""


def _exec_action(
    argv: list[str], cwd: str | None, timeout: int
) -> tuple[int, str, str, str]:
    """Run argv. Returns (exit_code, stdout, stderr, status)."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        elapsed = time.monotonic() - start
        _log(f"timeout after {elapsed:.1f}s argv={argv!r}")
        return (
            124,
            _truncate(e.stdout or "", STDOUT_MAX_BYTES),
            _truncate(e.stderr or f"timeout after {timeout}s", STDERR_MAX_BYTES),
            "timeout",
        )
    except FileNotFoundError as e:
        return 127, "", _truncate(str(e), STDERR_MAX_BYTES), "fail"

    status = "ok" if proc.returncode == 0 else "fail"
    return (
        proc.returncode,
        _truncate(proc.stdout or "", STDOUT_MAX_BYTES),
        _truncate(proc.stderr or "", STDERR_MAX_BYTES),
        status,
    )


def _write_reply(repo: str, task_id: str, reply: dict) -> Path:
    outbox = Path(repo) / COORD_DIR / OUTBOX
    outbox.mkdir(parents=True, exist_ok=True)
    out_path = outbox / f"{task_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(reply, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return out_path


def process_task(repo: str, inbox_path: Path) -> dict:
    """Process one inbox file, return the reply dict (also written to outbox)."""
    task_id_fallback = inbox_path.stem
    ack_at = _now_iso()
    try:
        payload = json.loads(inbox_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        reply = {
            "task_id": task_id_fallback,
            "ack_at": ack_at,
            "completed_at": _now_iso(),
            "exit_code": 2,
            "stdout": "",
            "stderr": f"invalid JSON: {e}",
            "status": "denied",
        }
        _write_reply(repo, task_id_fallback, reply)
        return reply

    ok, reason = _validate_task(payload)
    task_id = payload.get("task_id", task_id_fallback) if isinstance(payload, dict) else task_id_fallback
    if not ok:
        reply = {
            "task_id": task_id,
            "ack_at": ack_at,
            "completed_at": _now_iso(),
            "exit_code": 2,
            "stdout": "",
            "stderr": f"schema error: {reason}",
            "status": "denied",
        }
        _write_reply(repo, task_id, reply)
        return reply

    action = payload["action"]
    params = payload.get("params") or {}
    try:
        argv, cwd, timeout = resolve_action(action, params)
    except DeniedAction as e:
        reply = {
            "task_id": task_id,
            "ack_at": ack_at,
            "completed_at": _now_iso(),
            "exit_code": 2,
            "stdout": "",
            "stderr": f"denied: {e}",
            "status": "denied",
        }
        _write_reply(repo, task_id, reply)
        return reply

    _log(f"exec task={task_id} action={action} argv={argv!r}")
    exit_code, stdout, stderr, status = _exec_action(argv, cwd, timeout)
    reply = {
        "task_id": task_id,
        "ack_at": ack_at,
        "completed_at": _now_iso(),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "status": status,
        "action": action,
    }
    _write_reply(repo, task_id, reply)
    return reply


def run_once(repo: str | None = None, *, sync: bool = True) -> int:
    """Run one poll cycle. Returns number of tasks processed."""
    repo = repo or repo_root()
    if sync:
        _ensure_coord_branch_checked_out(repo)

    inbox_files = _list_inbox(repo)
    if not inbox_files:
        _log("no inbox tasks")
        return 0

    processed: list[str] = []
    for inbox_path in inbox_files:
        reply = process_task(repo, inbox_path)
        try:
            inbox_path.unlink()
        except FileNotFoundError:
            pass
        processed.append(reply["task_id"])

    if sync and processed:
        _git(["add", "-A", COORD_DIR], cwd=repo, check=False)
        status_out = _git(["status", "--porcelain"], cwd=repo).stdout
        if status_out.strip():
            short_ids = ",".join(t[:8] for t in processed)
            _git(
                [
                    "-c", "user.name=bw-coord-daemon",
                    "-c", "user.email=coord-daemon@bw-space.com",
                    "commit", "-m", f"coord(m1): reply {short_ids}",
                ],
                cwd=repo,
            )
            push = subprocess.run(
                ["git", "push", "origin", COORD_BRANCH],
                cwd=repo, capture_output=True, text=True, timeout=60,
            )
            if push.returncode != 0:
                _log(f"push failed: {push.stderr.strip()}")
            else:
                _log(f"pushed {len(processed)} reply commit(s)")
    return len(processed)


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 coord daemon")
    parser.add_argument(
        "--once", action="store_true",
        help="Run one poll cycle and exit (default; matches launchd StartInterval).",
    )
    parser.add_argument(
        "--no-sync", action="store_true",
        help="Skip git pull/commit/push (useful for local testing).",
    )
    parser.add_argument(
        "--repo", default=None,
        help="Override repo root (defaults to COORD_REPO_ROOT env or ~/dev/AI-Trader).",
    )
    args = parser.parse_args()

    try:
        run_once(repo=args.repo, sync=not args.no_sync)
    except Exception as e:  # noqa: BLE001 — fail-loud, log + return non-zero
        _log(f"FATAL: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

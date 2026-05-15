"""Daemon-level tests: schema validation, truncation, timeout, exec path.

These run with --no-sync (no git operations), against a tmp_path "repo" with
just the `.coord/inbox` + `.coord/outbox` layout the daemon needs.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

import coord_daemon as cd


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".coord" / "inbox").mkdir(parents=True)
    (repo / ".coord" / "outbox").mkdir(parents=True)
    return repo


def _write_task(repo: Path, task: dict) -> Path:
    target = repo / ".coord" / "inbox" / f"{task['task_id']}.json"
    target.write_text(json.dumps(task), encoding="utf-8")
    return target


def test_validate_task_accepts_minimal_valid():
    ok, reason = cd._validate_task({
        "task_id": "abc", "from": "dispatch-m4", "to": "m1",
        "action": "git_pull", "nonce": "n",
    })
    assert ok, reason


def test_validate_task_rejects_missing_fields():
    bad = {"task_id": "abc", "from": "dispatch-m4", "to": "m1"}
    ok, reason = cd._validate_task(bad)
    assert not ok and "action" in reason


def test_validate_task_rejects_wrong_recipient():
    ok, reason = cd._validate_task({
        "task_id": "abc", "from": "dispatch-m4", "to": "m99",
        "action": "git_pull", "nonce": "n",
    })
    assert not ok and "m1" in reason


def test_validate_task_rejects_expired():
    ok, reason = cd._validate_task({
        "task_id": "abc", "from": "dispatch-m4", "to": "m1",
        "action": "git_pull", "nonce": "n",
        "expires_at": "2000-01-01T00:00:00Z",
    })
    assert not ok and "expired" in reason


def test_truncate_caps_long_strings():
    big = "x" * (cd.STDOUT_MAX_BYTES + 1000)
    out = cd._truncate(big, cd.STDOUT_MAX_BYTES)
    assert len(out) <= cd.STDOUT_MAX_BYTES + 64
    assert "truncated" in out


def test_truncate_passes_short_strings():
    assert cd._truncate("hi", cd.STDOUT_MAX_BYTES) == "hi"


def test_exec_action_captures_exit_code(tmp_path):
    exit_code, stdout, stderr, status = cd._exec_action(
        ["python3", "-c", "import sys; sys.exit(7)"], cwd=None, timeout=5
    )
    assert exit_code == 7
    assert status == "fail"


def test_exec_action_timeout(tmp_path):
    exit_code, stdout, stderr, status = cd._exec_action(
        ["python3", "-c", "import time; time.sleep(5)"], cwd=None, timeout=1
    )
    assert status == "timeout"
    assert exit_code == 124


def test_process_task_denied_for_invalid_json(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    bad = repo / ".coord" / "inbox" / "bogus.json"
    bad.write_text("{not json}", encoding="utf-8")
    monkeypatch.setenv("COORD_REPO_ROOT", str(repo))
    reply = cd.process_task(str(repo), bad)
    assert reply["status"] == "denied"
    assert "invalid JSON" in reply["stderr"]
    # outbox file written under fallback id (the stem)
    assert (repo / ".coord" / "outbox" / "bogus.json").exists()


def test_process_task_denied_for_unknown_action(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("COORD_REPO_ROOT", str(repo))
    task = {
        "task_id": "t1", "from": "dispatch-m4", "to": "m1",
        "action": "rm_minus_rf", "nonce": "n", "params": {},
    }
    inbox_path = _write_task(repo, task)
    reply = cd.process_task(str(repo), inbox_path)
    assert reply["status"] == "denied"
    assert "rm_minus_rf" in reply["stderr"] or "whitelist" in reply["stderr"]
    assert (repo / ".coord" / "outbox" / "t1.json").exists()


def test_process_task_executes_git_status_via_whitelist(tmp_path, monkeypatch):
    """End-to-end: a valid git_status task runs and writes an ok outbox file."""
    # Use a real git repo so `git status --short` succeeds
    import subprocess
    repo = _make_repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "--allow-empty", "-m", "init", "-q"], cwd=repo, check=True)
    monkeypatch.setenv("COORD_REPO_ROOT", str(repo))

    task = {
        "task_id": "git-status-1", "from": "dispatch-m4", "to": "m1",
        "action": "git_status", "nonce": "n",
    }
    inbox_path = _write_task(repo, task)
    reply = cd.process_task(str(repo), inbox_path)
    assert reply["status"] == "ok"
    assert reply["exit_code"] == 0
    out = (repo / ".coord" / "outbox" / "git-status-1.json")
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["task_id"] == "git-status-1"


def test_run_once_no_sync_returns_zero_when_inbox_empty(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("COORD_REPO_ROOT", str(repo))
    n = cd.run_once(repo=str(repo), sync=False)
    assert n == 0


def test_run_once_no_sync_processes_and_clears_inbox(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("COORD_REPO_ROOT", str(repo))
    task = {
        "task_id": "denied-1", "from": "dispatch-m4", "to": "m1",
        "action": "does_not_exist", "nonce": "n",
    }
    inbox_path = _write_task(repo, task)
    n = cd.run_once(repo=str(repo), sync=False)
    assert n == 1
    assert not inbox_path.exists()
    assert (repo / ".coord" / "outbox" / "denied-1.json").exists()


def test_main_dry_run_flag_disables_sync(tmp_path, monkeypatch):
    """`--dry-run` should run one cycle and never invoke git pull/commit/push."""
    repo = _make_repo(tmp_path)
    task = {
        "task_id": "dry-1", "from": "dispatch-m4", "to": "m1",
        "action": "does_not_exist", "nonce": "n",
    }
    _write_task(repo, task)

    called = {"sync_values": []}

    def fake_run_once(repo=None, *, sync=True):
        called["sync_values"].append(sync)
        return 0

    monkeypatch.setattr(cd, "run_once", fake_run_once)
    monkeypatch.setattr(sys, "argv", ["coord_daemon.py", "--dry-run", "--repo", str(repo)])
    rc = cd.main()
    assert rc == 0
    assert called["sync_values"] == [False], (
        f"--dry-run must disable sync, got sync={called['sync_values']!r}"
    )


def test_main_no_sync_flag_disables_sync(monkeypatch, tmp_path):
    """Regression: `--no-sync` continues to work alongside --dry-run."""
    called = {"sync_values": []}

    def fake_run_once(repo=None, *, sync=True):
        called["sync_values"].append(sync)
        return 0

    monkeypatch.setattr(cd, "run_once", fake_run_once)
    monkeypatch.setattr(sys, "argv", ["coord_daemon.py", "--no-sync", "--repo", str(tmp_path)])
    rc = cd.main()
    assert rc == 0
    assert called["sync_values"] == [False]

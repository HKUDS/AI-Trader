"""Whitelist validation tests — these are the safety guarantees, prove them."""
from __future__ import annotations

import os

import pytest

import whitelist
from whitelist import ACTIONS, DeniedAction, resolve_action


def test_unknown_action_is_denied():
    with pytest.raises(DeniedAction):
        resolve_action("rm_rf_slash", {})


def test_git_pull_resolves_to_safe_argv():
    argv, cwd, timeout = resolve_action("git_pull", {})
    assert argv[0] == "git"
    assert "--ff-only" in argv
    assert "origin" in argv and "main" in argv
    assert "--force" not in argv
    assert "reset" not in argv
    assert timeout <= 120


def test_launchctl_kickstart_requires_bwstudio_label():
    with pytest.raises(DeniedAction):
        resolve_action("launchctl_kickstart", {"label": "com.apple.evilservice"})

    with pytest.raises(DeniedAction):
        resolve_action("launchctl_kickstart", {"label": ""})

    argv, _, _ = resolve_action(
        "launchctl_kickstart", {"label": "ai.bwstudio.bw-trader-api"}
    )
    assert argv[:3] == ["launchctl", "kickstart", "-k"]
    assert argv[3].startswith("gui/")
    assert argv[3].endswith("/ai.bwstudio.bw-trader-api")


def test_launchctl_kickstart_label_rejects_path_traversal():
    # Even if regex matches alphanumeric tail, anything starting with the wrong
    # prefix or containing dangerous chars must be rejected.
    for bad in [
        "ai.bwstudio.../com.apple.something",
        "ai.bwstudio.foo bar",
        "ai.bwstudio.$(rm -rf /)",
        "AI.BWSTUDIO.bar",  # case sensitive
    ]:
        with pytest.raises(DeniedAction):
            resolve_action("launchctl_kickstart", {"label": bad})


def test_uv_pip_install_uses_system_flag():
    argv, cwd, _ = resolve_action("uv_pip_install", {})
    assert argv[:4] == ["uv", "pip", "install", "--system"]
    assert "-r" in argv
    assert "service/requirements.txt" in argv
    assert cwd  # must run inside repo


def test_launchctl_bootstrap_accepts_label_param():
    argv, _, _ = resolve_action(
        "launchctl_bootstrap", {"label": "ai.bwstudio.bw-trader-coord-daemon"}
    )
    home = os.path.expanduser("~")
    assert argv[0] == "launchctl"
    assert argv[1] == "bootstrap"
    assert argv[2].startswith("gui/")
    assert argv[3] == f"{home}/Library/LaunchAgents/ai.bwstudio.bw-trader-coord-daemon.plist"


def test_launchctl_bootstrap_accepts_plist_path_param():
    home = os.path.expanduser("~")
    good = f"{home}/Library/LaunchAgents/ai.bwstudio.bw-trader-api.plist"
    argv, _, _ = resolve_action("launchctl_bootstrap", {"plist_path": good})
    assert argv[-1] == good


def test_launchctl_bootstrap_rejects_non_bwstudio_label():
    for bad in [
        "com.apple.something",
        "ai.bwstudio.",  # empty tail
        "AI.BWSTUDIO.foo",
        "ai.bwstudio.$(rm -rf /)",
        "",
    ]:
        with pytest.raises(DeniedAction):
            resolve_action("launchctl_bootstrap", {"label": bad})


def test_launchctl_bootstrap_rejects_non_bwstudio_plist_path():
    home = os.path.expanduser("~")
    for bad in [
        "/tmp/evil.plist",
        f"{home}/Library/LaunchAgents/com.apple.thing.plist",
        f"{home}/Library/LaunchAgents/ai.bwstudio.foo.txt",
    ]:
        with pytest.raises(DeniedAction):
            resolve_action("launchctl_bootstrap", {"plist_path": bad})


def test_launchctl_bootstrap_requires_at_least_one_param():
    with pytest.raises(DeniedAction):
        resolve_action("launchctl_bootstrap", {})


def test_launchctl_bootout_basic():
    argv, _, timeout = resolve_action(
        "launchctl_bootout", {"label": "ai.bwstudio.bw-trader-api"}
    )
    assert argv[:2] == ["launchctl", "bootout"]
    assert argv[2].startswith("gui/")
    assert argv[2].endswith("/ai.bwstudio.bw-trader-api")
    assert timeout <= 60


def test_launchctl_bootout_requires_bwstudio_label():
    for bad in [
        "com.apple.evilservice",
        "homebrew.mxcl.cloudflared",
        "",
        "ai.bwstudio.$(touch /tmp/pwned)",
    ]:
        with pytest.raises(DeniedAction):
            resolve_action("launchctl_bootout", {"label": bad})


def test_launchctl_bootstrap_path_must_be_in_launch_agents():
    home = os.path.expanduser("~")
    good = f"{home}/Library/LaunchAgents/ai.bwstudio.bw-trader-coord-daemon.plist"
    argv, _, _ = resolve_action("launchctl_bootstrap", {"plist_path": good})
    assert argv[0] == "launchctl"
    assert argv[1] == "bootstrap"
    assert argv[-1] == good

    bad_paths = [
        "/tmp/evil.plist",
        f"{home}/Library/LaunchAgents/com.apple.something.plist",
        f"{home}/Library/LaunchAgents/ai.bwstudio.foo.txt",  # not .plist
        f"{home}/Library/LaunchAgents/ai.bwstudio.foo/../../../etc/hosts",
        "../../../etc/launchd.plist",
    ]
    for bad in bad_paths:
        with pytest.raises(DeniedAction):
            resolve_action("launchctl_bootstrap", {"plist_path": bad})


def test_health_check_only_loopback_or_bw_space_com():
    ok_urls = [
        "http://127.0.0.1:8788/health",
        "http://localhost:8000/api/health",
        "https://bw-trader-api.bw-space.com/health",
    ]
    for url in ok_urls:
        argv, _, _ = resolve_action("health_check", {"url": url})
        assert argv[0] == "curl"
        assert url in argv

    bad_urls = [
        "http://evil.com/exfil",
        "http://10.0.0.1:9999/",
        "https://example.com",
        "https://bw-trader-api.attacker.com",  # wrong host
        "file:///etc/passwd",
        "",
    ]
    for url in bad_urls:
        with pytest.raises(DeniedAction):
            resolve_action("health_check", {"url": url})


def test_run_script_slug_only(tmp_path, monkeypatch):
    # Point the whitelist at a temp "repo" with a fake script dir
    fake_repo = tmp_path / "repo"
    scripts_dir = fake_repo / "deploy" / "m1-coord-scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "m1-redeploy.sh").write_text("#!/bin/sh\necho ok\n")
    monkeypatch.setenv(whitelist.REPO_ROOT_ENV, str(fake_repo))

    argv, _, _ = resolve_action("run_script", {"name": "m1-redeploy"})
    assert argv[0] == "bash"
    assert argv[1].endswith("/deploy/m1-coord-scripts/m1-redeploy.sh")

    for bad in ["../etc/passwd", "m1-redeploy.sh", "../m1-redeploy",
                "m1 redeploy", "M1-Redeploy", ""]:
        with pytest.raises(DeniedAction):
            resolve_action("run_script", {"name": bad})


def test_run_script_rejects_symlink_escape(tmp_path, monkeypatch):
    fake_repo = tmp_path / "repo"
    scripts_dir = fake_repo / "deploy" / "m1-coord-scripts"
    scripts_dir.mkdir(parents=True)
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/bin/sh\necho pwned\n")
    # Place a symlink inside scripts_dir pointing outside the allowed dir.
    (scripts_dir / "escape.sh").symlink_to(outside)
    monkeypatch.setenv(whitelist.REPO_ROOT_ENV, str(fake_repo))

    # The realpath check should reject this even though the slug + filename look ok.
    with pytest.raises(DeniedAction):
        resolve_action("run_script", {"name": "escape"})


def test_no_destructive_action_in_whitelist():
    # If anyone adds something dangerous to ACTIONS this test breaks loudly.
    # Note: launchctl_bootout is allowed but only for ai.bwstudio.* labels —
    # see test_launchctl_bootout_requires_bwstudio_label.
    for name in ACTIONS:
        assert "force" not in name
        assert "unload" not in name
        assert "rm" not in name
        assert "reset" not in name


def test_every_action_has_handler_and_timeout():
    for name, spec in ACTIONS.items():
        assert callable(spec.get("handler")), name
        assert isinstance(spec.get("timeout_seconds"), int), name
        assert 1 <= spec["timeout_seconds"] <= 900, name


def test_handlers_never_use_shell_strings():
    """Handlers must return argv lists, not shell command strings."""
    sample_params = {
        "launchctl_kickstart": {"label": "ai.bwstudio.bw-trader-api"},
        "launchctl_bootstrap": {
            "plist_path": os.path.expanduser(
                "~/Library/LaunchAgents/ai.bwstudio.bw-trader-coord-daemon.plist"
            )
        },
        "launchctl_bootout": {"label": "ai.bwstudio.bw-trader-api"},
        "launchctl_list": {"label": "ai.bwstudio.bw-trader-api"},
        "health_check": {"url": "http://127.0.0.1:8788/health"},
        "run_script": {"name": "m1-redeploy"},
    }
    for name, spec in ACTIONS.items():
        params = sample_params.get(name, {})
        validator = spec.get("validate")
        if validator and not validator(params):
            continue  # action that requires repo-on-disk for validation; skip
        argv = spec["handler"](params)
        assert isinstance(argv, list)
        assert all(isinstance(x, str) for x in argv)
        # No element should be a full shell pipeline.
        for token in argv:
            assert ";" not in token, (name, token)
            assert "&&" not in token, (name, token)
            assert "|" not in token or token == "|", (name, token)

"""Whitelist of actions the M1 coord daemon is allowed to execute.

Every action declares:
  - argv builder (params -> list[str])
  - optional cwd
  - optional params validator (rejects bad params before exec)
  - timeout in seconds
  - optional env additions

Anything not in ACTIONS is denied. Validators must return True for the params
to be accepted. Handlers must never embed user-controlled strings into a shell
string — argv is passed to subprocess without shell=True.

Red lines enforced here (do not relax without a security review):
  - no arbitrary shell command
  - no destructive git (push --force, reset --hard, clean -fdx)
  - no launchctl bootout / unload
  - launchctl labels must start with ai.bwstudio.
  - run_script names must be a short slug pointing at deploy/m1-coord-scripts/
  - health_check URLs must be loopback or *.bw-space.com
"""

from __future__ import annotations

import os
import re
from typing import Callable, TypedDict

REPO_ROOT_ENV = "COORD_REPO_ROOT"
DEFAULT_REPO_ROOT = os.path.expanduser("~/dev/AI-Trader")


def repo_root() -> str:
    return os.environ.get(REPO_ROOT_ENV, DEFAULT_REPO_ROOT)


def _uid() -> str:
    return str(os.getuid())


class ActionSpec(TypedDict, total=False):
    handler: Callable[[dict], list[str]]
    validate: Callable[[dict], bool]
    cwd: Callable[[dict], str] | str | None
    timeout_seconds: int
    env: Callable[[dict], dict[str, str]] | None


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_LABEL_RE = re.compile(r"^ai\.bwstudio\.[a-z0-9][a-z0-9.-]{0,63}$")


def _validate_launchctl_label(params: dict) -> bool:
    label = params.get("label", "")
    return isinstance(label, str) and bool(_LABEL_RE.match(label))


def _validate_bootstrap_plist(params: dict) -> bool:
    path = params.get("plist_path", "")
    if not isinstance(path, str):
        return False
    home = os.path.expanduser("~")
    expected_prefix = os.path.join(home, "Library", "LaunchAgents", "ai.bwstudio.")
    if not path.startswith(expected_prefix):
        return False
    if ".." in path or not path.endswith(".plist"):
        return False
    return True


def _validate_health_url(params: dict) -> bool:
    url = params.get("url", "")
    if not isinstance(url, str):
        return False
    loopback_ok = url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")
    bwspace_ok = url.startswith("https://") and ".bw-space.com" in url
    return loopback_ok or bwspace_ok


def _validate_script_name(params: dict) -> bool:
    name = params.get("name", "")
    if not isinstance(name, str) or not _SLUG_RE.match(name):
        return False
    script_path = os.path.join(repo_root(), "deploy", "m1-coord-scripts", f"{name}.sh")
    # Resolve to defend against any path tricks that survive the regex.
    resolved = os.path.realpath(script_path)
    expected_dir = os.path.realpath(os.path.join(repo_root(), "deploy", "m1-coord-scripts"))
    return resolved.startswith(expected_dir + os.sep)


ACTIONS: dict[str, ActionSpec] = {
    "git_pull": {
        "handler": lambda params: [
            "git", "-C", repo_root(), "pull", "--ff-only", "origin", "main",
        ],
        "validate": lambda params: params == {} or params is None or not params,
        "timeout_seconds": 60,
    },
    "git_status": {
        "handler": lambda params: ["git", "-C", repo_root(), "status", "--short"],
        "validate": lambda params: not params,
        "timeout_seconds": 10,
    },
    "uv_pip_install": {
        "handler": lambda params: [
            "uv", "pip", "install", "-r", "service/requirements.txt",
        ],
        "cwd": lambda params: repo_root(),
        "validate": lambda params: not params,
        "timeout_seconds": 300,
    },
    "launchctl_kickstart": {
        "handler": lambda params: [
            "launchctl", "kickstart", "-k", f"gui/{_uid()}/{params['label']}",
        ],
        "validate": _validate_launchctl_label,
        "timeout_seconds": 30,
    },
    "launchctl_bootstrap": {
        "handler": lambda params: [
            "launchctl", "bootstrap", f"gui/{_uid()}", params["plist_path"],
        ],
        "validate": _validate_bootstrap_plist,
        "timeout_seconds": 30,
    },
    "launchctl_list": {
        # Read-only status check for one label.
        "handler": lambda params: ["launchctl", "list", params["label"]],
        "validate": _validate_launchctl_label,
        "timeout_seconds": 10,
    },
    "health_check": {
        "handler": lambda params: [
            "curl", "-fsS", "-m", "10", params["url"],
        ],
        "validate": _validate_health_url,
        "timeout_seconds": 15,
    },
    "run_script": {
        "handler": lambda params: [
            "bash",
            os.path.join(repo_root(), "deploy", "m1-coord-scripts", f"{params['name']}.sh"),
        ],
        "validate": _validate_script_name,
        "timeout_seconds": 600,
    },
}


class DeniedAction(Exception):
    """Raised when an action is not in the whitelist or fails validation."""


def resolve_action(action: str, params: dict | None) -> tuple[list[str], str | None, int]:
    """Resolve an action name + params into (argv, cwd, timeout).

    Raises DeniedAction if the action is unknown or params fail validation.
    """
    if action not in ACTIONS:
        raise DeniedAction(f"action not in whitelist: {action!r}")

    spec = ACTIONS[action]
    params = params or {}

    validator = spec.get("validate")
    if validator is not None and not validator(params):
        raise DeniedAction(f"params failed validation for action {action!r}")

    argv = spec["handler"](params)
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise DeniedAction(f"handler for {action!r} returned non-argv")

    cwd_spec = spec.get("cwd")
    if callable(cwd_spec):
        cwd = cwd_spec(params)
    else:
        cwd = cwd_spec

    timeout = spec.get("timeout_seconds", 30)
    return argv, cwd, int(timeout)

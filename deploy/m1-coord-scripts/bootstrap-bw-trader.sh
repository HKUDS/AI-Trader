#!/usr/bin/env bash
# Idempotent re-bootstrap of bw-trader on M1.
#
# Safe operations only — does not transfer secrets, does not run migrations.
# The first-time human bootstrap (clone, .env transfer, CF tunnel creation) is
# in docs/deploy/M1-SELF-HOST-SOP-2026-05-12.md.
#
# This script:
#   - verifies the repo is on main and up to date
#   - re-installs Python deps
#   - re-bootstraps the api+scheduler launchd agents (idempotent)
#   - kicks each service and waits for the local health endpoint
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
UID_NUM="$(id -u)"

API_LABEL="ai.bwstudio.bw-trader-api"
SCHED_LABEL="ai.bwstudio.bw-trader-scheduler"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

log() { printf "\n▶ %s\n" "$*"; }

cd "$REPO_ROOT"

log "Verify branch is main"
current="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$current" != "main" ]]; then
  echo "expected main, got $current" >&2
  exit 1
fi

log "Pull main"
git fetch --prune origin
git pull --ff-only origin main

log "Install deps"
# --system + --break-system-packages: M1 uses brew Python 3.14 which is PEP 668
# externally-managed; uv refuses without the flag. Matches the coord daemon's
# whitelisted uv_pip_install action.
uv pip install --system --break-system-packages -r service/requirements.txt

for label in "$API_LABEL" "$SCHED_LABEL"; do
  plist="$LAUNCH_AGENTS/$label.plist"
  src="$REPO_ROOT/deploy/launchd/$label.plist"
  if [[ ! -f "$src" ]]; then
    echo "missing source plist: $src" >&2; exit 1
  fi
  log "Sync plist: $label"
  cp "$src" "$plist"

  if launchctl list "$label" >/dev/null 2>&1; then
    log "Kickstart $label"
    launchctl kickstart -k "gui/$UID_NUM/$label"
  else
    log "Bootstrap $label"
    # Enable first in case a prior failed bootstrap landed the label on the
    # per-user disabled list (which makes future bootstrap exit 5/IO error).
    launchctl enable "gui/$UID_NUM/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_NUM" "$plist"
  fi
done

log "Wait for local health"
for _ in $(seq 1 30); do
  if curl -fsS -m 3 http://127.0.0.1:8788/health >/dev/null; then
    echo "  ok health" ; exit 0
  fi
  sleep 2
done
echo "  health endpoint never came up" >&2
exit 1

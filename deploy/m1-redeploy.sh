#!/usr/bin/env bash
# BW-Trader · M1 redeploy
#
# Run this on the M1 Mac mini after a merge to main.
#   ~/dev/AI-Trader/deploy/m1-redeploy.sh             # full: pull + install + restart + health
#   ~/dev/AI-Trader/deploy/m1-redeploy.sh --health-only   # skip pull/install/restart
#   ~/dev/AI-Trader/deploy/m1-redeploy.sh --skip-install  # pull + restart (deps unchanged)
#
# Full SOP: docs/deploy/M1-SELF-HOST-SOP-2026-05-12.md

set -euo pipefail

# --- resolve repo root from script location, no matter where invoked from ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- flags ---
HEALTH_ONLY=0
SKIP_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --health-only) HEALTH_ONLY=1 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

UID_NUM="$(id -u)"
API_LABEL="ai.bwstudio.bw-trader-api"
SCHED_LABEL="ai.bwstudio.bw-trader-scheduler"
API_HEALTH_LOCAL="http://127.0.0.1:8788/health"
API_HEALTH_PUBLIC="https://bw-trader-api.bw-space.com/health"

log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()  { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
die() { printf "  \033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

cd "$REPO_ROOT"

if [[ "$HEALTH_ONLY" -eq 0 ]]; then
  log "Pull main"
  git fetch --prune origin
  git checkout main
  git pull --ff-only origin main
  ok "HEAD now $(git rev-parse --short HEAD): $(git log -1 --pretty=%s)"

  if [[ "$SKIP_INSTALL" -eq 0 ]]; then
    log "Install Python deps (uv)"
    (cd service && uv pip install --system -r requirements.txt)
    ok "deps in sync"
  else
    ok "skip-install flag set, leaving deps untouched"
  fi

  log "Restart launchd services"
  launchctl kickstart -k "gui/${UID_NUM}/${API_LABEL}"   || die "kickstart $API_LABEL failed — service not bootstrapped? see deploy/launchd/README.md"
  launchctl kickstart -k "gui/${UID_NUM}/${SCHED_LABEL}" || die "kickstart $SCHED_LABEL failed"
  ok "kickstart sent"

  log "Wait for API socket"
  for i in {1..15}; do
    if curl -fsS --max-time 2 "$API_HEALTH_LOCAL" >/dev/null 2>&1; then
      ok "API responding after ${i}s"
      break
    fi
    sleep 1
    [[ $i -eq 15 ]] && die "API still down after 15s — tail ~/Library/Logs/bw-trader-api.err.log"
  done
fi

log "Health checks"

# 1. Local
if curl -fsS --max-time 5 "$API_HEALTH_LOCAL" >/dev/null; then
  ok "local      $API_HEALTH_LOCAL"
else
  die "local health failed"
fi

# 2. Through Cloudflare Tunnel
if curl -fsS --max-time 8 "$API_HEALTH_PUBLIC" >/dev/null; then
  ok "tunnel     $API_HEALTH_PUBLIC"
else
  printf "  \033[1;33m!\033[0m tunnel health failed — check 'cloudflared tunnel info' and ~/.cloudflared/config.yml\n" >&2
  # non-fatal: local works, public may be transient
fi

# 3. Scheduler liveness (launchd state, not HTTP)
SCHED_STATE="$(launchctl print "gui/${UID_NUM}/${SCHED_LABEL}" 2>/dev/null | awk -F'= ' '/^[[:space:]]*state/{print $2; exit}' || true)"
if [[ "$SCHED_STATE" == "running" ]]; then
  ok "scheduler  state=running"
else
  printf "  \033[1;33m!\033[0m scheduler state='%s' — tail ~/Library/Logs/bw-trader-scheduler.err.log\n" "${SCHED_STATE:-unknown}" >&2
fi

echo
ok "M1 deploy complete · $(date '+%Y-%m-%d %H:%M:%S %Z')"

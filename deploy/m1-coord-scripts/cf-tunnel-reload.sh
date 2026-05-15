#!/usr/bin/env bash
# Reload cloudflared after an ingress config edit.
#
# Does NOT touch the ingress YAML itself — that change must be made by a human
# locally (it's a security-sensitive file). This script just signals reload.
#
# Called by coord daemon via run_script {name: cf-tunnel-reload}.
set -euo pipefail

if ! pgrep -x cloudflared >/dev/null; then
  echo "cloudflared is not running" >&2
  exit 1
fi

# cloudflared installed via brew runs under launchd as a user agent.
# `kill -HUP` triggers in-process reload of ingress rules.
pkill -HUP -x cloudflared
echo "sent HUP to cloudflared"

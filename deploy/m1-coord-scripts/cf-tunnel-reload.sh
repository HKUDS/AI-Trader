#!/usr/bin/env bash
# Reload cloudflared for bw-trader-api.
#
# Auto-applies the ingress rule + DNS route for bw-trader-api.bw-space.com on
# the existing m1-mcp-bwstudio tunnel, then HUPs cloudflared to pick it up.
#
# Idempotent — safe to re-run. The YAML insert + DNS route both no-op when
# already present.
#
# Called by coord daemon via run_script {name: cf-tunnel-reload}.
set -euo pipefail

TUNNEL_ID="${CF_TUNNEL_ID:-56d16310-5c44-4829-ae8a-d24f1fde2ccc}"  # m1-mcp-bwstudio
HOSTNAME_TARGET="${CF_HOSTNAME:-bw-trader-api.bw-space.com}"
LOCAL_SERVICE="${CF_LOCAL_SERVICE:-http://127.0.0.1:8788}"
CONFIG="${CF_CONFIG:-$HOME/.cloudflared/config.yml}"

if [[ ! -f "$CONFIG" ]]; then
  echo "cloudflared config not found at $CONFIG" >&2
  exit 1
fi

echo "==> Check $CONFIG for $HOSTNAME_TARGET"
if grep -Fq "$HOSTNAME_TARGET" "$CONFIG"; then
  echo "    ingress rule already present"
else
  echo "    appending ingress rule (before http_status catch-all)"
  tmp="$(mktemp -t cf-tunnel-reload.XXXXXX)"
  trap 'rm -f "$tmp"' EXIT
  # Insert the new ingress rule before the first `service: http_status:` line.
  # awk runs over a known-shape YAML; no shell interpolation into the data path.
  awk_status=0
  awk -v host="$HOSTNAME_TARGET" -v svc="$LOCAL_SERVICE" '
    BEGIN { inserted = 0 }
    /^[[:space:]]*-[[:space:]]+service:[[:space:]]+http_status:/ && !inserted {
      print "  - hostname: " host
      print "    service: " svc
      inserted = 1
    }
    { print }
    END {
      if (!inserted) {
        exit 2
      }
    }
  ' "$CONFIG" > "$tmp" || awk_status=$?
  if [[ "$awk_status" -ne 0 ]]; then
    echo "    no http_status: catch-all found in $CONFIG — refusing to edit blindly" >&2
    echo "    please add the following rule manually before the catch-all:" >&2
    echo "      - hostname: $HOSTNAME_TARGET" >&2
    echo "        service: $LOCAL_SERVICE" >&2
    exit 1
  fi
  cp "$CONFIG" "${CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
  mv "$tmp" "$CONFIG"
  trap - EXIT
  echo "    inserted; previous config backed up alongside"
fi

echo "==> Route DNS for $HOSTNAME_TARGET -> tunnel $TUNNEL_ID"
# `cloudflared tunnel route dns` is idempotent (existing record returns a clear
# message) — we don't fail the script on its exit code.
if command -v cloudflared >/dev/null 2>&1; then
  cloudflared tunnel route dns "$TUNNEL_ID" "$HOSTNAME_TARGET" 2>&1 | tail -5 || true
else
  echo "    cloudflared not on PATH — skipping DNS route step" >&2
fi

echo "==> HUP cloudflared"
if pgrep -x cloudflared >/dev/null; then
  pkill -HUP -x cloudflared
  echo "    HUP sent"
else
  echo "    cloudflared is not running — skipping HUP" >&2
fi

sleep 3
echo "==> Verify https://$HOSTNAME_TARGET/api/health"
curl -fsSI -m 10 "https://$HOSTNAME_TARGET/api/health" 2>&1 | head -3 \
  || echo "(not yet 200 — backend may need a tick; re-check with health-all.sh)"

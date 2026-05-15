#!/usr/bin/env bash
# Run a full health sweep from M1.
#
# Hits both loopback and public endpoints; non-zero exit if any fail.
# Called by coord daemon via run_script {name: health-all}.
set -euo pipefail

API_LOCAL="http://127.0.0.1:8788/health"
API_PUBLIC="https://bw-trader-api.bw-space.com/health"

declare -a FAILED=()

check() {
  local label="$1" url="$2"
  if curl -fsS -m 10 "$url" >/dev/null; then
    printf "  ok  %-24s %s\n" "$label" "$url"
  else
    printf "  FAIL %-24s %s\n" "$label" "$url"
    FAILED+=("$label")
  fi
}

check api-local  "$API_LOCAL"
check api-public "$API_PUBLIC"

if (( ${#FAILED[@]} > 0 )); then
  printf "\nfailed: %s\n" "${FAILED[*]}" >&2
  exit 1
fi
echo "all checks passed"

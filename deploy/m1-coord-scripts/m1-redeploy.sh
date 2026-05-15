#!/usr/bin/env bash
# Coord-friendly alias for deploy/m1-redeploy.sh full run.
#
# Invoked by the coord daemon as: run_script {name: m1-redeploy}.
# Forwards no flags — the daemon's job is to trigger the canonical redeploy.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

exec "$REPO_ROOT/deploy/m1-redeploy.sh"

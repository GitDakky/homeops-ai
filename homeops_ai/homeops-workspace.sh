#!/usr/bin/env bash
set -euo pipefail

export HOME=/config
export HERMES_HOME=/config/.hermes
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-3000}"
export HERMES_API_URL="${HERMES_API_URL:-http://127.0.0.1:8642}"
export HERMES_DASHBOARD_URL="${HERMES_DASHBOARD_URL:-http://127.0.0.1:9119}"
# HA add-on ingress/reverse-proxy access already sits behind Supervisor auth, but
# Workspace itself refuses non-loopback without a password. Set a deterministic
# add-on-local password if the user has not provided one.
export HERMES_PASSWORD="${HERMES_PASSWORD:-homeops-ai-local}"

cd /opt/hermes-workspace
exec node server-entry.js

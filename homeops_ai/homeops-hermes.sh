#!/usr/bin/env bash
set -euo pipefail

export HOME=/config
export HERMES_HOME=/config/.hermes
export HERMES_CONFIG_DIR=/config/.hermes
export HERMES_ACCEPT_HOOKS=1
export PATH="/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"

mkdir -p "$HERMES_HOME" /config/homeops
cd /config/homeops

if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: hermes command is not installed or not on PATH." >&2
  echo "PATH=$PATH" >&2
  exit 127
fi

if [ "$#" -eq 0 ]; then
  exec hermes
fi
exec hermes "$@"

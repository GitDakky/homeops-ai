#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Repo metadata"
python3 scripts/validate_release_metadata.py

echo "==> Option/schema coupling"
python3 scripts/validate_option_coupling.py

echo "==> Bash syntax"
bash -n homeops_ai/run.sh
bash -n homeops_ai/run_helpers.sh

echo "==> Python compile"
python3 -m py_compile \
  scripts/validate_option_coupling.py \
  homeops_ai/oc_config_helper.py \
  homeops_ai/render_nginx.py \
  homeops_ai/dashboard_api.py

echo "==> Python unit tests"
python3 -m unittest discover -s tests -v

echo "==> SVG parse"
python3 - <<'PY'
import xml.etree.ElementTree as ET

ET.parse("assets/openclaw-hero.svg")
ET.parse("assets/openclaw-architecture.svg")
print("svg-ok")
PY

echo "OK: local validation passed"

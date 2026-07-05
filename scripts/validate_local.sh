#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Repo metadata"
python3 scripts/validate_release_metadata.py

echo "==> Option/schema coupling"
python3 scripts/validate_option_coupling.py

echo "==> Legacy terminology guard"
python3 scripts/validate_no_openclaw_user_surface.py

echo "==> Bash syntax"
bash -n homeops_ai/run.sh
bash -n homeops_ai/run_helpers.sh

echo "==> Python compile"
python3 -m py_compile \
  scripts/validate_option_coupling.py \
  homeops_ai/oc_config_helper.py \
  homeops_ai/render_nginx.py \
  homeops_ai/dashboard_api.py \
  homeops_ai/homeops_router.py \
  scripts/dogfood_router.py

echo "==> Python unit tests"
python3 -m unittest discover -s tests -v

echo "==> Router unit tests"
if python3 -c "import pytest" 2>/dev/null; then
  python3 -m pytest tests/test_homeops_router.py -q
else
  echo "SKIP: pytest not installed (router tests run in CI and via dogfood)"
fi

echo "==> Router dogfood (offline e2e)"
python3 scripts/dogfood_router.py

echo "==> SVG parse"
python3 - <<'PY'
import xml.etree.ElementTree as ET

ET.parse("assets/hermes-hero.svg")
ET.parse("assets/hermes-architecture.svg")
print("svg-ok")
PY

echo "OK: local validation passed"

#!/usr/bin/env bash
# Run FastAPI gateway tests with a repo-local venv (see src/api/fastapi/requirements.txt).
# First run creates .venv at repo root and installs deps; override with ZACHAI_VENV.
#
# Usage (from repo root):
#   ./scripts/run-api-pytest.sh
#   ./scripts/run-api-pytest.sh -q
#   ./scripts/run-api-pytest.sh src/api/fastapi/test_story_12_3.py -q
#
# If you pass only pytest flags (first arg starts with "-"), the FastAPI test
# directory is prepended so collection does not walk the whole repo.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$ROOT"

VENV="${ZACHAI_VENV:-$ROOT/.venv}"
REQ="$ROOT/src/api/fastapi/requirements.txt"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

if [[ ! -x "$PY" ]]; then
  echo "run-api-pytest: creating venv at $VENV" >&2
  python3 -m venv "$VENV"
  "$PIP" install -U pip
  "$PIP" install -r "$REQ"
fi

if [[ $# -eq 0 ]]; then
  exec "$PY" -m pytest src/api/fastapi -q
fi
if [[ "$1" == -* ]]; then
  exec "$PY" -m pytest src/api/fastapi "$@"
fi
exec "$PY" -m pytest "$@"

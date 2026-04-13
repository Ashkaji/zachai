#!/usr/bin/env bash
# Run tests (optional), then commit all current changes with one message.
# Use at end of a BMAD phase (story, dev, code review) when the tree should be saved.
#
# Usage:
#   ./scripts/verify-and-commit.sh "feat(api): story 14.1 restore hardening"
#   VERIFY_CMD="python3 -m pytest src/api/fastapi/test_story_12_3.py -q" ./scripts/verify-and-commit.sh "test: restore"
#   ./scripts/verify-and-commit.sh --skip-tests "docs: planning only"
#
# Requires: pytest available on PATH or via python3 -m pytest (e.g. activate venv with API deps first).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SKIP_TESTS=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --skip-tests) SKIP_TESTS=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ $# -lt 1 ]]; then
  echo "usage: $0 [--skip-tests] <commit message>" >&2
  exit 1
fi
MSG="$*"

if [[ "$SKIP_TESTS" -eq 0 ]]; then
  VERIFY_CMD="${VERIFY_CMD:-python3 -m pytest src/api/fastapi -q}"
  echo "Running: $VERIFY_CMD"
  if ! eval "$VERIFY_CMD"; then
    echo "verify-and-commit: tests failed — no commit." >&2
    exit 1
  fi
else
  echo "verify-and-commit: skipping tests (--skip-tests)"
fi

if [[ -z "$(git status --porcelain)" ]]; then
  echo "Nothing to commit (working tree clean)."
  exit 0
fi

git add -A
git commit -m "$MSG"
echo "Committed: $MSG"

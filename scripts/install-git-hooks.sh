#!/bin/sh
# Point Git at repo-managed hooks (no pip / pre-commit package required).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x scripts/git-hooks/pre-commit
git config core.hooksPath scripts/git-hooks
echo "core.hooksPath=scripts/git-hooks — pre-commit hook will run scripts/sync_epic_docs.py"

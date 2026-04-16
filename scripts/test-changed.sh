#!/usr/bin/env bash
set -euo pipefail

changed="$(git diff --name-only origin/main...HEAD || true)"
if ! echo "$changed" | rg -q '^src/frontend/'; then
  echo "No frontend changes detected."
  exit 0
fi

cd src/frontend
npm test
npm run test:e2e

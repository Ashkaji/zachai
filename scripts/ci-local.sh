#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  if [[ -n "${DEV_SERVER_PID:-}" ]]; then
    kill "$DEV_SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

cd src/frontend
npm ci
npm test

# Start app server so Playwright can run exactly like CI.
npm run dev >/tmp/zachai-frontend-dev.log 2>&1 &
DEV_SERVER_PID=$!

for _ in $(seq 1 30); do
  if grep -q "Local:" /tmp/zachai-frontend-dev.log; then
    break
  fi
  sleep 1
done

npm run test:e2e
npm run test:pact:consumer

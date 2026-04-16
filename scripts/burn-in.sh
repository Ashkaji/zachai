#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../src/frontend"
iterations="${BURN_IN_ITERATIONS:-10}"

for i in $(seq 1 "$iterations"); do
  echo "Burn-in iteration $i/$iterations"
  npm run test:e2e || exit 1
done

#!/usr/bin/env bash
set -euo pipefail
# Strict mode keeps broker publication failures explicit in CI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/env-setup.sh"

pact-broker publish ./pacts   --consumer-app-version "$GIT_SHA"   --branch "$GIT_BRANCH"   --broker-base-url "$PACT_BROKER_BASE_URL"   --broker-token "$PACT_BROKER_TOKEN"

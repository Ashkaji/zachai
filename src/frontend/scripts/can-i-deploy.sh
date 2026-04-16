#!/usr/bin/env bash
set -euo pipefail
# Strict mode ensures deploy checks fail fast when broker data is missing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/env-setup.sh"

pact-broker can-i-deploy   --pacticipant "$PACTICIPANT"   --version "$GIT_SHA"   --to-environment production   --broker-base-url "$PACT_BROKER_BASE_URL"   --broker-token "$PACT_BROKER_TOKEN"   --retry-while-unknown=10   --retry-interval=30
